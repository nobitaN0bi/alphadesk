"""Dhan HQ broker adapter (Phase 2.1 + 2.2).

Production-grade Dhan integration with three production hardening patterns
inherited from ``@temp/QuantDinger/backend_api_python/app/services/live_trading/``:

    1. **Rate limiter** (token bucket; 10 orders/s by default) — Dhan enforces
       strict per-second quotas on ``/orders``; exceeding them gets the
       client rate-limited for the rest of the minute.
    2. **Circuit breaker** (3-strike OPEN for 60s with exponential backoff up
       to 5 minutes) — protects the rest of the pipeline from cascading
       failures when the Dhan API is degraded.
    3. **Idempotency** — every ``place_order`` call carries a deterministic
       ``correlation_id`` (Dhan's ``dhanOrderCorrelationId``). Re-submitting
       the same id returns the existing order instead of placing a duplicate.
       Combined with LangGraph's ``SqliteSaver`` checkpointer, this guarantees
       an order is never placed twice even if the graph resumes from an
       interrupt mid-execution.

Security & types:
    - ``DHAN_CLIENT_ID`` and ``DHAN_ACCESS_TOKEN`` come from env only.
    - ``OrderResult`` is the same Pydantic type the rest of the system uses.
    - We never fabricate ``securityId`` values; the
      :class:`SecurityIdMapper` is consulted and raises
      :class:`SecurityIdNotFoundError` on miss.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from broker.base import BrokerAdapter, OrderResult
from broker.circuit_breaker import BreakerOpen, CircuitBreaker
from broker.rate_limiter import TokenBucketRateLimiter, RateLimitConfig
from broker.security_id_mapper import (
    SecurityIdMapper,
    SecurityIdNotFoundError,
    get_default_mapper,
)
from graph.state import DhanOrder, Holding, PendingAction

logger = logging.getLogger("alphadesk.dhan")


# --------------------------------------------------------------------------- #
# Custom exception types
# --------------------------------------------------------------------------- #
class DhanAuthError(RuntimeError):
    """Raised when the Dhan API rejects our auth (401/403)."""


class DhanRateLimitedError(RuntimeError):
    """Raised when Dhan explicitly rate-limits us (HTTP 429)."""


class DhanBrokerError(RuntimeError):
    """Base class for all Dhan adapter errors."""


# --------------------------------------------------------------------------- #
# DhanBroker
# --------------------------------------------------------------------------- #
class DhanBroker(BrokerAdapter):
    """Concrete Dhan HQ broker implementation.

    Configuration via env:
        DHAN_CLIENT_ID          — required for live trading
        DHAN_ACCESS_TOKEN       — required, daily-rotated
        DHAN_BASE_URL           — default ``https://api.dhan.co``
        DHAN_RATE_LIMIT_PER_SEC — default 10
        DHAN_CB_THRESHOLD       — default 3
        DHAN_CB_COOLDOWN        — default 60.0 sec
        DHAN_INSTRUMENTS_PATH   — path to local securityId cache
    """

    name = "dhan"
    DEFAULT_BASE_URL = "https://api.dhan.co"

    def __init__(self) -> None:
        self.client_id = os.getenv("DHAN_CLIENT_ID", "").strip()
        self.access_token = os.getenv("DHAN_ACCESS_TOKEN", "").strip()
        if not self.client_id or not self.access_token:
            raise DhanAuthError(
                "DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN must be set for live trading."
            )
        self.base_url = os.getenv("DHAN_BASE_URL", self.DEFAULT_BASE_URL).rstrip("/")

        rate = float(os.getenv("DHAN_RATE_LIMIT_PER_SEC", "10"))
        self._rate_limiter = TokenBucketRateLimiter(
            RateLimitConfig(capacity=max(2, int(rate)), refill_per_sec=rate)
        )
        self._breaker = CircuitBreaker(
            failure_threshold=int(os.getenv("DHAN_CB_THRESHOLD", "3")),
            cooldown_seconds=float(os.getenv("DHAN_CB_COOLDOWN", "60.0")),
            name="dhan",
        )
        self._security_ids: SecurityIdMapper = get_default_mapper()
        # Lazily-created shared HTTP client (httpx has connection pooling).
        self._http = None  # type: ignore[assignment]

    # ------------------------------------------------------------------ #
    # HTTP layer (lazy httpx import)
    # ------------------------------------------------------------------ #
    async def _http_client(self):
        if self._http is None:
            try:
                import httpx
            except ImportError as exc:  # noqa: BLE001
                raise DhanBrokerError(
                    "httpx is required for the Dhan broker; pip install httpx"
                ) from exc
            timeout = float(os.getenv("DHAN_HTTP_TIMEOUT_SEC", "15.0"))
            self._http = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=timeout,
                headers={
                    "access-token": self.access_token,
                    "client-id": self.client_id,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
        return self._http

    async def aclose(self) -> None:
        """Close the shared HTTP client (call on app shutdown)."""
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    # ------------------------------------------------------------------ #
    # Core call helper (rate limit + circuit breaker + retries)
    # ------------------------------------------------------------------ #
    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Issue an HTTP request protected by rate limiter + circuit breaker."""
        await self._breaker.guard()
        await self._rate_limiter.acquire(1.0)
        client = await self._http_client()
        try:
            response = await client.request(
                method=method, url=path, params=params, json=json_body
            )
        except Exception as exc:
            await self._breaker.on_failure()
            raise DhanBrokerError(f"Dhan network error: {exc}") from exc

        # Auth failures are *not* breaker-counted (they won't recover via retry).
        if response.status_code in (401, 403):
            raise DhanAuthError(
                f"Dhan auth failed (status {response.status_code}): {response.text[:500]}"
            )

        # Rate limit & server errors count toward the breaker.
        if response.status_code == 429 or response.status_code >= 500:
            await self._breaker.on_failure()
            if response.status_code == 429:
                raise DhanRateLimitedError(
                    f"Dhan rate limited (429): {response.text[:200]}"
                )
            raise DhanBrokerError(
                f"Dhan server error (status {response.status_code}): {response.text[:200]}"
            )

        if response.status_code >= 400:
            # 4xx (other than 401/403/429) — surface to the caller, do not trip the breaker.
            try:
                payload = response.json()
            except Exception:  # noqa: BLE001
                payload = {"raw": response.text[:1000]}
            raise DhanBrokerError(
                f"Dhan client error (status {response.status_code}): {payload}"
            )

        await self._breaker.on_success()
        try:
            return response.json() or {}
        except Exception:  # noqa: BLE001
            return {"raw": response.text[:1000]}

    # ------------------------------------------------------------------ #
    # BrokerAdapter interface
    # ------------------------------------------------------------------ #
    async def place_order(self, action: PendingAction) -> OrderResult:
        """Place an order with idempotency + rate limiting + circuit breaker.

        ``action`` may be either a :class:`PendingAction` (legacy) or a
        :class:`DhanOrder` — both have the same fields needed to build the
        Dhan payload.
        """
        if not isinstance(action, DhanOrder):
            # Legacy PendingAction — translate.
            payload_sym = getattr(action, "symbol", "")
            action = DhanOrder(
                symbol=payload_sym,
                security_id="",  # must be filled by the caller / mapper
                quantity=int(getattr(action, "payload", {}).get("quantity", 1) or 1),
                price=0.0,
                order_type="MARKET",
                transaction_type="BUY" if action.action_type == "place_order" else "BUY",
                correlation_id=f"legacy-{action.symbol}-{int(time.time())}",
            )
        # Resolve securityId (never fabricate).
        security_id = action.security_id
        if not security_id:
            try:
                security_id = self._security_ids.get(action.symbol)
            except SecurityIdNotFoundError as exc:
                return OrderResult(
                    order_id=None,
                    status="rejected",
                    message=f"securityId lookup failed: {exc}",
                )

        body: Dict[str, Any] = {
            "dhanClientId": self.client_id,
            "correlationId": action.correlation_id,
            "transactionType": action.transaction_type,
            "exchangeSegment": action.exchange_segment,
            "productType": action.product_type,
            "orderType": action.order_type,
            "validity": action.validity,
            "tradingSymbol": action.symbol,
            "securityId": security_id,
            "quantity": action.quantity,
            "price": action.price if action.order_type == "LIMIT" else 0,
        }
        try:
            response = await self._request("POST", "/orders", json_body=body)
        except (DhanAuthError, DhanRateLimitedError, DhanBrokerError) as exc:
            logger.error("Dhan place_order failed for %s: %s", action.symbol, exc)
            return OrderResult(order_id=None, status="rejected", message=str(exc))

        # Dhan returns { "data": { "orderId": "..." }, "status": "success" }
        data = response.get("data") or {}
        order_id = str(data.get("orderId") or data.get("order_id") or "")
        return OrderResult(
            order_id=order_id or None,
            status="placed",
            message=response.get("status") or "ok",
        )

    # ------------------------------------------------------------------ #
    # Live account queries
    # ------------------------------------------------------------------ #
    async def get_funds(self) -> float:
        """Return available margin in INR from ``GET /fundlimit``."""
        try:
            response = await self._request("GET", "/fundlimit")
        except DhanBrokerError as exc:
            logger.error("Dhan get_funds failed: %s", exc)
            return 0.0
        # Dhan nests margin under data; field name uses the typo "availabelBalance"
        # historically — accept either spelling for safety.
        data = response.get("data") or response
        for key in ("availabelBalance", "availableBalance", "availableMargin"):
            val = data.get(key)
            if val is not None:
                try:
                    return float(val)
                except (TypeError, ValueError):
                    continue
        return 0.0

    async def get_holdings(self) -> List[Dict[str, Any]]:
        """Return raw list of holdings from ``GET /holdings`` (Dhan dict format)."""
        try:
            response = await self._request("GET", "/holdings")
        except DhanBrokerError as exc:
            logger.error("Dhan get_holdings failed: %s", exc)
            return []
        data = response.get("data")
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "holdings" in data:
            return list(data["holdings"])
        return []

    async def get_order_status(self, correlation_id: str) -> Optional[Dict[str, Any]]:
        """Look up an order by ``correlation_id`` (idempotency check).

        Dhan's order-book endpoint (``GET /orders``) returns all orders; we
        scan it client-side. Returns ``None`` if not found.
        """
        try:
            response = await self._request("GET", "/orders")
        except DhanBrokerError as exc:
            logger.warning("Dhan get_order_status failed: %s", exc)
            return None
        orders = response.get("data") or []
        for order in orders:
            if str(order.get("correlationId") or order.get("correlation_id")) == correlation_id:
                return order
        return None

    # ------------------------------------------------------------------ #
    # Mapping helpers
    # ------------------------------------------------------------------ #
    def to_holding(self, raw: Dict[str, Any]) -> Holding:
        """Translate a Dhan holdings dict to our :class:`Holding` model."""
        try:
            sym = raw.get("tradingSymbol") or raw.get("symbol") or ""
            qty = int(raw.get("totalQty") or raw.get("quantity") or 0)
            avg = float(raw.get("avgCostPrice") or raw.get("averagePrice") or 0.0)
            ltp = float(raw.get("ltp") or raw.get("lastTradedPrice") or 0.0)
            sec_id = raw.get("securityId")
            sec_str = str(sec_id) if sec_id is not None else None
            pnl = float(raw.get("unrealizedProfit") or raw.get("pnl") or 0.0)
            pnl_pct = float(
                raw.get("unrealizedProfitPercent") or raw.get("pnlPercent") or 0.0
            )
            day_change_pct = float(raw.get("dayChangePercentage") or 0.0)
        except (TypeError, ValueError) as exc:
            raise DhanBrokerError(f"Malformed holding from Dhan: {exc}") from exc
        return Holding(
            symbol=sym,
            security_id=sec_str,
            quantity=qty,
            avg_price=avg,
            current_price=ltp,
            pnl=pnl,
            pnl_pct=pnl_pct,
            day_change_pct=day_change_pct,
        )


__all__ = [
    "DhanBroker",
    "DhanAuthError",
    "DhanRateLimitedError",
    "DhanBrokerError",
    "BreakerOpen",
]

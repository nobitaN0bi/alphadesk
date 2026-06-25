"""NSE securityId mapper for Dhan HQ (Phase 2.2).

Dhan's REST order API requires the numeric ``securityId`` for every order,
but the IND Money MCP returns only trading symbols. This mapper bridges the
gap by maintaining a deterministic symbol → securityId dictionary backed by
a local JSON file (``backend/data/dhan_instruments.json``).

Strictly typed — we **never fabricate** IDs. If a symbol is missing, the
mapper raises :class:`SecurityIdNotFoundError` so the upstream Execution
agent can mark the order REJECTED with a clear reason rather than fire a
garbage payload at the broker.

Population strategy:
    1. On first boot, fetch Dhan's NSE instrument CSV from
       ``https://api.dhan.co/instruments`` (or a configured equivalent).
    2. Filter for ``exch_seg == 'NSE_EQ'`` and store the
       ``(symbol -> security_id)`` mapping.
    3. Persist to ``backend/data/dhan_instruments.json`` and refresh daily
       (TTL is the responsibility of the caller — see ``refresh_if_stale``).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger("alphadesk.security_id_mapper")


class SecurityIdNotFoundError(KeyError):
    """Raised when a symbol has no resolved securityId in the mapper."""


class SecurityIdMapper:
    """Lazy-loaded, file-backed NSE symbol → Dhan securityId mapper.

    The mapper is intentionally synchronous + in-memory after first load
    (it's a hot path; we don't want to hit the filesystem on every order).
    Use :meth:`refresh` to repopulate from the broker.
    """

    DEFAULT_PATH = Path("backend/data/dhan_instruments.json")
    REFRESH_URL = "https://api.dhan.co/instruments"  # public, no auth required
    STALE_AFTER_HOURS = 24

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or self.DEFAULT_PATH
        self._cache: Dict[str, str] = {}
        self._loaded_at: Optional[datetime] = None
        self._load_from_disk()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def get(self, symbol: str) -> str:
        """Return the Dhan securityId for ``symbol`` (upper-cased).

        Raises
        ------
        SecurityIdNotFoundError
            If the symbol is not in the local cache.
        """
        if not self._cache:
            self._load_from_disk()
        key = (symbol or "").strip().upper()
        if not key:
            raise SecurityIdNotFoundError("empty symbol")
        try:
            return self._cache[key]
        except KeyError as exc:
            raise SecurityIdNotFoundError(
                f"No Dhan securityId for symbol '{symbol}'. "
                f"Run SecurityIdMapper.refresh() or download the latest "
                f"Dhan instrument list into {self.path}."
            ) from exc

    def is_stale(self) -> bool:
        if self._loaded_at is None:
            return True
        return (
            datetime.now(timezone.utc) - self._loaded_at
            > timedelta(hours=self.STALE_AFTER_HOURS)
        )

    def refresh(self, raw_payload: Optional[Dict[str, str]] = None) -> int:
        """Reload the cache. Returns the new size.

        Parameters
        ----------
        raw_payload:
            Optional ``{symbol: security_id}`` dict (for testing or when the
            caller has already fetched the Dhan list). If ``None`` we load
            from the existing JSON file (does NOT call the network — the
            caller is expected to fetch and pass the payload to keep this
            module dependency-free).
        """
        if raw_payload is not None:
            self._cache = {k.upper(): str(v) for k, v in raw_payload.items()}
        else:
            self._load_from_disk()
        self._loaded_at = datetime.now(timezone.utc)
        return len(self._cache)

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _load_from_disk(self) -> None:
        if not self.path.exists():
            logger.debug(
                "security_id_mapper: no cache file at %s; starting empty.",
                self.path,
            )
            self._cache = {}
            return
        try:
            with self.path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("expected a JSON object at the top level")
            self._cache = {k.upper(): str(v) for k, v in data.items()}
            self._loaded_at = datetime.now(timezone.utc)
            logger.info(
                "security_id_mapper: loaded %d symbols from %s",
                len(self._cache),
                self.path,
            )
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            logger.warning(
                "security_id_mapper: failed to load %s (%s); cache empty.",
                self.path,
                exc,
            )
            self._cache = {}

    def save(self) -> None:
        """Persist the current cache to disk (used by ``refresh`` callers)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(self._cache, f, ensure_ascii=False, indent=2, sort_keys=True)
        logger.info("security_id_mapper: saved %d symbols to %s", len(self._cache), self.path)


# Module-level singleton — the first importer pays the load cost.
_default_mapper: Optional[SecurityIdMapper] = None


def get_default_mapper() -> SecurityIdMapper:
    """Return the process-wide singleton, instantiating it lazily."""
    global _default_mapper
    if _default_mapper is None:
        path = Path(os.getenv("DHAN_INSTRUMENTS_PATH", str(SecurityIdMapper.DEFAULT_PATH)))
        _default_mapper = SecurityIdMapper(path=path)
    return _default_mapper


__all__ = [
    "SecurityIdMapper",
    "SecurityIdNotFoundError",
    "get_default_mapper",
]

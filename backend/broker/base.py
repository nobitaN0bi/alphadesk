"""BrokerAdapter abstract base class + loader.

Defines the contract a concrete broker (e.g. ``backend/broker/dhan.py``) must
implement for live order placement, plus :func:`load_broker` which returns
the configured adapter or ``None``.

The Dhan adapter is wired here in Phase 2.1; setting ``BROKER=dhan`` plus
``DHAN_CLIENT_ID`` and ``DHAN_ACCESS_TOKEN`` enables live trading. When
``BROKER`` is empty, the Execution agent operates the paper watchlist only
(the original AlphaDesk behavior).
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from typing import Optional

from pydantic import BaseModel, Field

from graph.state import PendingAction

logger = logging.getLogger("alphadesk.broker")


class OrderResult(BaseModel):
    """Typed result of a broker order placement."""

    order_id: Optional[str] = Field(None, description="Broker-assigned order id, if accepted.")
    status: str = Field(..., description="Order status, e.g. 'placed', 'rejected'.")
    message: Optional[str] = Field(None, description="Human-readable detail from the broker.")


class BrokerAdapter(ABC):
    """Interface every concrete broker integration must implement."""

    name: str = "base"

    @abstractmethod
    def place_order(self, action: PendingAction) -> OrderResult:
        """Place (or simulate) an order for the given approved action."""
        raise NotImplementedError


def load_broker() -> Optional[BrokerAdapter]:
    """Return the configured ``BrokerAdapter``, or ``None`` when live trading is disabled.

    Reads the ``BROKER`` env var. Supported values:

        - ``dhan``  -> :class:`broker.dhan.DhanBroker` (Phase 2.1, live trading)
        - empty    -> ``None`` (paper watchlist mode)

    If ``BROKER=dhan`` is set but the Dhan adapter fails to import (e.g.
    missing ``httpx``), this logs a warning and returns ``None`` so the rest
    of the system stays in paper mode rather than crashing the request.
    """
    name = os.environ.get("BROKER", "").strip().lower()
    if not name:
        return None
    if name == "dhan":
        try:
            from broker.dhan import DhanBroker  # local import — avoids hard dep

            return DhanBroker()
        except Exception as exc:  # noqa: BLE001 - never crash the request
            logger.error(
                "BROKER=dhan configured but DhanBroker failed to init (%s); "
                "falling back to paper watchlist.",
                exc,
            )
            return None
    logger.warning("Unknown BROKER=%r; falling back to paper watchlist.", name)
    return None

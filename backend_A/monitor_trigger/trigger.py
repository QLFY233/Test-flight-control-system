"""Monitor trigger — handles alert events from backend B.

When B sends an alert event:
1. Forwards to frontend via WebSocket
2. Wakes up beta with alert context for advisory generation
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from backend_A.state import AppState

logger = logging.getLogger(__name__)


class MonitorTrigger:
    """Handler for B→A alert events."""

    def __init__(self, app_state: "AppState") -> None:
        self._app_state = app_state
        # Throttle: prevent duplicate alerts in window
        self._alert_history: dict[str, float] = {}
        self._throttle_seconds = 2.0

    async def handle_alert(self, payload: dict) -> None:
        """Handle an incoming alert from B.

        1. Throttle duplicate alerts (same code within throttle window).
        2. Forward to all WebSocket clients.
        3. Inject alert context for beta.
        """
        code = payload.get("code", "unknown")
        level = payload.get("level", "warn")
        now = time.time()

        # Throttle (except critical)
        if level != "critical":
            last = self._alert_history.get(code, 0)
            if now - last < self._throttle_seconds:
                logger.debug(f"monitor_trigger: throttling alert code={code}")
                return
        self._alert_history[code] = now

        logger.warning(
            f"monitor_trigger: alert level={level} code={code} "
            f"detail={payload.get('detail', '')}"
        )

        # Forward to frontend via WS (bridge already handles this)
        # Inject alert into beta context for advisory generation
        alert_context = (
            f"[SYSTEM ALERT] Level: {level}, Code: {code}\n"
            f"Detail: {payload.get('detail', 'N/A')}\n"
        )
        if payload.get("suggestion"):
            alert_context += f"Suggestion: {payload['suggestion']}\n"
        alert_context += (
            f"Time: {now}\n"
            f"You should analyze this alert using available analytics tools "
            f"and provide a safety advisory. Do NOT auto-execute any commands."
        )

        # Store for beta's next interaction
        async with self._app_state.lock:
            if not hasattr(self._app_state, 'alert_contexts'):
                self._app_state.alert_contexts = []
            self._app_state.alert_contexts.append({
                "timestamp": now,
                "level": level,
                "code": code,
                "context": alert_context,
            })
            # Keep only last 10 alerts
            if len(self._app_state.alert_contexts) > 10:
                self._app_state.alert_contexts = self._app_state.alert_contexts[-10:]


# ---------------------------------------------------------------------------
# Alert handler that can be registered on the bus
# ---------------------------------------------------------------------------

class AlertHandler:
    """Bus-compatible alert handler."""

    def __init__(self, app_state: "AppState") -> None:
        self.trigger = MonitorTrigger(app_state)

    async def handle_event(self, tool: str, payload: dict) -> None:
        """Handle an alert event from the bus."""
        if tool == "alert":
            await self.trigger.handle_alert(payload)

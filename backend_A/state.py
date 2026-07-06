"""Shared application state with asyncio.Lock concurrency protection."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional

from backend_A.config_loader import Config


@dataclass
class AppState:
    """Thread-unsafe shared state protected by asyncio.Lock."""

    config: Config

    # Flight session
    session_id: Optional[str] = None

    # Current drone pose (updated by B→A pose events)
    current_pose: Optional[dict] = None
    # {
    #   "pos": [x, y, z],
    #   "quat": [w, x, y, z],
    #   "vel": [vx, vy, vz],
    #   "accel": [ax, ay, az],
    #   "angularVel": [wx, wy, wz],
    #   "ts": float
    # }

    # Alpha translator input queue
    alpha_input_queue: list[str] = field(default_factory=list)

    # Current trajectory plan from alpha
    current_trajectory_plan: Optional[object] = None

    # Beta proposal pending human approval
    pending_proposal: Optional[dict] = None
    # { "id": str, "intent": str, "created_at": float, "session_id": str }

    # Last message the human sent to beta (for forward_last_human_message)
    last_human_message_to_beta: Optional[str] = None

    # Pending async translation task (non-blocking alpha)
    pending_translation: Optional[asyncio.Task] = None

    # Last translated intent (TrajectorySpec)
    last_intent: Optional[dict] = None

    # IPC connection status
    ipc_connected: bool = False

    # Last pong timestamp from B
    last_pong_at: float = 0.0

    # Flight status: idle / hovering / planned / executing / completed / aborted
    flight_status: str = "idle"

    # LLM health tracking
    last_llm_call_ok: bool = True

    # Telemetry buffer (batch write)
    telemetry_buffer: list[dict] = field(default_factory=list)

    # Concurrency protection
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    # When current_pose was last updated
    pose_updated_at: float = 0.0

    # Active WebSocket connections
    ws_connections: set = field(default_factory=set)

    # Active SSE streams
    sse_streams: set = field(default_factory=set)

    def drain_alpha_input_queue(self) -> list[str]:
        """Atomically drain and return all pending alpha inputs."""
        items = list(self.alpha_input_queue)
        self.alpha_input_queue.clear()
        return items

    def add_alpha_input(self, text: str) -> None:
        """Thread-safe: append to alpha input queue."""
        self.alpha_input_queue.append(text)

    def update_pose(self, pose_data: dict) -> None:
        """Update current pose with timestamp."""
        self.current_pose = pose_data
        self.pose_updated_at = time.time()

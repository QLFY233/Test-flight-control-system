"""Alpha agent — non-conversational trajectory translator.

Alpha translates flight intent text into TrajectorySpec JSON.
It does NOT output natural language and does NOT converse with humans.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from pydantic import BaseModel, Field

from backend_A.agents.llm import make_agent
from backend_A.agents.translator_base import TrajectoryTranslator, TranslateError

if TYPE_CHECKING:
    from backend_A.state import AppState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# TrajectorySpec — the structured output alpha produces
# ---------------------------------------------------------------------------

class Waypoint(BaseModel):
    """A single waypoint in a trajectory segment."""
    t: float = 0.0
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    yaw: Optional[float] = None


class TrajectorySegment(BaseModel):
    """One segment of a trajectory (e.g. takeoff, waypoint leg, land)."""
    id: str = ""
    type: str = "waypoint"  # waypoint / hover / takeoff / land
    waypoints: list[Waypoint] = Field(default_factory=list)
    speed: float = 1.0
    acceleration: float = 1.0
    duration: float = 0.0
    description: str = ""


class TrajectorySpec(BaseModel):
    """Complete trajectory specification produced by alpha."""
    task_id: str = ""
    segments: list[TrajectorySegment] = Field(default_factory=list)
    constraints: dict = Field(default_factory=lambda: {
        "speed_max": 1.5,
        "accel_max": 2.0,
        "angular_velocity_max": 0.5,
        "keep_clear_distance": 0.5,
    })
    metadata: dict = Field(default_factory=dict)

    @classmethod
    def hover(cls, pose: Optional[dict] = None) -> "TrajectorySpec":
        """Create a safe hover-at-current-position trajectory."""
        pos = [0.0, 0.0, 0.5]
        if pose and pose.get("pos"):
            pos = list(pose["pos"])
        return cls(
            task_id=f"hover_{int(time.time())}",
            segments=[
                TrajectorySegment(
                    id="hover",
                    type="hover",
                    waypoints=[Waypoint(t=0, x=pos[0], y=pos[1], z=pos[2])],
                    speed=0.0,
                    duration=1.0,
                    description="Safety hover at current position",
                )
            ],
        )

    def has_remaining(self) -> bool:
        """Check if there are unexecuted segments."""
        return len(self.segments) > 0

    def next_segment(self) -> Optional[dict]:
        """Pop and return the next segment dict."""
        if not self.segments:
            return None
        seg = self.segments.pop(0)
        return seg.model_dump()

    def to_dict(self) -> dict:
        return self.model_dump()


# ---------------------------------------------------------------------------
# LLM Translator — uses Pydantic AI Agent with output_type=TrajectorySpec
# ---------------------------------------------------------------------------

class LLMTranslator(TrajectoryTranslator):
    """Alpha implementation using an LLM (DeepSeek) for intent-to-trajectory translation."""

    def __init__(self, agent) -> None:
        self._agent = agent

    async def translate(self, intent: str, pose: Optional[dict] = None) -> dict:
        """Translate intent text into a TrajectorySpec dict via LLM."""
        context_parts = [f"Flight intent: {intent}"]
        if pose:
            context_parts.append(
                f"Current drone state: position={pose.get('pos')}, "
                f"velocity={pose.get('vel')}, "
                f"orientation quaternion={pose.get('quat')}"
            )
        prompt = "\n".join(context_parts)

        try:
            result = await self._agent.run(prompt)
            spec: TrajectorySpec = result.output
            if spec is None:
                raise TranslateError("LLM returned no output")
            return spec.to_dict()
        except Exception as exc:
            raise TranslateError(f"Translation failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def _load_prompt(filename: str) -> str:
    """Load a prompt from the prompts/ directory."""
    prompt_path = Path(__file__).resolve().parent.parent / "prompts" / filename
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    # Fallback default prompts
    if "alpha" in filename:
        return (
            "你是试飞控制系统的翻译器 Alpha。你的唯一职责是把飞行指令翻译成 "
            "TrajectorySpec JSON。你不与人对话。输出必须是严格的 TrajectorySpec 格式。\n\n"
            "## TrajectorySpec 格式\n"
            "你必须输出一个 JSON 对象，包含 segments 列表。每个 segment 代表一段轨迹。\n\n"
            "### Segment 类型\n"
            "- takeoff: 从当前位置起飞到指定高度\n"
            "- waypoint: 飞行到指定航点\n"
            "- hover: 在当前位置悬停\n"
            "- land: 降落\n\n"
            "### 安全规则\n"
            "1. 起飞前确保高度足够(至少 0.5m)\n"
            "2. 航点之间保持安全距离(至少 0.5m)\n"
            "3. 速度不超过场地限制(默认 1.5 m/s)\n"
            "4. 所有航点必须在场地边界内\n"
            "5. 不确定时使用 hover 作为安全默认\n\n"
            "请将用户的飞行指令翻译为 TrajectorySpec 格式输出。"
        )
    return ""


def make_translator() -> TrajectoryTranslator:
    """Create the alpha translator based on ALPHA_BACKEND env var.

    ALPHA_BACKEND values:
    - "llm" (default): Use LLM (DeepSeek) for translation.
    - "small": Future — use trained small model for translation.
    """
    backend = os.environ.get("ALPHA_BACKEND", "llm")
    if backend == "small":
        raise NotImplementedError(
            "Small model alpha translator is not yet implemented. "
            "Set ALPHA_BACKEND=llm to use the LLM translator."
        )

    instructions = _load_prompt("alpha.md")
    agent = make_agent(instructions=instructions, output_type=TrajectorySpec)
    logger.info(f"agents/alpha: created {backend} translator")
    return LLMTranslator(agent)


# ---------------------------------------------------------------------------
# Alpha Loop
# ---------------------------------------------------------------------------

async def alpha_loop(app_state: "AppState", bus_router) -> None:
    """Periodic alpha translation loop.

    1. Sleep for configurable period.
    2. Drain alpha input queue.
    3. Arbitrate: new inputs > existing plan > hover default.
    4. Translate intent to TrajectorySpec.
    5. Send to solver via bus.
    6. Push alpha_output via WebSocket.
    """
    translator = make_translator()

    # Register alpha as a bus component
    from backend_A.bus.registry import register
    register("alpha", translator, tools=["translate"])

    logger.info(
        f"agents/alpha: loop started, period={app_state.config.alpha_loop_period}s"
    )

    backoff = 1.0

    while True:
        try:
            await asyncio.sleep(app_state.config.alpha_loop_period)

            pose = None
            alpha_inputs: list[str] = []

            async with app_state.lock:
                pose = app_state.current_pose
                alpha_inputs = app_state.drain_alpha_input_queue()

            spec: Optional[dict] = None

            # Arbitration: new inputs > existing plan > hover
            if alpha_inputs:
                # Join multiple inputs with newlines
                combined_intent = "\n".join(alpha_inputs)
                try:
                    spec = await translator.translate(combined_intent, pose)
                    async with app_state.lock:
                        app_state.last_intent = spec
                    logger.info(f"alpha: translated intent → {spec.get('task_id', '?')}")
                except TranslateError as exc:
                    logger.error(f"alpha: translation failed: {exc}")
                    # On failure, fall through to hover
                    spec = TrajectorySpec.hover(pose).to_dict()

            elif app_state.current_trajectory_plan is not None:
                # Continue existing plan
                try:
                    plan = TrajectorySpec(**app_state.current_trajectory_plan)
                    if plan.has_remaining():
                        seg = plan.next_segment()
                        spec = {
                            "task_id": plan.task_id,
                            "segments": [seg] if seg else [],
                            "constraints": plan.constraints,
                            "metadata": plan.metadata,
                        }
                    else:
                        spec = TrajectorySpec.hover(pose).to_dict()
                except Exception:
                    spec = TrajectorySpec.hover(pose).to_dict()

            else:
                # Default: hover
                spec = TrajectorySpec.hover(pose).to_dict()

            # Store current plan
            if spec:
                async with app_state.lock:
                    app_state.current_trajectory_plan = spec

                # Send to solver via bus
                try:
                    await bus_router.call(
                        to="solver", tool="trajectory", args=spec
                    )
                except Exception as exc:
                    logger.error(f"alpha: failed to send to solver: {exc}")

                # Push alpha_output via WebSocket
                await _ws_push_alpha_output(app_state, spec)

            # Reset backoff on success
            backoff = 1.0

        except asyncio.CancelledError:
            logger.info("agents/alpha: loop cancelled")
            break
        except Exception as exc:
            logger.error(f"agents/alpha: loop error: {exc}", exc_info=True)
            # Backoff restart
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 5.0)


async def _ws_push_alpha_output(app_state: "AppState", spec: dict) -> None:
    """Push alpha output to all WebSocket clients."""
    import json as _json
    msg = _json.dumps({
        "type": "alpha_output",
        "schema_version": 1,
        "trajectory": spec,
    }, ensure_ascii=False)
    dead = set()
    for ws in list(app_state.ws_connections):
        try:
            await ws.send_text(msg)
        except Exception:
            dead.add(ws)
    app_state.ws_connections -= dead


def start_alpha_loop(app_state: "AppState", bus_router) -> asyncio.Task:
    """Start the alpha loop as a background asyncio Task."""
    return asyncio.create_task(alpha_loop(app_state, bus_router))

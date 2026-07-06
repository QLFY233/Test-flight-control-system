"""
Startup and shutdown orchestration for Backend B.

Manages the lifecycle of all components:
  1. Load configuration
  2. Initialize BState
  3. Initialize ROS node
  4. Initialize bus registry (solver, monitor, heartbeat)
  5. Initialize IPC client and connect to Backend A
  6. Start solver thread (20 Hz)
  7. Start monitor thread (10 Hz)
  8. Start uplink thread (10 Hz) - sends telemetry/events to A
"""

import logging
import threading
import time
import signal
import sys
from typing import Optional

logger = logging.getLogger("backend_b.lifecycle")

# Import constants
SOLVER_TICK_RATE = 20.0
SOLVER_TICK_INTERVAL = 1.0 / SOLVER_TICK_RATE

MONITOR_TICK_RATE = 10.0
MONITOR_TICK_INTERVAL = 1.0 / MONITOR_TICK_RATE

UPLINK_TICK_RATE = 10.0
UPLINK_TICK_INTERVAL = 1.0 / UPLINK_TICK_RATE


def startup(
    field_path: str = "config/field.yaml",
    constraints_path: str = "config/default_constraints.yaml",
    socket_path: str = "/tmp/flight_control_AB.sock",
    ros_node_name: str = "backend_b",
) -> tuple:
    """
    Initialize all Backend B components and start background threads.

    Args:
        field_path: Path to field.yaml.
        constraints_path: Path to default_constraints.yaml.
        socket_path: Unix socket path to connect to Backend A.
        ros_node_name: ROS node name.

    Returns:
        Tuple of (bstate, solver, monitor, ipc_client, solver_thread, monitor_thread, uplink_thread)
    """
    logger.info("=" * 60)
    logger.info("Backend B starting up...")
    logger.info("=" * 60)

    # --- Step 1: Load configuration ---
    logger.info("Loading configuration...")
    from backend_B.config_loader import load_config, Config
    try:
        config = load_config(field_path, constraints_path)
    except FileNotFoundError as e:
        logger.error("Config file not found: %s", e)
        raise
    logger.info(
        "Config loaded: field=%s, presets=%s",
        field_path,
        list(config.presets.keys()) if config.presets else "none",
    )

    # --- Step 2: Initialize BState ---
    from backend_B.state import BState
    bstate = BState()
    bstate.field = config.field
    bstate.default_constraints = {
        "speed_max": config.default_constraints.speed_max,
        "accel_max": config.default_constraints.accel_max,
        "angular_velocity_max": config.default_constraints.angular_velocity_max,
        "keep_clear_distance": config.default_constraints.keep_clear_distance,
        "ceiling": config.default_constraints.ceiling,
        "floor": config.default_constraints.floor,
    }
    logger.info("BState initialized")

    # --- Step 3: Initialize ROS node ---
    logger.info("Initializing ROS node '%s'...", ros_node_name)
    from backend_B.rosbridge.node import init_ros_node
    init_ros_node(ros_node_name)

    # --- Step 4: Initialize bus registry ---
    logger.info("Initializing bus registry...")
    from backend_B.bus.registry import register
    from backend_B.bus.protocol import COMP_SOLVER, COMP_MONITOR, COMP_HEARTBEAT

    # Create Field model for solver
    from backend_B.solver.field import Field
    field = Field.from_config(config)

    # Solver component
    from backend_B.solver.component import SolverComponent
    solver = SolverComponent(bstate.default_constraints)
    register(COMP_SOLVER, solver)

    # Monitor component
    from backend_B.monitor.component import MonitorComponent
    monitor = MonitorComponent(bstate.default_constraints, config.field)
    register(COMP_MONITOR, monitor)

    # Heartbeat component (simple ping/pong handler)
    class HeartbeatComponent:
        def handle(self, tool, args, bstate):
            if tool == "ping":
                return {"pong": True, "timestamp": time.time()}
            return {"status": "error", "detail": f"Unknown tool: {tool}"}
    register(COMP_HEARTBEAT, HeartbeatComponent())

    logger.info("Bus registry: %s", list(["solver", "monitor", "heartbeat"]))

    # --- Step 5: Initialize IPC client ---
    logger.info("Initializing IPC client (socket: %s)...", socket_path)
    from backend_B.ipc.client import IpcClient
    ipc_client = IpcClient(socket_path=socket_path, bstate=bstate)
    ipc_client.start()

    # --- Step 6: Initialize ROS publisher and subscriber ---
    from backend_B.rosbridge.adapter import Phase1Adapter
    from backend_B.rosbridge.publisher import SetpointPublisher
    from backend_B.rosbridge.subscriber import PoseSubscriber

    adapter = Phase1Adapter()
    publisher = SetpointPublisher(adapter)
    subscriber = PoseSubscriber(bstate)

    # Wait briefly for connections
    time.sleep(0.5)

    # --- Step 7: Start solver thread (20 Hz) ---
    logger.info("Starting solver thread at %.1f Hz...", SOLVER_TICK_RATE)
    solver_stop = threading.Event()

    def _solver_loop():
        next_tick = time.time()
        while not solver_stop.is_set():
            try:
                events = solver.tick(bstate, adapter)
                if events:
                    for evt in events:
                        event_name = evt.get("event", "unknown")
                        data = evt.get("data", {})
                        ipc_client.send_event(event_name, data)
            except Exception as exc:
                logger.exception("Solver tick error: %s", exc)

            next_tick += SOLVER_TICK_INTERVAL
            sleep_time = next_tick - time.time()
            if sleep_time > 0:
                time.sleep(sleep_time)
            else:
                next_tick = time.time() + SOLVER_TICK_INTERVAL

    solver_thread = threading.Thread(target=_solver_loop, name="solver-tick", daemon=True)
    solver_thread.start()

    # --- Step 8: Start monitor thread (10 Hz) ---
    logger.info("Starting monitor thread at %.1f Hz...", MONITOR_TICK_RATE)
    monitor_stop = threading.Event()

    def _monitor_loop():
        next_tick = time.time()
        while not monitor_stop.is_set():
            try:
                current_sample = solver.current_trajectory
                if current_sample and current_sample.samples:
                    sample_idx = min(solver._sample_index, len(current_sample.samples) - 1)
                    sample = current_sample.samples[sample_idx]
                else:
                    sample = None

                alerts = monitor.tick(bstate, sample)
                if alerts:
                    for alert in alerts:
                        ipc_client.send_event("alert", alert)
            except Exception as exc:
                logger.exception("Monitor tick error: %s", exc)

            next_tick += MONITOR_TICK_INTERVAL
            sleep_time = next_tick - time.time()
            if sleep_time > 0:
                time.sleep(sleep_time)
            else:
                next_tick = time.time() + MONITOR_TICK_INTERVAL

    monitor_thread = threading.Thread(target=_monitor_loop, name="monitor-tick", daemon=True)
    monitor_thread.start()

    # --- Step 9: Start uplink thread (10 Hz) ---
    logger.info("Starting uplink thread at %.1f Hz...", UPLINK_TICK_RATE)
    uplink_stop = threading.Event()

    def _uplink_loop():
        next_tick = time.time()
        while not uplink_stop.is_set():
            try:
                if bstate.ipc_connected and bstate.has_pose():
                    pose = bstate.get_pose_list()
                    telemetry = {
                        "event": "telemetry",
                        "data": {
                            "pose": pose,
                            "solver_status": bstate.solver_status,
                            "timestamp": time.time(),
                        },
                    }
                    ipc_client.send_event("telemetry", telemetry["data"])
            except Exception as exc:
                logger.exception("Uplink error: %s", exc)

            next_tick += UPLINK_TICK_INTERVAL
            sleep_time = next_tick - time.time()
            if sleep_time > 0:
                time.sleep(sleep_time)
            else:
                next_tick = time.time() + UPLINK_TICK_INTERVAL

    uplink_thread = threading.Thread(target=_uplink_loop, name="uplink", daemon=True)
    uplink_thread.start()

    # Store stop events for shutdown
    bstate._solver_stop = solver_stop
    bstate._monitor_stop = monitor_stop
    bstate._uplink_stop = uplink_stop
    bstate._subscriber = subscriber
    bstate._ipc_client = ipc_client

    logger.info("=" * 60)
    logger.info("Backend B startup complete")
    logger.info("=" * 60)

    return (bstate, solver, monitor, ipc_client, solver_thread, monitor_thread, uplink_thread)


def shutdown(bstate, solver, monitor, ipc_client) -> None:
    """
    Gracefully shut down all Backend B components.

    Args:
        bstate: BState instance with stored stop events.
        solver: SolverComponent (unused, retained for API consistency).
        monitor: MonitorComponent (unused, retained for API consistency).
        ipc_client: IpcClient instance.
    """
    logger.info("=" * 60)
    logger.info("Backend B shutting down...")
    logger.info("=" * 60)

    # Stop background threads
    for attr_name in ("_solver_stop", "_monitor_stop", "_uplink_stop"):
        stop_event = getattr(bstate, attr_name, None)
        if stop_event is not None:
            stop_event.set()
            logger.info("Signalled stop for %s", attr_name)

    # Unregister ROS subscribers
    subscriber = getattr(bstate, "_subscriber", None)
    if subscriber is not None:
        try:
            subscriber.shutdown()
        except Exception as e:
            logger.warning("Error shutting down subscriber: %s", e)

    # Stop IPC client
    try:
        ipc_client.stop()
    except Exception as e:
        logger.warning("Error stopping IPC client: %s", e)

    logger.info("Backend B shutdown complete")


# ---- signal handler registration ----

_shutdown_requested = False
_cleanup_func = None


def _signal_handler(signum, frame):
    global _shutdown_requested
    logger.info("Received signal %d, initiating shutdown...", signum)
    _shutdown_requested = True


def register_signal_handlers(cleanup_func=None):
    """
    Register SIGINT and SIGTERM handlers for graceful shutdown.

    Args:
        cleanup_func: Callable to invoke when shutdown is requested.
    """
    global _cleanup_func
    _cleanup_func = cleanup_func

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
    logger.info("Signal handlers registered")

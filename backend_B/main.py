"""
Backend B entry point.

Usage:
    python -m backend_B.main
    python -m backend_B.main --stub                    # Run with hardcoded test
    python -m backend_B.main --socket /tmp/my_sock     # Custom socket path
    python -m backend_B.main --field config/field.yaml --constraints config/default_constraints.yaml

The main thread runs rospy.spin() (or a stub loop if --stub).
Background threads (solver, monitor, uplink, IPC) run concurrently.
"""

import sys
import time
import logging
import argparse
import threading
import os

# Configure logging early
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger("backend_b.main")


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Backend B - Real-time Flight Control Bridge",
    )
    parser.add_argument(
        "--stub", action="store_true",
        help="Run with a hardcoded test loop (no ROS required)",
    )
    parser.add_argument(
        "--socket", type=str, default="/tmp/flight_control_AB.sock",
        help="Unix socket path to Backend A (default: /tmp/flight_control_AB.sock)",
    )
    parser.add_argument(
        "--field", type=str, default="config/field.yaml",
        help="Path to field.yaml",
    )
    parser.add_argument(
        "--constraints", type=str, default="config/default_constraints.yaml",
        help="Path to default_constraints.yaml",
    )
    parser.add_argument(
        "--node-name", type=str, default="backend_b",
        help="ROS node name (default: backend_b)",
    )
    parser.add_argument(
        "--log-level", type=str, default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )
    return parser.parse_args()


def _stub_loop(bstate, solver):
    """
    Hardcoded test loop for running Backend B without ROS.

    Simulates drone pose updates and runs the solver/monitor loops
    in the main thread for testing/debugging.
    """
    logger.info("Running in STUB mode (no ROS)")

    # Simulate receiving a trajectory after 2 seconds
    stub_trajectory_sent = False

    while getattr(threading.current_thread(), "do_run", True):
        # Simulate a fake pose update
        from backend_B.state import PoseData
        bstate.current_pose = PoseData(x=1.0, y=0.5, z=1.0)

        # After 2 seconds, send a stub trajectory
        if not stub_trajectory_sent and time.time() - getattr(
            bstate, "_stub_start", time.time()
        ) > 2:
            logger.info("STUB: Injecting test trajectory")
            stub_spec = {
                "task_id": "stub-test-001",
                "segments": [
                    {
                        "from": {"x": 0.0, "y": 0.0, "z": 1.0, "yaw": 0.0},
                        "to": {"x": 3.0, "y": 2.0, "z": 1.5, "yaw": 0.5},
                    },
                    {
                        "from": {"x": 3.0, "y": 2.0, "z": 1.5, "yaw": 0.5},
                        "to": {"x": 4.0, "y": 3.5, "z": 1.0, "yaw": 0.0},
                    },
                ],
                "global_constraints": {},
            }
            result = solver.handle("trajectory", stub_spec, bstate)
            logger.info("STUB trajectory result: %s", result)
            stub_trajectory_sent = True

        time.sleep(0.1)


def main():
    args = _parse_args()

    # Set log level
    logging.getLogger().setLevel(getattr(logging, args.log_level))

    logger.info("Backend B starting (pid=%d)", os.getpid())
    logger.info("  socket: %s", args.socket)
    logger.info("  field: %s", args.field)
    logger.info("  constraints: %s", args.constraints)

    # Startup
    from backend_B.lifecycle import startup, shutdown, register_signal_handlers

    (bstate, solver, monitor, ipc_client,
     solver_thread, monitor_thread, uplink_thread) = startup(
        field_path=args.field,
        constraints_path=args.constraints,
        socket_path=args.socket,
        ros_node_name=args.node_name,
    )

    # Register signal handlers
    def _cleanup():
        shutdown(bstate, solver, monitor, ipc_client)
    register_signal_handlers(_cleanup)

    # Track start time for stub mode
    bstate._stub_start = time.time()

    try:
        if args.stub:
            _stub_loop(bstate, solver)
        else:
            # ROS main thread: spin until interrupted
            import rospy
            logger.info("Entering rospy.spin()...")
            rospy.spin()
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received")
    except Exception as exc:
        logger.exception("Fatal error in main loop: %s", exc)
        return 1
    finally:
        shutdown(bstate, solver, monitor, ipc_client)

    logger.info("Backend B exited normally")
    return 0


if __name__ == "__main__":
    sys.exit(main())

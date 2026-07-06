"""
Thread-safe shared state for Backend B.

All pose access is protected by a threading.Lock so that the ROS subscriber
callback, solver tick, monitor cycle, and IPC thread can read/write safely.
"""

import time
from dataclasses import dataclass, field
from threading import Lock


@dataclass
class PoseData:
    """Current drone pose estimate."""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    qw: float = 1.0
    qx: float = 0.0
    qy: float = 0.0
    qz: float = 0.0

    def as_position(self) -> list:
        """Return [x, y, z] as a plain list."""
        return [self.x, self.y, self.z]

    def as_list(self) -> list:
        """Return [x, y, z, qw, qx, qy, qz] as a plain list."""
        return [self.x, self.y, self.z, self.qw, self.qx, self.qy, self.qz]

    def update_from_pose_msg(self, msg) -> None:
        """Update from a ROS PoseStamped or Pose message."""
        self.x = msg.pose.position.x
        self.y = msg.pose.position.y
        self.z = msg.pose.position.z
        self.qw = msg.pose.orientation.w
        self.qx = msg.pose.orientation.x
        self.qy = msg.pose.orientation.y
        self.qz = msg.pose.orientation.z

    def update_from_dict(self, d: dict) -> None:
        """Update from a plain dict with x,y,z,qw,qx,qy,qz keys."""
        self.x = d.get("x", self.x)
        self.y = d.get("y", self.y)
        self.z = d.get("z", self.z)
        self.qw = d.get("qw", self.qw)
        self.qx = d.get("qx", self.qx)
        self.qy = d.get("qy", self.qy)
        self.qz = d.get("qz", self.qz)


@dataclass
class BState:
    """
    Central shared state for Backend B.

    Thread-safety: pose_lock protects _current_pose and last_data_ts.
    Other fields are set/read by a single thread or are atomic primitives.
    """
    pose_lock: Lock = field(default_factory=Lock)
    _current_pose: PoseData | None = None

    ipc_connected: bool = False
    solver_status: str = "idle"  # idle | executing | hovering | aborted
    current_trajectory: object | None = None
    current_segment_index: int = 0
    last_data_ts: float = 0.0

    # Loaded configuration (set during startup)
    field: object | None = None
    default_constraints: dict = field(default_factory=dict)

    # ----- pose property with lock -----

    @property
    def current_pose(self) -> PoseData | None:
        with self.pose_lock:
            return self._current_pose

    @current_pose.setter
    def current_pose(self, value: PoseData | None):
        with self.pose_lock:
            self._current_pose = value

    # ----- convenience methods -----

    def update_pose(self, msg) -> None:
        """Thread-safe pose update from a ROS message."""
        with self.pose_lock:
            if self._current_pose is None:
                self._current_pose = PoseData()
            self._current_pose.update_from_pose_msg(msg)
            self.last_data_ts = time.time()

    def has_pose(self) -> bool:
        """Return True if a valid pose estimate exists."""
        with self.pose_lock:
            return self._current_pose is not None

    def get_pose_list(self) -> list | None:
        """Return pose as [x,y,z,qw,qx,qy,qz] or None."""
        with self.pose_lock:
            if self._current_pose is None:
                return None
            return self._current_pose.as_list()

    def get_position(self) -> list | None:
        """Return [x, y, z] or None."""
        with self.pose_lock:
            if self._current_pose is None:
                return None
            return self._current_pose.as_position()

    def get_yaw(self) -> float | None:
        """Approximate yaw from quaternion (assumes small roll/pitch)."""
        with self.pose_lock:
            if self._current_pose is None:
                return None
            p = self._current_pose
            siny_cosp = 2.0 * (p.qw * p.qz + p.qx * p.qy)
            cosy_cosp = 1.0 - 2.0 * (p.qy * p.qy + p.qz * p.qz)
            import math
            return math.atan2(siny_cosp, cosy_cosp)

    def data_stale(self, max_age: float = 1.0) -> bool:
        """Return True if we haven't received data in max_age seconds."""
        with self.pose_lock:
            if self.last_data_ts == 0.0:
                return True
            return (time.time() - self.last_data_ts) > max_age

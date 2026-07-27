"""
SQLAlchemy ORM 模型 — 4 张表。
environments / flight_sessions / telemetry / conversations
"""
import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Text, DateTime, Index, UniqueConstraint, ForeignKey,
)
from sqlalchemy.orm import relationship
from db.session import Base


class Environment(Base):
    """环境条件 — JSON 灵活字段。"""
    __tablename__ = "environments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    data = Column(Text, nullable=False)  # JSON blob
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    sessions = relationship("FlightSession", back_populates="environment")


class FlightSession(Base):
    """试飞会话。"""
    __tablename__ = "flight_sessions"

    id = Column(String(20), primary_key=True)  # YYYYMMDDHHMMSS
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    environment_id = Column(Integer, ForeignKey("environments.id"), nullable=True)
    task_description = Column(Text, nullable=True)
    beta_plan = Column(Text, nullable=True)        # β 产出的自然语言计划
    alpha_actions = Column(Text, nullable=True)     # α 产出的 ActionCommand JSON
    status = Column(String(20), default="idle")

    environment = relationship("Environment", back_populates="sessions")
    telemetry_rows = relationship("Telemetry", back_populates="session")


class Telemetry(Base):
    """轨迹时序 — 高频。"""
    __tablename__ = "telemetry"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(20), ForeignKey("flight_sessions.id"), nullable=False)
    t = Column(Float, nullable=False)

    position_x = Column(Float, nullable=True)
    position_y = Column(Float, nullable=True)
    position_z = Column(Float, nullable=True)
    velocity_x = Column(Float, nullable=True)
    velocity_y = Column(Float, nullable=True)
    velocity_z = Column(Float, nullable=True)
    accel_x = Column(Float, nullable=True)
    accel_y = Column(Float, nullable=True)
    accel_z = Column(Float, nullable=True)
    angular_velocity_x = Column(Float, nullable=True)
    angular_velocity_y = Column(Float, nullable=True)
    angular_velocity_z = Column(Float, nullable=True)
    quat_w = Column(Float, nullable=True)
    quat_x = Column(Float, nullable=True)
    quat_y = Column(Float, nullable=True)
    quat_z = Column(Float, nullable=True)

    session = relationship("FlightSession", back_populates="telemetry_rows")

    __table_args__ = (
        UniqueConstraint("session_id", "t", name="uq_telemetry_session_t"),
        Index("idx_telemetry_session", "session_id"),
    )


class Conversation(Base):
    """对话记录。"""
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(20), ForeignKey("flight_sessions.id"), nullable=False)
    agent = Column(String(10), nullable=False)      # 'alpha' / 'beta'
    role = Column(String(20), nullable=False)        # 'human' / 'agent' / 'tool_call' / 'tool_result'
    content = Column(Text, nullable=False)
    metadata_json = Column("metadata", Text, nullable=True)  # JSON: {tool_name, tool_args, ...}
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    __table_args__ = (
        Index("idx_conv_session", "session_id"),
    )

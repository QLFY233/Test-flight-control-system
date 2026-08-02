"""
SQLAlchemy 引擎 + session factory。
"""
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import event

# 项目根目录 (backend-A/db/session.py → 上两级 = 项目根)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEFAULT_DB = os.path.join(_PROJECT_ROOT, "data", "flight_control.db")
DB_PATH = os.environ.get("FLIGHT_DB_PATH", _DEFAULT_DB)
DB_URL = f"sqlite+aiosqlite:///{DB_PATH}"


class Base(DeclarativeBase):
    pass


engine = create_async_engine(DB_URL, echo=False)

# N8: SQLite 默认不强制外键 — 每个新连接开启 PRAGMA foreign_keys,
# 避免 conversations/telemetry 产生孤儿行 (FK 悬空)
@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def create_all():
    """创建所有表 (启动时调用)。"""
    # 确保 data/ 目录存在
    db_dir = os.path.dirname(DB_PATH)
    if db_dir and not os.path.isdir(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    import db.models  # noqa: 确保模型导入
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

"""
SQLAlchemy 引擎 + session factory。
"""
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

# 项目根目录 (backend-A/db/session.py → 上两级 = 项目根)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEFAULT_DB = os.path.join(_PROJECT_ROOT, "data", "flight_control.db")
DB_PATH = os.environ.get("FLIGHT_DB_PATH", _DEFAULT_DB)
DB_URL = f"sqlite+aiosqlite:///{DB_PATH}"


class Base(DeclarativeBase):
    pass


engine = create_async_engine(DB_URL, echo=False)
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


async def get_session() -> AsyncSession:
    """获取 AsyncSession context manager。
    阶段 G/H: 作为 FastAPI Depends(get_session) 使用。
    """
    async with async_session() as session:
        yield session

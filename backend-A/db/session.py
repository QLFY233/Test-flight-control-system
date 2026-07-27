"""
SQLAlchemy 引擎 + session factory。
"""
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

DB_PATH = os.environ.get("FLIGHT_DB_PATH", "data/flight_control.db")
DB_URL = f"sqlite+aiosqlite:///{DB_PATH}"


class Base(DeclarativeBase):
    pass


engine = create_async_engine(DB_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def create_all():
    """创建所有表 (启动时调用)。"""
    import db.models  # noqa: 确保模型导入
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    """获取 AsyncSession context manager。"""
    async with async_session() as session:
        yield session

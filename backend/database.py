"""
数据库连接与会话管理 (V2 — 异步 PostgreSQL + Redis 缓存)

架构说明：
- AsyncPG 作为主库（高并发场景），提供异步 SQLAlchemy 引擎。
- 保留 SQLite 同步引擎作为开发/单机环境的 fallback。
- Redis 连接池用于捡漏雷达结果缓存（TTL 24h）。

环境变量：
  DATABASE_URL    — PostgreSQL 连接串 (默认 None，走 SQLite fallback)
  REDIS_URL       — Redis 连接串   (默认 redis://localhost:6379/0)
"""
import os
import asyncio
from typing import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker, declarative_base

import redis.asyncio as aioredis

# ── PostgreSQL (异步) ────────────────────────────────────────
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "",
)

_async_engine = None
_async_session_factory = None

if DATABASE_URL:
    # asyncpg 要求 URL 以 postgresql+asyncpg:// 开头
    if not DATABASE_URL.startswith("postgresql+asyncpg"):
        _pg_url = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1) \
                               .replace("postgres://", "postgresql+asyncpg://", 1)
    else:
        _pg_url = DATABASE_URL

    _async_engine = create_async_engine(
        _pg_url,
        echo=False,
        pool_size=20,           # 连接池大小
        max_overflow=10,        # 溢出连接数
        pool_pre_ping=True,     # 每次使用前检测连接有效性
    )
    _async_session_factory = async_sessionmaker(
        _async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 异步依赖注入：获取 PostgreSQL 异步会话。"""
    if _async_session_factory is None:
        raise RuntimeError("PostgreSQL 未配置，请设置 DATABASE_URL")
    async with _async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


# ── SQLite (同步 — fallback / 开发环境) ───────────────────────
SQLITE_URL = "sqlite:///./gaokao.db"

_sync_engine = create_engine(
    SQLITE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_sync_engine)

Base = declarative_base()


def get_db():
    """FastAPI 同步依赖注入：SQLite 会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Redis (异步连接池) ────────────────────────────────────────
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

_redis_pool: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis | None:
    """返回 Redis 客户端实例（若已连接）。"""
    return _redis_pool


async def init_redis():
    """应用启动时初始化 Redis 连接池。"""
    global _redis_pool
    try:
        _redis_pool = aioredis.from_url(
            REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=20,
        )
        # 验证连接
        await _redis_pool.ping()
        print(f"[Redis] 连接成功: {REDIS_URL}")
    except Exception as e:
        print(f"[Redis] 连接失败，缓存功能禁用: {e}")
        _redis_pool = None


async def close_redis():
    """应用关闭时清理 Redis 连接。"""
    if _redis_pool:
        await _redis_pool.close()
        print("[Redis] 连接已关闭")


# ── 工具函数 ────────────────────────────────────────────────────

def is_async_db_available() -> bool:
    """PostgreSQL 异步引擎是否可用。"""
    return _async_engine is not None


def is_redis_available() -> bool:
    """Redis 连接是否就绪。"""
    return _redis_pool is not None

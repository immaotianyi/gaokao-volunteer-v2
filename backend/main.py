"""
FastAPI 入口 (V3 — 异步 PostgreSQL + Redis + SSE)

启动方式:
  生产: uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
  开发: uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import pandas as pd

from database import Base, _sync_engine, init_redis, close_redis
from routers.profile import router as profile_router
from routers.leakage import router as leakage_router
from routers.risk import router as risk_router
from routers.risk_agent import router as risk_agent_router
from routers.payment import router as payment_router
from routers.admin import router as admin_router
from routers.advisor import router as advisor_router
from routers.score_rank import router as score_rank_router

# ── 加载 .env（python-dotenv 若不可用则手动解析） ──────────
_ENV_FILE = Path(__file__).parent.parent / ".env"
if _ENV_FILE.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_ENV_FILE)
    except ImportError:
        # 手动解析 .env
        with open(_ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    key, val = key.strip(), val.strip()
                    if key not in os.environ:
                        os.environ[key] = val

# ── 全局数据缓存 ─────────────────────────────────────────────
global_data: dict[str, pd.DataFrame] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：建表 + 预加载 CSV + 初始化 KB + 初始化 Redis。"""
    # SQLite 建表（同步）
    Base.metadata.create_all(bind=_sync_engine)

    # ── SQLite 已建表的轻量列补丁：为 user_profiles 补 6 个选科成绩列（任务 #8）──
    # 仅对 SQLite 做 ALTER TABLE，列已存在则忽略；不影响 PostgreSQL 部署
    try:
        from sqlalchemy import text
        _new_columns = [
            "physics_score", "chemistry_score", "biology_score",
            "history_score", "geography_score", "politics_score",
        ]
        with _sync_engine.connect() as conn:
            for col in _new_columns:
                try:
                    conn.execute(text(f"ALTER TABLE user_profiles ADD COLUMN {col} INTEGER"))
                except Exception:
                    # 列已存在或表不存在，忽略
                    pass
            conn.commit()
    except Exception as e:
        print(f"[MAIN] ⚠ user_profiles 列补丁跳过: {e}")

    # 预加载招生计划 CSV
    data_dir = Path(__file__).parent / "data"
    for name in ("plans_2025.csv", "plans_2026.csv"):
        filepath = data_dir / name
        if filepath.exists():
            global_data[name] = pd.read_csv(filepath)

    # 预加载历年录取数据（如果存在）
    history_file = data_dir / "admission_history.csv"
    if history_file.exists():
        global_data["admission_history.csv"] = pd.read_csv(history_file)
        print(f"[MAIN] 历年录取数据已加载 ({len(global_data['admission_history.csv'])} 行)")
    else:
        print(f"[MAIN] 历年录取数据未找到，估值模型将跳过")

    # ── V3.1: 初始化招生章程知识库 ──
    try:
        from services.enrollment_kb import get_knowledge_base
        kb = get_knowledge_base()
        print(f"[MAIN] 招生章程知识库已初始化")
    except Exception as e:
        print(f"[MAIN] ⚠ 知识库初始化失败 (不影响主流程): {e}")

    # ── V4: 预加载一分一段表 ──
    try:
        from services.score_rank import preload_all
        preload_all()
    except Exception as e:
        print(f"[MAIN] ⚠ 一分一段表加载失败 (不影响主流程): {e}")

    # 初始化 Redis
    await init_redis()

    yield

    global_data.clear()
    await close_redis()


app = FastAPI(
    title="高考志愿狙击手 API",
    description="志愿探雷器 + 捡漏雷达 后端服务 (V4 Agent)",
    version="0.4.0",
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 路由 ─────────────────────────────────────────────────────
app.include_router(profile_router)
app.include_router(leakage_router)
app.include_router(risk_router)         # V3 规则引擎
app.include_router(risk_agent_router)    # V4 AI Agent
app.include_router(advisor_router)       # AI 志愿顾问 (方案C)
app.include_router(payment_router)
app.include_router(admin_router)         # 管理后台（风险关键词+历史数据）
app.include_router(score_rank_router)    # 分数-位次映射


@app.get("/health", tags=["health"])
def health_check():
    cache_ok = True
    try:
        from database import is_redis_available
        cache_ok = is_redis_available()
    except Exception:
        cache_ok = False

    ocr_available = bool(os.getenv("BAIDU_OCR_API_KEY"))

    return {
        "status": "ok",
        "version": "0.5.0",
        "redis": "connected" if cache_ok else "unavailable",
        "agent": True,
    }


# ── 静态文件 (demo.html) —— 必须放在最后 ────────────────────
_PROJECT_ROOT = Path(__file__).parent.parent
_STATIC_DIR = _PROJECT_ROOT
if _STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static")

#!/usr/bin/env python3
"""
数据灌库脚本 — 将 CSV 数据批量导入 PostgreSQL (AdmissionPlan 表)

用法:
  python scripts/seed_db.py

环境变量:
  DATABASE_URL — PostgreSQL 连接串 (默认 postgresql://localhost:5432/gaokao)

"""
import asyncio
import os
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# 将 backend 目录加入 sys.path，以便导入 database 模块
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models import AdmissionPlan, RiskKeyword, AdmissionHistory

# ── 配置 ───────────────────────────────────────────────────────
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/gaokao",
)

if not DATABASE_URL.startswith("postgresql+asyncpg"):
    _pg_url = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1) \
                           .replace("postgres://", "postgresql+asyncpg://", 1)
else:
    _pg_url = DATABASE_URL

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

BATCH_SIZE = 200

# ── 默认风险关键词种子数据 ─────────────────────────────────────
DEFAULT_RISK_KEYWORDS = [
    {"keyword": "土木", "category": "土木建筑类", "risk_level": 1, "reason": "行业下行，就业前景不确定"},
    {"keyword": "农学", "category": "农学类", "risk_level": 1, "reason": "就业面窄，薪资偏低"},
    {"keyword": "护理", "category": "护理类", "risk_level": 2, "reason": "工作强度大，社会认可度偏低"},
    {"keyword": "生化", "category": "生化环材", "risk_level": 2, "reason": "四大天坑之一，就业竞争激烈"},
    {"keyword": "环境", "category": "生化环材", "risk_level": 2, "reason": "四大天坑之一，岗位少"},
    {"keyword": "材料", "category": "生化环材", "risk_level": 2, "reason": "四大天坑之一，需深造"},
    {"keyword": "矿业", "category": "矿业地质", "risk_level": 3, "reason": "高危行业，地理位置偏远"},
    {"keyword": "冶金", "category": "矿业地质", "risk_level": 3, "reason": "传统重工业，环境艰苦"},
    {"keyword": "哲学", "category": "哲学历史", "risk_level": 1, "reason": "就业面极窄"},
    {"keyword": "历史", "category": "哲学历史", "risk_level": 1, "reason": "就业对口率低"},
    {"keyword": "图书", "category": "图书档案", "risk_level": 1, "reason": "岗位稀缺"},
    {"keyword": "考古", "category": "哲学历史", "risk_level": 2, "reason": "岗位极度稀缺"},
]


def load_csv(filename: str) -> pd.DataFrame:
    filepath = DATA_DIR / filename
    if not filepath.exists():
        raise FileNotFoundError(f"CSV 文件不存在: {filepath}")
    return pd.read_csv(filepath)


async def seed_plans(engine):
    """灌入招生计划数据"""
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    df_2025 = load_csv("plans_2025.csv")
    df_2026 = load_csv("plans_2026.csv")

    # 添加年份列
    if "year" not in df_2025.columns:
        df_2025["year"] = 2025
    if "year" not in df_2026.columns:
        df_2026["year"] = 2026

    df_all = pd.concat([df_2025, df_2026], ignore_index=True)

    # 填充缺失字段
    for col in ("tuition", "lowest_score_2025", "lowest_rank_2025"):
        if col not in df_all.columns:
            df_all[col] = None
    for col in ("batch", "school_type", "major_category"):
        if col not in df_all.columns:
            df_all[col] = None
    if "is_new" not in df_all.columns:
        df_all["is_new"] = False

    records = df_all.to_dict(orient="records")
    total = len(records)
    print(f"[seed] 共 {total} 条招生计划记录待导入")

    async with async_session() as session:
        await session.execute(text(f"DELETE FROM {AdmissionPlan.__tablename__}"))
        await session.commit()
        print(f"[seed] 已清空表: {AdmissionPlan.__tablename__}")

        for i in range(0, total, BATCH_SIZE):
            batch = records[i:i + BATCH_SIZE]
            for row in batch:
                session.add(AdmissionPlan(
                    year=int(row["year"]),
                    province=str(row.get("province", "")),
                    subject_group=str(row.get("subject_group", "")),
                    batch=str(row.get("batch", "")) if pd.notna(row.get("batch")) else None,
                    university_code=str(row.get("university_code", "")),
                    university_name=str(row.get("university_name", "")),
                    group_code=str(row.get("group_code", "")),
                    major_code=str(row.get("major_code", "")),
                    major_name=str(row.get("major_name", "")),
                    plan_count=int(row.get("plan_count", 0)),
                    tuition=row.get("tuition") if pd.notna(row.get("tuition")) else None,
                    lowest_score_2025=row.get("lowest_score_2025") if pd.notna(row.get("lowest_score_2025")) else None,
                    lowest_rank_2025=row.get("lowest_rank_2025") if pd.notna(row.get("lowest_rank_2025")) else None,
                    is_new=bool(row.get("is_new", False)),
                    school_type=str(row.get("school_type", "")) if pd.notna(row.get("school_type")) else None,
                    major_category=str(row.get("major_category", "")) if pd.notna(row.get("major_category")) else None,
                ))
            await session.commit()
            progress = min(i + BATCH_SIZE, total)
            print(f"[seed] 进度: {progress}/{total} ({progress * 100 // total}%)")

    print(f"[seed] ✅ 招生计划灌库完成！共导入 {total} 条记录")


async def seed_risk_keywords(engine):
    """灌入默认风险关键词"""
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # 先检查是否已有数据
        from sqlalchemy import select
        result = await session.execute(select(RiskKeyword).limit(1))
        if result.scalar_one_or_none():
            print("[seed] 风险关键词表已有数据，跳过种子数据灌入")
            return

        for kw in DEFAULT_RISK_KEYWORDS:
            session.add(RiskKeyword(
                keyword=kw["keyword"],
                category=kw["category"],
                risk_level=kw["risk_level"],
                reason=kw["reason"],
                is_active=True,
            ))
        await session.commit()
    print(f"[seed] ✅ 风险关键词灌库完成！共导入 {len(DEFAULT_RISK_KEYWORDS)} 条记录")


async def run_verification(engine):
    """执行验证 SQL"""
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    print("\n" + "=" * 60)
    print("数据验证")
    print("=" * 60)

    async with async_session() as session:
        # 各省份-科类数据量检查
        result = await session.execute(text("""
            SELECT province, subject_group, COUNT(*) as cnt
            FROM admission_plans
            GROUP BY province, subject_group
            ORDER BY cnt DESC
        """))
        print("\n📊 各省份-科类数据量:")
        for row in result:
            print(f"  {row[0]} / {row[1]}: {row[2]} 条")

        # 计划数为 0 的异常记录检查
        result = await session.execute(text("""
            SELECT COUNT(*) FROM admission_plans WHERE plan_count <= 0
        """))
        zero_count = result.scalar()
        print(f"\n📊 计划数≤0 的异常记录: {zero_count} 条")

        # 缺失历史数据的记录占比
        result = await session.execute(text("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN lowest_score_2025 IS NULL THEN 1 ELSE 0 END) as missing_score,
                SUM(CASE WHEN lowest_rank_2025 IS NULL THEN 1 ELSE 0 END) as missing_rank
            FROM admission_plans
        """))
        row = result.fetchone()
        total, missing_score, missing_rank = row
        print(f"\n📊 缺失历史数据记录:")
        print(f"  总计: {total}")
        print(f"  缺失最低分: {missing_score} ({missing_score/total*100:.1f}%)")
        print(f"  缺失最低位次: {missing_rank} ({missing_rank/total*100:.1f}%)")

        # 批次分布
        result = await session.execute(text("""
            SELECT batch, COUNT(*) as cnt
            FROM admission_plans
            GROUP BY batch
            ORDER BY cnt DESC
        """))
        print(f"\n📊 批次分布:")
        for row in result:
            print(f"  {row[0] or 'NULL'}: {row[1]} 条")

        # 学校类型分布
        result = await session.execute(text("""
            SELECT school_type, COUNT(DISTINCT university_name) as uni_cnt, COUNT(*) as record_cnt
            FROM admission_plans
            WHERE school_type IS NOT NULL
            GROUP BY school_type
            ORDER BY uni_cnt DESC
        """))
        print(f"\n📊 学校类型分布:")
        for row in result:
            print(f"  {row[0]}: {row[1]} 所大学, {row[2]} 条记录")


async def seed(engine):
    """主灌库逻辑"""
    await seed_plans(engine)
    await seed_risk_keywords(engine)
    await run_verification(engine)


async def main():
    engine = create_async_engine(
        _pg_url,
        echo=False,
        pool_size=5,
        max_overflow=5,
    )
    try:
        await seed(engine)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

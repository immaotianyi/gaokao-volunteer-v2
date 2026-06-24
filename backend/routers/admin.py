"""
管理员路由 — 风险关键词字典 CRUD + 历史数据管理

需要简单的 admin key 鉴权。

- GET    /api/admin/risk-keywords       列出所有风险关键词
- POST   /api/admin/risk-keywords       新增风险关键词
- PUT    /api/admin/risk-keywords/{id}   更新风险关键词
- DELETE /api/admin/risk-keywords/{id}   删除(软删除)风险关键词
- POST   /api/admin/admission-history    批量导入历史录取数据
- GET    /api/admin/admission-history    查询历史录取数据
"""
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from models import RiskKeyword, AdmissionHistory
from schemas import (
    RiskKeywordCreate,
    RiskKeywordResponse,
    AdmissionHistoryBase,
    AdmissionHistoryResponse,
    MessageResponse,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])

# 简单的 admin key 鉴权（从环境变量或默认值读取）
ADMIN_KEY = os.getenv("ADMIN_KEY", "gaokao-admin-2026")


async def verify_admin(x_admin_key: str = Header(None)):
    """验证 admin key"""
    if x_admin_key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="无效的管理员密钥")
    return True


# ── RiskKeyword CRUD ─────────────────────────────────────────

@router.get("/risk-keywords", response_model=list[RiskKeywordResponse])
async def list_risk_keywords(
    category: Optional[str] = None,
    is_active: Optional[bool] = None,
    _: bool = Depends(verify_admin),
):
    """列出所有风险关键词，支持按分类和启用状态过滤"""
    from database import get_async_session

    async for session in get_async_session():
        stmt = select(RiskKeyword)
        if category:
            stmt = stmt.where(RiskKeyword.category == category)
        if is_active is not None:
            stmt = stmt.where(RiskKeyword.is_active == is_active)
        stmt = stmt.order_by(RiskKeyword.risk_level.desc(), RiskKeyword.keyword)
        result = await session.execute(stmt)
        keywords = result.scalars().all()
        return [RiskKeywordResponse.model_validate(k) for k in keywords]

    return []


@router.post("/risk-keywords", response_model=RiskKeywordResponse, status_code=201)
async def create_risk_keyword(
    payload: RiskKeywordCreate,
    _: bool = Depends(verify_admin),
):
    """新增风险关键词"""
    from database import get_async_session

    async for session in get_async_session():
        # 检查是否已存在
        stmt = select(RiskKeyword).where(RiskKeyword.keyword == payload.keyword)
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"关键词 '{payload.keyword}' 已存在",
            )

        kw = RiskKeyword(
            keyword=payload.keyword,
            category=payload.category,
            risk_level=payload.risk_level,
            reason=payload.reason,
            is_active=True,
        )
        session.add(kw)
        await session.commit()
        await session.refresh(kw)
        return RiskKeywordResponse.model_validate(kw)

    raise HTTPException(status_code=500, detail="数据库连接失败")


@router.put("/risk-keywords/{kw_id}", response_model=RiskKeywordResponse)
async def update_risk_keyword(
    kw_id: int,
    payload: RiskKeywordCreate,
    _: bool = Depends(verify_admin),
):
    """更新风险关键词"""
    from database import get_async_session

    async for session in get_async_session():
        stmt = select(RiskKeyword).where(RiskKeyword.id == kw_id)
        result = await session.execute(stmt)
        kw = result.scalar_one_or_none()
        if not kw:
            raise HTTPException(status_code=404, detail="关键词不存在")

        kw.keyword = payload.keyword
        kw.category = payload.category
        kw.risk_level = payload.risk_level
        kw.reason = payload.reason

        await session.commit()
        await session.refresh(kw)
        return RiskKeywordResponse.model_validate(kw)

    raise HTTPException(status_code=500, detail="数据库连接失败")


@router.delete("/risk-keywords/{kw_id}", response_model=MessageResponse)
async def delete_risk_keyword(
    kw_id: int,
    _: bool = Depends(verify_admin),
):
    """软删除风险关键词（设置 is_active=False）"""
    from database import get_async_session

    async for session in get_async_session():
        stmt = select(RiskKeyword).where(RiskKeyword.id == kw_id)
        result = await session.execute(stmt)
        kw = result.scalar_one_or_none()
        if not kw:
            raise HTTPException(status_code=404, detail="关键词不存在")

        kw.is_active = False
        await session.commit()
        return MessageResponse(message=f"关键词 '{kw.keyword}' 已停用")

    raise HTTPException(status_code=500, detail="数据库连接失败")


# ── AdmissionHistory CRUD ────────────────────────────────────

@router.get("/admission-history", response_model=list[AdmissionHistoryResponse])
async def list_admission_history(
    year: Optional[int] = None,
    province: Optional[str] = None,
    university_name: Optional[str] = None,
    _: bool = Depends(verify_admin),
):
    """查询历史录取数据，支持按年份/省份/大学过滤"""
    from database import get_async_session

    async for session in get_async_session():
        stmt = select(AdmissionHistory)
        if year:
            stmt = stmt.where(AdmissionHistory.year == year)
        if province:
            stmt = stmt.where(AdmissionHistory.province == province)
        if university_name:
            stmt = stmt.where(AdmissionHistory.university_name == university_name)
        stmt = stmt.order_by(AdmissionHistory.year.desc(), AdmissionHistory.university_name)
        stmt = stmt.limit(1000)
        result = await session.execute(stmt)
        records = result.scalars().all()
        return [AdmissionHistoryResponse.model_validate(r) for r in records]

    return []


@router.post("/admission-history", response_model=MessageResponse, status_code=201)
async def import_admission_history(
    records: list[AdmissionHistoryBase],
    _: bool = Depends(verify_admin),
):
    """批量导入历史录取数据"""
    from database import get_async_session

    async for session in get_async_session():
        imported = 0
        skipped = 0
        for rec in records:
            history = AdmissionHistory(
                year=rec.year,
                province=rec.province,
                subject_group=rec.subject_group,
                university_code=rec.university_code,
                university_name=rec.university_name,
                group_code=rec.group_code,
                major_code=rec.major_code,
                major_name=rec.major_name,
                lowest_score=rec.lowest_score,
                lowest_rank=rec.lowest_rank,
                avg_score=rec.avg_score,
                applicant_count=rec.applicant_count,
            )
            try:
                session.add(history)
                imported += 1
            except Exception:
                skipped += 1
                continue

        await session.commit()
        return MessageResponse(
            message=f"导入完成: {imported} 条成功, {skipped} 条跳过"
        )

    raise HTTPException(status_code=500, detail="数据库连接失败")

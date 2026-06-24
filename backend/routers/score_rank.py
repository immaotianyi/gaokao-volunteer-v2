"""
分数-位次映射 API 路由

接口：
- GET  /api/score-rank/convert   分数→位次 转换
- POST /api/score-rank/convert   分数→位次 转换（支持更多参数）
- GET  /api/score-rank/range     获取分数区间位次
- GET  /api/score-rank/years     获取可用年份列表
"""

from fastapi import APIRouter, Query, HTTPException
from services.score_rank import (
    score_to_rank,
    rank_to_score,
    get_score_range,
    get_available_years,
)
from schemas import ScoreRankRequest, ScoreRankResponse, ScoreRangeResponse

router = APIRouter(prefix="/api/score-rank", tags=["score-rank"])


@router.get("/convert", response_model=ScoreRankResponse)
async def convert_score_to_rank_get(
    score: int = Query(..., ge=0, le=750, description="高考分数"),
    subject_group: str = Query("物理类", description="科类（物理类/历史类）"),
    year: int = Query(2025, description="年份"),
):
    """GET 方式：分数 → 位次 转换"""
    return _do_convert(score, subject_group, year)


@router.post("/convert", response_model=ScoreRankResponse)
async def convert_score_to_rank_post(payload: ScoreRankRequest):
    """POST 方式：分数 → 位次 转换"""
    return _do_convert(payload.score, payload.subject_group, payload.year)


def _do_convert(score: int, subject_group: str, year: int) -> ScoreRankResponse:
    try:
        rank = score_to_rank(score, year, subject_group)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return ScoreRankResponse(
        score=score,
        rank=rank,
        subject_group=subject_group,
        year=year,
        province="广东",
    )


@router.get("/range", response_model=ScoreRangeResponse)
async def get_rank_range(
    score: int = Query(..., ge=0, le=750, description="高考分数"),
    subject_group: str = Query("物理类", description="科类"),
    tolerance: int = Query(5, ge=1, le=50, description="分数容差"),
    year: int = Query(2025, description="年份"),
):
    """获取分数对应的位次区间"""
    try:
        data = get_score_range(score, tolerance, year, subject_group)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return ScoreRangeResponse(
        score=data["score"],
        rank=data["rank"],
        min_score=data["min_score"],
        max_score=data["max_score"],
        min_rank=data["min_rank"],
        max_rank=data["max_rank"],
        tolerance=data["tolerance"],
        subject_group=subject_group,
        year=year,
        province="广东",
    )


@router.get("/reverse")
async def reverse_lookup(
    rank: int = Query(..., ge=1, description="全省排位"),
    subject_group: str = Query("物理类", description="科类"),
    year: int = Query(2025, description="年份"),
):
    """位次 → 分数 反查"""
    try:
        score = rank_to_score(rank, year, subject_group)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return ScoreRankResponse(
        score=score,
        rank=rank,
        subject_group=subject_group,
        year=year,
        province="广东",
    )


@router.get("/years")
async def list_years():
    """获取可用的一分一段表年份"""
    return {"years": get_available_years(), "default": 2025}

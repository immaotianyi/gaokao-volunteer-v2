"""

Pydantic 请求/响应模型定义

"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# ── UserProfile ──────────────────────────────────────────────

class UserProfileBase(BaseModel):
    province: str = Field(..., min_length=2, max_length=20, description="省份")
    score: int = Field(..., ge=0, le=750, description="高考总分")
    rank: Optional[int] = Field(None, ge=0, description="全省位次")
    subjects: Optional[str] = Field(None, max_length=20, description="选科组合")
    english_score: Optional[int] = Field(None, ge=0, le=150, description="英语单科成绩")
    math_score: Optional[int] = Field(None, ge=0, le=150, description="数学单科成绩")
    chinese_score: Optional[int] = Field(None, ge=0, le=150, description="语文单科成绩")
    vision_status: str = Field("正常", description="视力状况")


class UserProfileCreate(UserProfileBase):
    """创建/更新用户档案的请求体"""
    user_id: str = Field(..., min_length=1, max_length=50, description="用户唯一标识")


class UserProfileResponse(UserProfileBase):
    """返回给前端的用户档案"""
    user_id: str
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── AdmissionPlan ────────────────────────────────────────────

class AdmissionPlanBase(BaseModel):
    year: int = Field(..., ge=2000, le=2100)
    province: str = Field(..., min_length=2, max_length=20)
    subject_group: str = Field(..., max_length=20, description="科类")
    batch: Optional[str] = Field("本科批", max_length=20, description="批次")
    university_code: str = Field(..., max_length=10)
    university_name: str = Field(..., max_length=50)
    group_code: str = Field(..., max_length=10)
    major_code: str = Field(..., max_length=10)
    major_name: str = Field(..., max_length=100)
    plan_count: int = Field(0, ge=0)


class AdmissionPlanResponse(AdmissionPlanBase):
    id: int
    tuition: Optional[int] = None
    lowest_score_2025: Optional[int] = None
    lowest_rank_2025: Optional[int] = None
    is_new: bool = False
    school_type: Optional[str] = None
    major_category: Optional[str] = None

    model_config = {"from_attributes": True}


# ── RiskKeyword ──────────────────────────────────────────────

class RiskKeywordBase(BaseModel):
    keyword: str = Field(..., min_length=1, max_length=50, description="风险关键词")
    category: str = Field(..., max_length=30, description="大类")
    risk_level: int = Field(1, ge=1, le=3, description="1=低偏好, 2=中风险, 3=高风险")
    reason: Optional[str] = Field(None, max_length=200, description="风险说明")


class RiskKeywordCreate(RiskKeywordBase):
    pass


class RiskKeywordResponse(RiskKeywordBase):
    id: int
    is_active: bool = True

    model_config = {"from_attributes": True}


# ── AdmissionHistory ─────────────────────────────────────────

class AdmissionHistoryBase(BaseModel):
    year: int = Field(..., ge=2000, le=2100)
    province: str = Field(..., min_length=2, max_length=20)
    subject_group: str = Field(..., max_length=20)
    university_code: str = Field(..., max_length=10)
    university_name: str = Field(..., max_length=50)
    group_code: str = Field(..., max_length=10)
    major_code: str = Field(..., max_length=10)
    major_name: str = Field(..., max_length=100)
    lowest_score: Optional[int] = None
    lowest_rank: Optional[int] = None
    avg_score: Optional[int] = None
    applicant_count: Optional[int] = None


class AdmissionHistoryResponse(AdmissionHistoryBase):
    id: int

    model_config = {"from_attributes": True}


# ── 通用响应 ─────────────────────────────────────────────────

class MessageResponse(BaseModel):
    message: str


# ── 捡漏雷达 ─────────────────────────────────────────────────

class LeakageRadarRequest(BaseModel):
    province: str = Field(..., min_length=2, max_length=20, description="省份")
    subject_group: str = Field(..., max_length=20, description="科类（物理类/历史类）")
    batch: Optional[str] = Field(None, description="批次过滤: 本科批/专科批/提前批")
    school_types: Optional[list[str]] = Field(None, description="院校类型过滤: 985/211/双一流/省属重点/普通本科/民办")
    min_score: Optional[int] = Field(None, ge=0, le=750, description="最低分数过滤")
    max_score: Optional[int] = Field(None, ge=0, le=750, description="最高分数过滤")
    user_score: Optional[int] = Field(None, ge=0, le=750, description="用户高考分数（用于估分匹配）")
    user_subjects_detail: Optional[str] = Field(None, max_length=20, description="用户具体选科（用于稀缺度计算）")
    score_tolerance: int = Field(30, ge=5, le=100, description="分数容差（默认 ±30 分）")


class LeakageOpportunity(BaseModel):
    university_name: str
    major_name: str
    group_code: str
    plan_count: int
    opportunity_type: str = Field(..., description="新增专业 / 扩招专业 / 中外合作 / 新校区 / 首招批次")
    reason: str
    leakage_score: Optional[int] = Field(None, description="捡漏评分 0-100")
    score_breakdown: Optional[list[str]] = Field(None, description="评分明细")
    lowest_score_2025: Optional[int] = None
    lowest_rank_2025: Optional[int] = None
    school_type: Optional[str] = None
    batch: Optional[str] = None
    # V2 新增字段
    estimated_score: Optional[int] = Field(None, description="预估分数线")
    confidence_range: Optional[list[int]] = Field(None, description="置信区间 [low, high]")
    estimation_source: Optional[str] = Field(None, description="估值来源（同校同类专业/同层次院校）")
    is_sino_foreign: bool = Field(False, description="是否中外合作")
    is_high_tuition: bool = Field(False, description="是否高收费（>2.5万/年）")
    is_new_campus: bool = Field(False, description="是否新校区首次招生")
    is_first_batch: bool = Field(False, description="是否首次在本科批招生")
    subject_scarcity: Optional[float] = Field(None, description="选科稀缺度（0-1）")
    group_size: Optional[int] = Field(None, description="专业组内专业数")
    tuition: Optional[int] = Field(None, description="学费")
    plan_count_prev: Optional[int] = Field(None, description="上年计划数")
    # V3 新增：Tavily 动态信息层
    live_latest_score: Optional[str] = Field(None, description="[联网]最新分数线信息")
    live_employment: Optional[str] = Field(None, description="[联网]就业前景信息")
    live_news: Optional[str] = Field(None, description="[联网]相关新闻")
    live_sources: Optional[list[str]] = Field(None, description="[联网]来源URL列表")
    # V4 新增：雪峰知识库维度（方案B）
    data_trust_level: Optional[str] = Field(None, description="数据可信度分级 T1-T4")
    data_trust_desc: Optional[str] = Field(None, description="数据可信度说明")


class LeakageRadarResponse(BaseModel):
    province: str
    subject_group: str
    total: int
    opportunities: list[LeakageOpportunity]
    # V2 新增字段
    last_updated: Optional[str] = Field(None, description="数据最后更新时间")
    new_since_yesterday: int = Field(0, description="自昨天以来新增的捡漏机会数")
    top_pick: Optional[LeakageOpportunity] = Field(None, description="评分最高的机会")


# ── 志愿探雷器 ─────────────────────────────────────────────────

class RiskTarget(BaseModel):
    """单个审查目标：大学-专业组合"""
    university: str = Field(..., min_length=1, max_length=50, description="大学名称")
    major: str = Field(..., min_length=1, max_length=100, description="专业名称")


class CheckRiskRequest(BaseModel):
    """志愿探雷审查请求"""
    profile: UserProfileBase = Field(..., description="考生档案")
    targets: list[RiskTarget] = Field(..., min_length=1, max_length=50, description="待审查的志愿列表")


class RiskCheckItem(RiskTarget):
    """单个审查结果"""
    status: str = Field(..., description="PASS | WARNING | DANGER | UNKNOWN")
    reason: str
    matched_clause: str = ""


class CheckRiskResponse(BaseModel):
    total: int
    results: list[RiskCheckItem]


# ── AI 顾问 (方案C) ────────────────────────────────────────────

class ChatMessage(BaseModel):
    """单条聊天消息"""
    role: str = Field(..., description="user | assistant")
    content: str = Field(..., min_length=1, max_length=2000)


class AdvisorRequest(BaseModel):
    """AI 顾问聊天请求"""
    message: str = Field(..., min_length=1, max_length=2000, description="用户提问")
    history: list[ChatMessage] = Field(default_factory=list, description="对话历史（多轮记忆）")
    profile: Optional[UserProfileBase] = Field(None, description="考生档案（可选，提供后回答更精准）")


class AdvisorResponse(BaseModel):
    """AI 顾问聊天响应"""
    reply: str = Field(..., description="顾问回复")
    sources: Optional[list[str]] = Field(None, description="引用的数据来源")
    data_trust_level: Optional[str] = Field(None, description="数据可信度 T1-T4")
    suggestions: Optional[list[str]] = Field(None, description="后续可追问的建议问题")


# ── 分数-位次映射 ─────────────────────────────────────────────────

class ScoreRankRequest(BaseModel):
    """分数→位次转换请求"""
    score: int = Field(..., ge=0, le=750, description="高考分数")
    subject_group: str = Field("物理类", description="科类（物理类/历史类）")
    year: int = Field(2025, ge=2020, le=2026, description="年份")


class ScoreRankResponse(BaseModel):
    """分数→位次转换响应"""
    score: int
    rank: int = Field(..., description="全省累计人数（位次）")
    subject_group: str
    year: int
    province: str = "广东"


class ScoreRangeResponse(BaseModel):
    """分数区间位次响应"""
    score: int
    rank: int
    min_score: int
    max_score: int
    min_rank: int
    max_rank: int
    tolerance: int
    subject_group: str
    year: int
    province: str = "广东"

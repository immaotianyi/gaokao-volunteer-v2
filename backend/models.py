"""

数据库 ORM 模型定义

"""
from sqlalchemy import Column, Integer, String, Boolean, Index, DateTime, Text, func
from database import Base


class UserProfile(Base):
    """用户档案表 - 存储考生基本信息和自身条件"""
    __tablename__ = "user_profiles"

    user_id = Column(String(50), primary_key=True)
    province = Column(String(20), nullable=False)
    score = Column(Integer, nullable=False)
    rank = Column(Integer, nullable=True)
    subjects = Column(String(20), nullable=True)
    english_score = Column(Integer, nullable=True)
    math_score = Column(Integer, nullable=True)
    chinese_score = Column(Integer, nullable=True)
    vision_status = Column(String(20), default="正常")

    def __repr__(self):
        return f"<UserProfile(user_id={self.user_id}, province={self.province}, score={self.score})>"


class AdmissionPlan(Base):
    """招生计划表 - 存储某年度某省的招生专业/计划数据"""
    __tablename__ = "admission_plans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    year = Column(Integer, nullable=False, index=True)
    province = Column(String(20), nullable=False)
    subject_group = Column(String(20), nullable=False)
    batch = Column(String(20), nullable=True, default="本科批")
    university_code = Column(String(10), nullable=False)
    university_name = Column(String(50), nullable=False)
    group_code = Column(String(10), nullable=False)
    major_code = Column(String(10), nullable=False)
    major_name = Column(String(100), nullable=False)
    plan_count = Column(Integer, default=0)
    tuition = Column(Integer, nullable=True)
    lowest_score_2025 = Column(Integer, nullable=True)
    lowest_rank_2025 = Column(Integer, nullable=True)
    is_new = Column(Boolean, default=False)
    school_type = Column(String(20), nullable=True)
    major_category = Column(String(20), nullable=True)

    def __repr__(self):
        return f"<AdmissionPlan({self.year} {self.university_name} {self.major_name})>"


class RiskKeyword(Base):
    """风险关键词字典表 - 可动态配置低偏好/高风险专业标签"""
    __tablename__ = "risk_keywords"

    id = Column(Integer, primary_key=True, autoincrement=True)
    keyword = Column(String(50), nullable=False, unique=True)
    category = Column(String(30), nullable=False)
    risk_level = Column(Integer, default=1)  # 1=低偏好, 2=中风险, 3=高风险
    reason = Column(String(200))
    is_active = Column(Boolean, default=True)

    def __repr__(self):
        return f"<RiskKeyword(keyword={self.keyword}, level={self.risk_level})>"


class AdmissionHistory(Base):
    """历史录取数据表 - 按年份、省份、大学、专业存储历年录取最低分/位次"""
    __tablename__ = "admission_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    year = Column(Integer, nullable=False, index=True)
    province = Column(String(20), nullable=False)
    subject_group = Column(String(20), nullable=False)
    university_code = Column(String(10), nullable=False)
    university_name = Column(String(50), nullable=False)
    group_code = Column(String(10), nullable=False)
    major_code = Column(String(10), nullable=False)
    major_name = Column(String(100), nullable=False)
    lowest_score = Column(Integer)
    lowest_rank = Column(Integer)
    avg_score = Column(Integer)
    applicant_count = Column(Integer)

    __table_args__ = (
        Index('idx_year_province_group_major',
              'year', 'province', 'university_code', 'group_code', 'major_code',
              unique=True),
    )

    def __repr__(self):
        return f"<AdmissionHistory({self.year} {self.university_name} {self.major_name})>"


class Order(Base):
    """支付订单表 — 持久化订单状态（替代内存 dict）"""
    __tablename__ = "orders"

    order_id = Column(String(64), primary_key=True)           # 商户订单号 out_trade_no
    user_id = Column(String(50), nullable=False, index=True)
    amount = Column(Integer, nullable=False)                   # 单位：分
    status = Column(String(20), default="PENDING", nullable=False)  # PENDING | SUCCESS | CLOSED | REFUND
    mode = Column(String(10), default="mock", nullable=False)  # mock | real
    # 微信支付返回的交易单号（真实模式回调才有）
    transaction_id = Column(String(64), nullable=True)
    # Native 下单返回的二维码链接（真实模式）
    code_url = Column(String(255), nullable=True)
    # 前端展示用的二维码图片 URL（模拟模式）
    qrcode_url = Column(String(512), nullable=True)
    poll_count = Column(Integer, default=0)
    # 支付成功时间
    paid_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self):
        return f"<Order({self.order_id} {self.status} {self.mode})>"


class UserUnlock(Base):
    """用户解锁记录表 — 支付成功后标记用户已解锁雷达（持久化，替代内存 set）"""
    __tablename__ = "user_unlocks"

    user_id = Column(String(50), primary_key=True)
    order_id = Column(String(64), nullable=False, index=True)
    unlocked_at = Column(DateTime, server_default=func.now(), nullable=False)
    # 解锁有效期（天数），默认 30 天
    expire_days = Column(Integer, default=30, nullable=False)

    def __repr__(self):
        return f"<UserUnlock({self.user_id} order={self.order_id})>"

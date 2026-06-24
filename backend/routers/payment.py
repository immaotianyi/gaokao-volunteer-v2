"""
支付路由 — 微信 Native 支付 V3 + 模拟回退 + 雷达解锁

接口:
  POST /api/pay/qrcode                生成支付二维码订单（真实/模拟自动切换）
  GET  /api/pay/status/{order_id}     轮询支付状态
  POST /api/pay/notify                微信支付回调通知（验签+解密+解锁）
  POST /api/pay/unlock-radar          支付成功后手动确认解锁（兜底）
  GET  /api/pay/radar-status/{user_id} 查询用户雷达解锁状态
  GET  /api/pay/mode                  查询当前支付模式（real/mock）

模式说明:
  - 真实模式: 配置齐全的 WECHAT_* 环境变量后，调用微信支付 V3 Native API
  - 模拟模式: 无凭证时自动降级，第3次轮询自动 SUCCESS（开发/演示用）
"""
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, update

from database import SessionLocal
from models import Order, UserUnlock
from services import wechat_pay

router = APIRouter(prefix="/api/pay", tags=["payment"])

# ── 时区（东八区） ──
_TZ_CN = timezone(timedelta(hours=8))

# ── 内存兜底（SQLite 不可用时降级用，仅模拟模式） ──
_orders_mem: dict[str, dict] = {}
_unlocked_mem: set[str] = set()


# ── 请求/响应模型 ─────────────────────────────────────────────
class QrcodeRequest(BaseModel):
    user_id: str = "anonymous"


class QrcodeResponse(BaseModel):
    order_id: str
    qrcode_url: str
    code_url: Optional[str] = None   # 真实模式的 weixin:// 链接
    amount: int                      # 单位：分
    mode: str                        # real | mock


class PaymentStatus(BaseModel):
    order_id: str
    status: str       # PENDING | SUCCESS | CLOSED | REFUND
    poll_count: int
    mode: str


class UnlockRadarRequest(BaseModel):
    user_id: str
    order_id: str


class RadarStatusResponse(BaseModel):
    user_id: str
    unlocked: bool
    expire_days: Optional[int] = None


# ── 工具函数 ─────────────────────────────────────────────────
def _now() -> datetime:
    return datetime.now(_TZ_CN)


def _is_real_mode() -> bool:
    return wechat_pay.is_configured()


def _save_order(order: Order):
    """持久化订单到 SQLite（失败则降级到内存）。"""
    try:
        with SessionLocal() as db:
            db.add(order)
            db.commit()
    except Exception as e:
        print(f"[PAY] 订单持久化失败，降级内存: {e}")
        _orders_mem[order.order_id] = {
            "user_id": order.user_id,
            "amount": order.amount,
            "poll_count": order.poll_count,
            "status": order.status,
            "mode": order.mode,
            "code_url": order.code_url,
            "qrcode_url": order.qrcode_url,
            "created_at": time.time(),
        }


def _get_order(order_id: str) -> Optional[Order]:
    """从 SQLite 读取订单，失败则查内存。"""
    try:
        with SessionLocal() as db:
            o = db.get(Order, order_id)
            return o
    except Exception:
        pass
    data = _orders_mem.get(order_id)
    if not data:
        return None
    # 内存兜底构造伪 Order 对象
    o = Order(
        order_id=order_id,
        user_id=data["user_id"],
        amount=data["amount"],
        status=data["status"],
        mode=data["mode"],
        code_url=data.get("code_url"),
        qrcode_url=data.get("qrcode_url"),
        poll_count=data.get("poll_count", 0),
    )
    return o


def _update_order(order_id: str, **fields):
    """更新订单字段。"""
    try:
        with SessionLocal() as db:
            db.execute(update(Order).where(Order.order_id == order_id).values(**fields))
            db.commit()
    except Exception as e:
        print(f"[PAY] 订单更新失败，降级内存: {e}")
        if order_id in _orders_mem:
            _orders_mem[order_id].update(fields)


def _mark_unlocked(user_id: str, order_id: str):
    """标记用户已解锁雷达。"""
    # 内存
    _unlocked_mem.add(user_id)
    # 持久化
    try:
        with SessionLocal() as db:
            existing = db.get(UserUnlock, user_id)
            if existing:
                existing.order_id = order_id
                existing.unlocked_at = _now()
            else:
                db.add(UserUnlock(user_id=user_id, order_id=order_id))
            db.commit()
    except Exception as e:
        print(f"[PAY] 解锁记录持久化失败，仅内存: {e}")


def _is_unlocked(user_id: str) -> tuple[bool, Optional[int]]:
    """查询用户解锁状态，返回 (unlocked, expire_days)。"""
    # 内存优先
    if user_id in _unlocked_mem:
        return True, 30
    # 持久化
    try:
        with SessionLocal() as db:
            rec = db.get(UserUnlock, user_id)
            if rec:
                return True, rec.expire_days
    except Exception:
        pass
    return False, None


# ── 路由 ─────────────────────────────────────────────────────
@router.get("/mode")
def get_pay_mode():
    """查询当前支付模式（前端据此显示「演示模式」标签）。"""
    return {"mode": "real" if _is_real_mode() else "mock"}


@router.post("/qrcode", response_model=QrcodeResponse)
async def generate_qrcode(payload: QrcodeRequest):
    """生成支付订单 + 二维码。

    真实模式: 调用微信 Native 下单，返回 code_url（weixin:// 链接）。
    模拟模式: 用 QR Server API 生成展示二维码。
    """
    order_id = wechat_pay.gen_out_trade_no()
    amount_fen = wechat_pay.get_amount_fen()
    real = _is_real_mode()

    if real:
        # ── 真实模式：调微信 Native 下单 ──
        try:
            result = await wechat_pay.native_prepay(order_id, payload.user_id)
            code_url = result.get("code_url", "")
            # 前端需要图片 URL，用 QR Server API 把 code_url 转成二维码图片
            qrcode_img = (
                f"https://api.qrserver.com/v1/create-qr-code/"
                f"?size=300x300&data={code_url}"
            )
            order = Order(
                order_id=order_id,
                user_id=payload.user_id,
                amount=amount_fen,
                status="PENDING",
                mode="real",
                code_url=code_url,
                qrcode_url=qrcode_img,
            )
            _save_order(order)
            return QrcodeResponse(
                order_id=order_id,
                qrcode_url=qrcode_img,
                code_url=code_url,
                amount=amount_fen,
                mode="real",
            )
        except Exception as e:
            print(f"[PAY] 微信下单失败，降级模拟模式: {e}")
            # 下单失败也降级到模拟，保证前端可用
            real = False

    # ── 模拟模式 ──
    qrcode_url = (
        f"https://api.qrserver.com/v1/create-qr-code/"
        f"?size=300x300&data=PAYMENT_{order_id}_AMOUNT_{amount_fen}FEN"
    )
    order = Order(
        order_id=order_id,
        user_id=payload.user_id,
        amount=amount_fen,
        status="PENDING",
        mode="mock",
        qrcode_url=qrcode_url,
    )
    _save_order(order)
    return QrcodeResponse(
        order_id=order_id,
        qrcode_url=qrcode_url,
        code_url=None,
        amount=amount_fen,
        mode="mock",
    )


@router.get("/status/{order_id}", response_model=PaymentStatus)
async def check_payment_status(order_id: str):
    """轮询支付状态。

    真实模式: 主动查微信订单状态 API（兜底回调可能丢失）。
    模拟模式: 第1-2次 PENDING，第3次起自动 SUCCESS。
    """
    order = _get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    new_poll = (order.poll_count or 0) + 1
    _update_order(order_id, poll_count=new_poll)

    if order.mode == "real":
        # ── 真实模式：查微信订单 ──
        try:
            wx_result = await wechat_pay.query_order(order_id)
            trade_state = wx_result.get("trade_state", "")
            if trade_state == "SUCCESS":
                _update_order(
                    order_id,
                    status="SUCCESS",
                    transaction_id=wx_result.get("transaction_id", ""),
                    paid_at=_now(),
                )
                _mark_unlocked(order.user_id, order_id)
                return PaymentStatus(
                    order_id=order_id, status="SUCCESS",
                    poll_count=new_poll, mode="real",
                )
            elif trade_state in ("CLOSED", "REVOKED", "PAYERROR"):
                _update_order(order_id, status=trade_state)
                return PaymentStatus(
                    order_id=order_id, status=trade_state,
                    poll_count=new_poll, mode="real",
                )
            # NOTPAY / USERPAYING → PENDING
            return PaymentStatus(
                order_id=order_id, status="PENDING",
                poll_count=new_poll, mode="real",
            )
        except Exception as e:
            print(f"[PAY] 微信查单失败: {e}")
            return PaymentStatus(
                order_id=order_id, status="PENDING",
                poll_count=new_poll, mode="real",
            )

    # ── 模拟模式：第3次轮询自动 SUCCESS ──
    if new_poll >= 3:
        _update_order(order_id, status="SUCCESS", paid_at=_now())
        _mark_unlocked(order.user_id, order_id)
        return PaymentStatus(
            order_id=order_id, status="SUCCESS",
            poll_count=new_poll, mode="mock",
        )
    return PaymentStatus(
        order_id=order_id, status="PENDING",
        poll_count=new_poll, mode="mock",
    )


@router.post("/notify")
async def wechat_notify(request: Request):
    """微信支付回调通知端点。

    微信在用户支付成功后 POST 到此地址（需在 .env WECHAT_NOTIFY_URL 配置）。
    流程：验签 → AES 解密 → 取 out_trade_no/transaction_id → 更新订单 → 解锁用户。
    必须返回 200 + {"code":"SUCCESS"}，否则微信会重试。
    """
    raw_body = await request.body()
    raw_str = raw_body.decode("utf-8")
    headers = {k.lower(): v for k, v in request.headers.items()}

    try:
        resource = wechat_pay.parse_notify(headers, raw_str)
    except ValueError as e:
        print(f"[PAY] 回调验签失败: {e}")
        return {"code": "FAIL", "message": "签名验证失败"}
    except Exception as e:
        print(f"[PAY] 回调解密失败: {e}")
        return {"code": "FAIL", "message": "解密失败"}

    out_trade_no = resource.get("out_trade_no", "")
    transaction_id = resource.get("transaction_id", "")
    trade_state = resource.get("trade_state", "")
    # attach 透传的 user_id
    user_id = resource.get("attach", "")

    if trade_state == "SUCCESS":
        _update_order(
            out_trade_no,
            status="SUCCESS",
            transaction_id=transaction_id,
            paid_at=_now(),
        )
        if user_id:
            _mark_unlocked(user_id, out_trade_no)
        print(f"[PAY] 回调解锁成功: order={out_trade_no} user={user_id}")

    # 微信要求返回此格式
    return {"code": "SUCCESS", "message": "成功"}


@router.post("/unlock-radar")
async def unlock_radar(payload: UnlockRadarRequest):
    """支付成功后手动确认解锁（兜底，正常由回调或轮询触发）。"""
    order = _get_order(payload.order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order.status != "SUCCESS":
        raise HTTPException(status_code=400, detail="订单尚未支付成功")
    _mark_unlocked(payload.user_id, payload.order_id)
    return {"status": "ok", "user_id": payload.user_id, "unlocked": True}


@router.get("/radar-status/{user_id}", response_model=RadarStatusResponse)
async def get_radar_status(user_id: str):
    """查询用户雷达解锁状态（持久化优先，内存兜底）。"""
    unlocked, expire_days = _is_unlocked(user_id)
    return RadarStatusResponse(
        user_id=user_id, unlocked=unlocked, expire_days=expire_days,
    )

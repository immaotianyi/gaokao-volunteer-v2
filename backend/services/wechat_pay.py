"""
微信支付 V3 服务层 — Native 下单 / 查单 / 回调验签解密

设计原则：
1. 无凭证（WECHAT_MCH_ID / API V3 密钥 / 商户证书未配置）时，is_configured() 返回 False，
   上层路由自动走模拟模式，保证开发/演示环境零配置可用。
2. 配置齐全后自动切真实微信支付 Native API V3，无需改代码。
3. 金额单位统一用「分」（微信支付规范）。

环境变量（.env）：
  WECHAT_APPID            公众号/小程序 AppID
  WECHAT_MCH_ID           商户号
  WECHAT_API_V3_KEY       APIv3 密钥（商户平台设置的 32 位密钥）
  WECHAT_CERT_SERIAL_NO   商户证书序列号
  WECHAT_PRIVATE_KEY_PATH 商户私钥 apiclient_key.pem 路径
  WECHAT_NOTIFY_URL       支付回调通知地址（必须 HTTPS，公网可达）
  PAY_PRODUCT_DESC        商品描述（默认：高考志愿狙击手·雷达解锁）
  PAY_AMOUNT_FEN          金额（分），默认 990 = ¥9.90
"""
import os
import json
import time
import uuid
import base64
import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx

# ── 配置读取 ──────────────────────────────────────────────────
WECHAT_APPID = os.getenv("WECHAT_APPID", "")
WECHAT_MCH_ID = os.getenv("WECHAT_MCH_ID", "")
WECHAT_API_V3_KEY = os.getenv("WECHAT_API_V3_KEY", "")
WECHAT_CERT_SERIAL_NO = os.getenv("WECHAT_CERT_SERIAL_NO", "")
WECHAT_PRIVATE_KEY_PATH = os.getenv("WECHAT_PRIVATE_KEY_PATH", "")
WECHAT_NOTIFY_URL = os.getenv("WECHAT_NOTIFY_URL", "")
PAY_PRODUCT_DESC = os.getenv("PAY_PRODUCT_DESC", "高考志愿狙击手·雷达解锁")
PAY_AMOUNT_FEN = int(os.getenv("PAY_AMOUNT_FEN", "990"))

# 微信支付 API 基址
WX_API_BASE = "https://api.mch.weixin.qq.com"

# 商户私钥缓存
_private_key = None


def is_configured() -> bool:
    """是否已配置真实微信支付所需全部凭证。"""
    return all([
        WECHAT_APPID,
        WECHAT_MCH_ID,
        WECHAT_API_V3_KEY,
        WECHAT_CERT_SERIAL_NO,
        WECHAT_PRIVATE_KEY_PATH,
        WECHAT_NOTIFY_URL,
    ])


def get_amount_fen() -> int:
    """返回订单金额（分）。"""
    return PAY_AMOUNT_FEN


def gen_out_trade_no() -> str:
    """生成商户订单号：ORDER_年月日时分秒 + 12位随机 hex。"""
    ts = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d%H%M%S")
    return f"ORDER_{ts}{secrets.token_hex(6).upper()}"


# ── 私钥加载与签名 ────────────────────────────────────────────
def _load_private_key():
    """加载商户私钥（RSA）。延迟加载，仅真实模式触发。"""
    global _private_key
    if _private_key is not None:
        return _private_key
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    _private_key = serialization.load_pem_private_key(
        _read_key_file(WECHAT_PRIVATE_KEY_PATH).encode(),
        password=None,
    )
    return _private_key


def _read_key_file(path: str) -> str:
    """读取私钥文件内容（支持相对路径，相对 backend/ 目录）。"""
    if os.path.isabs(path) and os.path.exists(path):
        with open(path) as f:
            return f.read()
    # 相对路径：相对项目 backend 目录解析
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates = [
        path,
        os.path.join(backend_dir, path),
        os.path.join(backend_dir, "cert", path),
        os.path.join(backend_dir, "cert", os.path.basename(path)),
    ]
    for c in candidates:
        if os.path.exists(c):
            with open(c) as f:
                return f.read()
    raise FileNotFoundError(f"商户私钥文件未找到: {path}")


def _sign(message: str) -> str:
    """使用商户私钥对 message 做 SHA256withRSA 签名，返回 base64。"""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    key = _load_private_key()
    signature = key.sign(
        message.encode("utf-8"),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode("utf-8")


def _build_auth_header(method: str, url_path: str, body: str) -> str:
    """构造微信支付 V3 Authorization 头。

    签名串格式：
      HTTP请求方法\n
      请求URL（不含域名）\n
      时间戳\n
      随机串\n
      请求报文主体（GET 为空）\n
    """
    timestamp = str(int(time.time()))
    nonce = secrets.token_hex(16)
    sign_message = f"{method}\n{url_path}\n{timestamp}\n{nonce}\n{body}\n"
    signature = _sign(sign_message)
    return (
        f'WECHATPAY2-SHA256-RSA2048 '
        f'mchid="{WECHAT_MCH_ID}",'
        f'nonce_str="{nonce}",'
        f'signature="{signature}",'
        f'timestamp="{timestamp}",'
        f'serial_no="{WECHAT_CERT_SERIAL_NO}"'
    )


# ── Native 下单 ──────────────────────────────────────────────
async def native_prepay(out_trade_no: str, user_id: str) -> dict:
    """调用微信支付 Native 下单 API，返回 {code_url}。

    API: POST /v3/pay/transactions/native
    返回: {"code_url": "weixin://wxpay/bizpayurl?pr=xxx"}
    """
    body = {
        "appid": WECHAT_APPID,
        "mchid": WECHAT_MCH_ID,
        "description": PAY_PRODUCT_DESC,
        "out_trade_no": out_trade_no,
        "time_expire": _gen_time_expire(),
        "notify_url": WECHAT_NOTIFY_URL,
        "amount": {
            "total": PAY_AMOUNT_FEN,
            "currency": "CNY",
        },
        # attach 透传 user_id，回调时用于解锁
        "attach": user_id,
    }
    body_str = json.dumps(body, ensure_ascii=False)
    url_path = "/v3/pay/transactions/native"
    auth = _build_auth_header("POST", url_path, body_str)

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{WX_API_BASE}{url_path}",
            content=body_str,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": auth,
                "User-Agent": "gaokao-sniper/1.0",
            },
        )
    if resp.status_code != 200:
        raise RuntimeError(f"微信下单失败 [{resp.status_code}]: {resp.text}")
    return resp.json()  # {"code_url": "..."}


def _gen_time_expire() -> str:
    """订单过期时间（RFC3339），当前 +30 分钟。"""
    expire = datetime.now(timezone(timedelta(hours=8))) + timedelta(minutes=30)
    return expire.strftime("%Y-%m-%dT%H:%M:%S+08:00")


# ── 查单 ─────────────────────────────────────────────────────
async def query_order(out_trade_no: str) -> dict:
    """查询微信支付订单状态。

    API: GET /v3/pay/transactions/out-trade-no/{out_trade_no}?mchid=xxx
    返回: {trade_state, transaction_id, amount:{total,...}, ...}
    """
    url_path = f"/v3/pay/transactions/out-trade-no/{out_trade_no}?mchid={WECHAT_MCH_ID}"
    auth = _build_auth_header("GET", url_path, "")
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{WX_API_BASE}{url_path}",
            headers={
                "Accept": "application/json",
                "Authorization": auth,
                "User-Agent": "gaokao-sniper/1.0",
            },
        )
    if resp.status_code != 200:
        raise RuntimeError(f"微信查单失败 [{resp.status_code}]: {resp.text}")
    return resp.json()


# ── 回调验签 + 解密 ──────────────────────────────────────────
def _verify_signature(timestamp: str, nonce: str, body: str, signature: str,
                      wx_serial_no: str) -> bool:
    """验证微信回调签名（使用微信平台证书公钥）。

    生产环境应获取微信平台证书并缓存。这里简化处理：
    若未配置平台证书，跳过验签（仅适用于开发调试，生产必须配置）。
    """
    platform_cert_path = os.getenv("WECHAT_PLATFORM_CERT_PATH", "")
    if not platform_cert_path:
        # 未配置平台证书 → 跳过验签（开发模式）
        return True
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography import x509
    cert_pem = _read_key_file(platform_cert_path)
    cert = x509.load_pem_x509_certificate(cert_pem.encode())
    pub = cert.public_key()
    message = f"{timestamp}\n{nonce}\n{body}\n".encode("utf-8")
    try:
        pub.verify(
            base64.b64decode(signature),
            message,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return True
    except Exception:
        return False


def decrypt_resource(associated_data: str, nonce: str, ciphertext: str) -> dict:
    """解密回调通知中的 resource.ciphertext（AES-256-GCM）。

    返回明文 JSON dict，含 out_trade_no / transaction_id / trade_state / amount 等。
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key = WECHAT_API_V3_KEY.encode("utf-8")
    nonce_bytes = nonce.encode("utf-8")
    cipher_bytes = base64.b64decode(ciphertext)
    # AES-GCM 的 additional_data
    ad = associated_data.encode("utf-8") if associated_data else b""
    aesgcm = AESGCM(key)
    plain = aesgcm.decrypt(nonce_bytes, cipher_bytes, ad)
    return json.loads(plain.decode("utf-8"))


def parse_notify(headers: dict, raw_body: str) -> dict:
    """解析微信支付回调通知，返回解密后的资源 dict。

    流程：
      1. 验签（Wechatpay-Signature / Wechatpay-Timestamp / Wechatpay-Nonce）
      2. 解析 JSON 取 resource.{associated_data, nonce, ciphertext}
      3. AES-256-GCM 解密
    """
    timestamp = headers.get("wechatpay-timestamp", "")
    nonce = headers.get("wechatpay-nonce", "")
    signature = headers.get("wechatpay-signature", "")
    serial = headers.get("wechatpay-serial", "")

    if not _verify_signature(timestamp, nonce, raw_body, signature, serial):
        raise ValueError("微信回调签名验证失败")

    body = json.loads(raw_body)
    resource = body.get("resource", {})
    return decrypt_resource(
        resource.get("associated_data", ""),
        resource.get("nonce", ""),
        resource.get("ciphertext", ""),
    )

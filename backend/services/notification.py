"""
通知推送服务 — 站内消息 + 邮件摘要

渠道优先级:
  1. 站内消息 (badge/角标) — MVP, 零外部依赖
  2. 邮件摘要 (SMTP) — 中等难度
  3. 微信服务号模板消息 — 高难度 (需认证服务号)
"""
import json
import os
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Optional


# ── 站内消息 ───────────────────────────────────────────────

# 内存存储（生产环境替换为 Redis/DB）
_notifications: dict[str, list[dict]] = {}  # user_id → [通知列表]


def add_notification(
    user_id: str,
    title: str,
    body: str,
    category: str = "radar",
    action_url: str = "",
) -> dict:
    """添加一条站内通知。"""
    if user_id not in _notifications:
        _notifications[user_id] = []

    notif = {
        "id": f"notif_{len(_notifications[user_id])}_{int(datetime.now().timestamp())}",
        "title": title,
        "body": body,
        "category": category,
        "action_url": action_url,
        "created_at": datetime.now().isoformat(),
        "read": False,
    }
    _notifications[user_id].append(notif)

    # 保留最近 100 条
    if len(_notifications[user_id]) > 100:
        _notifications[user_id] = _notifications[user_id][-100:]

    return notif


def get_notifications(user_id: str, limit: int = 20) -> list[dict]:
    """获取用户的站内通知列表。"""
    notifs = _notifications.get(user_id, [])
    return notifs[-limit:]


def get_unread_count(user_id: str) -> int:
    """获取未读通知数量（用于 Badge 角标）。"""
    notifs = _notifications.get(user_id, [])
    return sum(1 for n in notifs if not n["read"])


def mark_all_read(user_id: str) -> int:
    """标记全部已读。"""
    notifs = _notifications.get(user_id, [])
    count = 0
    for n in notifs:
        if not n["read"]:
            n["read"] = True
            count += 1
    return count


def generate_daily_radar_notification(
    user_id: str,
    new_count: int,
    total_count: int,
    top_pick: Optional[dict] = None,
) -> dict:
    """生成每日捡漏雷达通知。"""
    title = f"今日新增 {new_count} 个捡漏机会"
    body = f"捡漏雷达扫描完成，共发现 {total_count} 个安全机会，其中 {new_count} 个为今日新增。"

    if top_pick:
        body += f"\n最佳机会: {top_pick.get('university_name', '')} {top_pick.get('major_name', '')} (评分{top_pick.get('leakage_score', 0)}分)"

    return add_notification(
        user_id=user_id,
        title=title,
        body=body,
        category="radar",
        action_url="/radar",
    )


# ── 邮件摘要 ───────────────────────────────────────────────

def _build_radar_email_html(
    user_name: str,
    new_count: int,
    total_count: int,
    top_picks: list[dict],
    date_str: str,
) -> str:
    """构建捡漏雷达每日邮件 HTML。"""
    picks_html = ""
    for i, pick in enumerate(top_picks[:5]):
        picks_html += f"""
        <tr>
            <td style="padding:12px;border-bottom:1px solid #eee;">
                <strong>#{i+1}</strong> {pick.get('university_name', '')} — {pick.get('major_name', '')}
                <br><span style="color:#888;font-size:13px;">
                    评分: {pick.get('leakage_score', 0)}分 | 计划招 {pick.get('plan_count', 0)} 人
                    {'| 估分: ' + str(pick.get('estimated_score', '')) + '分' if pick.get('estimated_score') else ''}
                </span>
            </td>
        </tr>"""

    return f"""
    <html>
    <body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
        <div style="background:#1a1a2e;color:#eab308;padding:20px;border-radius:12px 12px 0 0;">
            <h1 style="margin:0;">📡 高考志愿狙击手 — 每日捡漏情报</h1>
        </div>
        <div style="background:#fff;padding:20px;border:1px solid #eee;border-top:none;border-radius:0 0 12px 12px;">
            <p>{user_name}，您好！</p>
            <p>{date_str} 捡漏雷达扫描结果：</p>
            <div style="background:#f0fdf4;padding:15px;border-radius:8px;margin:15px 0;">
                <strong style="color:#16a34a;">今日新增 {new_count} 个捡漏机会</strong>
                <br>当前共有 {total_count} 个安全志愿等您查看
            </div>
            <h3>🏆 最佳机会 TOP{min(5, len(top_picks))}</h3>
            <table style="width:100%;border-collapse:collapse;">
                {picks_html}
            </table>
            <div style="margin-top:20px;text-align:center;">
                <a href="http://localhost:8000" style="background:#eab308;color:#000;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:bold;">查看全部机会</a>
            </div>
            <p style="color:#888;font-size:12px;margin-top:20px;">
                此邮件由高考志愿狙击手系统自动发送，如需退订请回复"TD"。
            </p>
        </div>
    </body>
    </html>"""


async def send_daily_email(
    to_email: str,
    user_name: str,
    new_count: int,
    total_count: int,
    top_picks: list[dict],
) -> bool:
    """
    发送每日捡漏邮件摘要。

    需要配置环境变量:
      SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD
    """
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    from_email = os.getenv("SMTP_FROM", smtp_user)

    if not smtp_host or not smtp_user:
        print("[Notification] SMTP 未配置，跳过邮件发送")
        return False

    date_str = datetime.now().strftime("%Y年%m月%d日")

    html_content = _build_radar_email_html(
        user_name=user_name,
        new_count=new_count,
        total_count=total_count,
        top_picks=top_picks,
        date_str=date_str,
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📡 高考捡漏情报 {date_str} — 今日新增 {new_count} 个机会"
    msg["From"] = from_email
    msg["To"] = to_email
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
        print(f"[Notification] 邮件已发送至 {to_email}")
        return True
    except Exception as e:
        print(f"[Notification] 邮件发送失败: {e}")
        return False

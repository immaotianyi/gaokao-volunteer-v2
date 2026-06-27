"""
通知推送服务 — 站内消息 + 邮件摘要（V2 — SQLite 持久化）

渠道优先级:
  1. 站内消息 (badge/角标) — SQLite 持久化，重启不丢
  2. 邮件摘要 (SMTP) — 中等难度
  3. 微信服务号模板消息 — 高难度 (需认证服务号)
"""
import json
import os
import asyncio
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Optional

from sqlalchemy import desc, func, select

from database import SessionLocal, Base, is_async_db_available
from models import Notification


# ── 建表（首次调用时自动创建） ────────────────────────────────
def _ensure_table():
    """确保 notifications 表存在。"""
    try:
        Base.metadata.create_all(bind=SessionLocal.kw["bind"], tables=[Notification.__table__])
    except Exception as e:
        print(f"[Notification] 建表失败，fallback 到内存: {e}")


_ensure_table()


# ── 内存 fallback（SQLite 不可用时） ──────────────────────────
_mem_notifications: dict[str, list[dict]] = {}


def add_notification(
    user_id: str,
    title: str,
    body: str,
    category: str = "radar",
    action_url: str = "",
) -> dict:
    """添加一条站内通知（持久化到 SQLite）。"""
    notif_id = f"notif_{user_id}_{int(datetime.now().timestamp() * 1000)}"

    notif = {
        "id": notif_id,
        "user_id": user_id,
        "title": title,
        "body": body,
        "category": category,
        "action_url": action_url,
        "created_at": datetime.now().isoformat(),
        "read": False,
    }

    try:
        db = SessionLocal()
        row = Notification(
            id=notif_id,
            user_id=user_id,
            title=title,
            body=body,
            category=category,
            action_url=action_url,
            read=False,
        )
        db.add(row)
        db.commit()
    except Exception as e:
        print(f"[Notification] SQLite 写入失败，fallback 到内存: {e}")
        if user_id not in _mem_notifications:
            _mem_notifications[user_id] = []
        _mem_notifications[user_id].append(notif)
        if len(_mem_notifications[user_id]) > 100:
            _mem_notifications[user_id] = _mem_notifications[user_id][-100:]
    finally:
        try:
            db.close()
        except:
            pass

    return notif


def get_notifications(user_id: str, limit: int = 20) -> list[dict]:
    """获取用户的站内通知列表（从 SQLite 读取）。"""
    try:
        db = SessionLocal()
        rows = db.query(Notification).filter(
            Notification.user_id == user_id
        ).order_by(desc(Notification.created_at)).limit(limit).all()

        if not rows:
            # 尝试从内存 fallback 读取
            mem = _mem_notifications.get(user_id, [])
            return mem[-limit:] if mem else []

        return [{
            "id": r.id,
            "user_id": r.user_id,
            "title": r.title,
            "body": r.body,
            "category": r.category,
            "action_url": r.action_url or "",
            "created_at": r.created_at.isoformat() if r.created_at else "",
            "read": r.read,
        } for r in rows]
    except Exception as e:
        print(f"[Notification] SQLite 读取失败，fallback 到内存: {e}")
        mem = _mem_notifications.get(user_id, [])
        return mem[-limit:] if mem else []
    finally:
        try:
            db.close()
        except:
            pass


def get_unread_count(user_id: str) -> int:
    """获取未读通知数量（用于 Badge 角标）。"""
    try:
        db = SessionLocal()
        count = db.query(func.count(Notification.id)).filter(
            Notification.user_id == user_id,
            Notification.read == False,
        ).scalar()
        return int(count or 0)
    except Exception as e:
        print(f"[Notification] SQLite 读取失败，fallback 到内存: {e}")
        notifs = _mem_notifications.get(user_id, [])
        return sum(1 for n in notifs if not n["read"])
    finally:
        try:
            db.close()
        except:
            pass


def mark_all_read(user_id: str) -> int:
    """标记全部已读。"""
    try:
        db = SessionLocal()
        rows = db.query(Notification).filter(
            Notification.user_id == user_id,
            Notification.read == False,
        ).all()
        count = 0
        for r in rows:
            r.read = True
            count += 1
        db.commit()
        return count
    except Exception as e:
        print(f"[Notification] SQLite 更新失败，fallback 到内存: {e}")
        notifs = _mem_notifications.get(user_id, [])
        count = 0
        for n in notifs:
            if not n["read"]:
                n["read"] = True
                count += 1
        return count
    finally:
        try:
            db.close()
        except:
            pass


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
            <h1 style="margin:0;">高考志愿狙击手 — 每日捡漏情报</h1>
        </div>
        <div style="background:#fff;padding:20px;border:1px solid #eee;border-top:none;border-radius:0 0 12px 12px;">
            <p>{user_name}，您好！</p>
            <p>{date_str} 捡漏雷达扫描结果：</p>
            <div style="background:#f0fdf4;padding:15px;border-radius:8px;margin:15px 0;">
                <strong style="color:#16a34a;">今日新增 {new_count} 个捡漏机会</strong>
                <br>当前共有 {total_count} 个安全志愿等您查看
            </div>
            <h3>最佳机会 TOP{min(5, len(top_picks))}</h3>
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


def _smtp_send_sync(msg_str: str, smtp_config: dict) -> bool:
    """同步发送邮件（供 asyncio.to_thread 调用，避免阻塞事件循环）。"""
    try:
        from email import message_from_string
        msg_obj = message_from_string(msg_str)
        with smtplib.SMTP(smtp_config["host"], smtp_config["port"], timeout=30) as server:
            server.starttls()
            server.login(smtp_config["user"], smtp_config["password"])
            server.send_message(msg_obj)
        return True
    except Exception as e:
        print(f"[Notification] 邮件发送失败: {e}")
        return False


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
    msg["Subject"] = f"高考捡漏情报 {date_str} — 今日新增 {new_count} 个机会"
    msg["From"] = from_email
    msg["To"] = to_email
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    smtp_config = {
        "host": smtp_host,
        "port": smtp_port,
        "user": smtp_user,
        "password": smtp_password,
    }
    success = await asyncio.to_thread(_smtp_send_sync, msg.as_string(), smtp_config)
    if success:
        print(f"[Notification] 邮件已发送至 {to_email}")
    return success

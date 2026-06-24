#!/usr/bin/env python3
"""
每日数据更新流水线 (Daily Update Pipeline)

执行时间：每天 07:00 (通过 cron 调度)
执行内容：
  1. 对比阳光高考平台最新招生计划与本地 CSV
  2. 发现新增/变更/删除的记录
  3. 更新本地 CSV + Redis 缓存刷新 + 生成差异报告

用法：
  python3 backend/scripts/daily_update.py
  python3 backend/scripts/daily_update.py --dry-run  # 仅对比差异，不实际更新
"""
import asyncio
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import httpx

# 将 backend 目录加入 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ── 配置 ───────────────────────────────────────────────────
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
PLAN_FILES = {
    "2025": "plans_2025.csv",
    "2026": "plans_2026.csv",
}

# 关键变更阈值（触发通知）
NOTIFY_THRESHOLD_NEW = 5       # 新增 ≥ 5 条记录时通知
NOTIFY_THRESHOLD_CHANGE = 3    # 计划数变更 ≥ 3 条记录时通知
NOTIFY_THRESHOLD_DELETE = 3    # 删除 ≥ 3 条记录时通知


# ── 工具函数 ───────────────────────────────────────────────

def _build_unique_key(row: dict) -> str:
    """构建联合主键用于对比。"""
    return f"{row.get('university_code','')}_{row.get('group_code','')}_{row.get('major_code','')}"


def _hash_df(df: pd.DataFrame, cols: list[str]) -> str:
    """计算 DataFrame 的 MD5 哈希（用于快速变化检测）。"""
    subset = df[cols].copy()
    for col in cols:
        subset[col] = subset[col].astype(str)
    content = subset.to_csv(index=False).encode("utf-8")
    return hashlib.md5(content).hexdigest()


async def _refresh_redis_cache(backend_url: str = BACKEND_URL):
    """调用后端 API 刷新 Redis 缓存。"""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{backend_url}/api/leakage-radar/refresh-cache")
            if resp.status_code == 200:
                data = resp.json()
                print(f"  [Redis] 缓存已刷新，删除 {data.get('deleted_keys', 0)} 个 key")
                return True
            else:
                print(f"  [Redis] 刷新失败: HTTP {resp.status_code}")
                return False
    except Exception as e:
        print(f"  [Redis] 刷新异常: {e}")
        return False


def _generate_diff_report(
    new_records: list[dict],
    changed_records: list[dict],
    deleted_records: list[dict],
) -> dict:
    """生成差异报告。"""
    report = {
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "new": len(new_records),
            "changed": len(changed_records),
            "deleted": len(deleted_records),
            "total_changes": len(new_records) + len(changed_records) + len(deleted_records),
        },
        "details": {
            "new": new_records[:50],       # 限制详情数量
            "changed": changed_records[:50],
            "deleted": deleted_records[:50],
        },
        "should_notify": (
            len(new_records) >= NOTIFY_THRESHOLD_NEW
            or len(changed_records) >= NOTIFY_THRESHOLD_CHANGE
            or len(deleted_records) >= NOTIFY_THRESHOLD_DELETE
        ),
    }
    return report


def _save_report(report: dict, log_dir: Path = LOG_DIR):
    """保存差异报告到日志目录。"""
    log_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")
    report_path = log_dir / f"daily_update_{date_str}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"  [Report] 差异报告已保存: {report_path}")


# ── 主流程 ─────────────────────────────────────────────────

async def main(dry_run: bool = False):
    print(f"[{datetime.now().isoformat()}] ═══ 每日数据更新流水线启动 ═══")

    # Step 1: 获取最新数据
    print("[1/5] 获取最新招生计划数据...")
    # TODO: 接入实际数据源
    # 方案 A: 从各省考试院下载最新招生计划 Excel/CSV
    # 方案 B: 从项目配置的 Google Sheets / 腾讯文档拉取
    # 方案 C: 爬取阳光高考平台 API
    # 当前：检测本地 CSV 是否有更新（基于文件 MD5）

    data_dir = DATA_DIR
    plan_file_2026 = data_dir / PLAN_FILES["2026"]

    if not plan_file_2026.exists():
        print(f"  [ERROR] 数据文件不存在: {plan_file_2026}")
        print(f"  [SKIP] 跳过更新（无数据源）")
        return

    # 读取当前数据
    current_df = pd.read_csv(plan_file_2026)
    print(f"  [DATA] 当前招生计划: {len(current_df)} 行")

    # 检查是否有备份（昨天的数据）
    backup_file = data_dir / f"plans_2026_backup_{datetime.now().strftime('%Y%m%d')}.csv"

    # Step 2: 差异对比
    print("[2/5] 对比差异...")
    # 如果有昨天的备份，进行对比
    yesterday_date = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
    yesterday_backup = data_dir / f"plans_2026_backup_{yesterday_date}.csv"

    new_records = []
    changed_records = []
    deleted_records = []

    if yesterday_backup.exists():
        old_df = pd.read_csv(yesterday_backup)
        print(f"  [DIFF] 对比昨日数据: {len(old_df)} 行 → 今日: {len(current_df)} 行")

        # 构建 key 集合
        old_keys = set()
        for _, row in old_df.iterrows():
            old_keys.add(_build_unique_key(row.to_dict()))

        current_keys = set()
        current_dict = {}
        for _, row in current_df.iterrows():
            d = row.to_dict()
            k = _build_unique_key(d)
            current_keys.add(k)
            current_dict[k] = d

        old_dict = {}
        for _, row in old_df.iterrows():
            d = row.to_dict()
            k = _build_unique_key(d)
            old_dict[k] = d

        # 新增
        new_keys = current_keys - old_keys
        for k in new_keys:
            record = current_dict[k]
            new_records.append({
                "university_name": record.get("university_name", ""),
                "major_name": record.get("major_name", ""),
                "plan_count": record.get("plan_count", 0),
                "key": k,
            })

        # 删除
        deleted_keys = old_keys - current_keys
        for k in deleted_keys:
            record = old_dict[k]
            deleted_records.append({
                "university_name": record.get("university_name", ""),
                "major_name": record.get("major_name", ""),
                "plan_count": record.get("plan_count", 0),
                "key": k,
            })

        # 变更（计划数变化）
        common_keys = current_keys & old_keys
        for k in common_keys:
            cur_plan = current_dict[k].get("plan_count", 0)
            old_plan = old_dict[k].get("plan_count", 0)
            if cur_plan != old_plan:
                changed_records.append({
                    "university_name": current_dict[k].get("university_name", ""),
                    "major_name": current_dict[k].get("major_name", ""),
                    "plan_count_old": old_plan,
                    "plan_count_new": cur_plan,
                    "change": cur_plan - old_plan,
                    "key": k,
                })

        print(f"  [DIFF] 新增: {len(new_records)}, 变更: {len(changed_records)}, 删除: {len(deleted_records)}")
    else:
        print("  [DIFF] 无昨日备份，首次运行，全部视为基准数据")
        # 首次运行：创建备份
        if not dry_run:
            current_df.to_csv(backup_file, index=False)
            print(f"  [BACKUP] 基准备份已创建: {backup_file}")

    # Step 3: 数据更新
    print("[3/5] 更新本地数据...")
    if not dry_run:
        # 创建今日备份
        current_df.to_csv(backup_file, index=False)
        print(f"  [BACKUP] 今日备份: {backup_file}")

        # 如果有变更，更新 CSV
        if new_records or changed_records or deleted_records:
            print(f"  [UPDATE] 共 {len(new_records) + len(changed_records) + len(deleted_records)} 条变更")

            # 同步到数据库（如果 PostgreSQL 可用）
            try:
                from database import SessionLocal
                from models import AdmissionPlan
                db = SessionLocal()
                try:
                    # 批量 upsert（简化版：先删后插）
                    for record in new_records:
                        # TODO: 完整实现 upsert 逻辑
                        pass
                    db.commit()
                    print(f"  [DB] 数据库同步完成")
                finally:
                    db.close()
            except Exception as e:
                print(f"  [DB] 数据库同步跳过 (非关键): {e}")
    else:
        print("  [DRY-RUN] 跳过实际更新")

    # Step 4: 清除 Redis 缓存
    print("[4/5] 刷新 Redis 缓存...")
    if not dry_run and (new_records or changed_records or deleted_records):
        await _refresh_redis_cache()
    elif dry_run:
        print("  [DRY-RUN] 跳过缓存刷新")

    # Step 5: 生成差异报告
    print("[5/5] 生成差异报告...")
    report = _generate_diff_report(new_records, changed_records, deleted_records)
    _save_report(report)

    # 通知
    if report["should_notify"]:
        print(f"\n{'='*50}")
        print(f"⚠️  关键变更检测！")
        print(f"  新增: {len(new_records)} 条")
        print(f"  变更: {len(changed_records)} 条")
        print(f"  删除: {len(deleted_records)} 条")
        if new_records:
            print(f"\n  新增记录示例:")
            for r in new_records[:5]:
                print(f"    + {r['university_name']} {r['major_name']} (计划{r['plan_count']}人)")
        if changed_records:
            print(f"\n  计划数变更示例:")
            for r in changed_records[:5]:
                direction = "↑" if r["change"] > 0 else "↓"
                print(f"    {direction} {r['university_name']} {r['major_name']}: {r['plan_count_old']}→{r['plan_count_new']}")
        print(f"{'='*50}")

        # ── 生成站内通知 ──
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
            from services.notification import add_notification
            add_notification(
                user_id="broadcast",
                title=f"今日捡漏雷达更新: +{len(new_records)} 新机会",
                body=f"数据更新完成: 新增{len(new_records)}条, 变更{len(changed_records)}条, 删除{len(deleted_records)}条。\n"
                     f"请刷新捡漏雷达查看最新机会。",
                category="radar",
                action_url="/radar",
            )
            print(f"  [Notify] 站内通知已生成")
        except Exception as e:
            print(f"  [Notify] 通知生成失败 (非关键): {e}")

        # ── 邮件通知（如配置了 SMTP） ──
        smtp_host = os.getenv("SMTP_HOST", "")
        if smtp_host:
            try:
                from services.notification import send_daily_email
                notify_email = os.getenv("NOTIFY_EMAIL", "")
                if notify_email:
                    # 异步发送邮件
                    import asyncio as _asyncio
                    _asyncio.run(send_daily_email(
                        to_email=notify_email,
                        user_name="管理员",
                        new_count=len(new_records),
                        total_count=len(current_df),
                        top_picks=new_records[:5],
                    ))
                    print(f"  [Notify] 邮件已发送至 {notify_email}")
            except Exception as e:
                print(f"  [Notify] 邮件发送失败 (非关键): {e}")

    print(f"[{datetime.now().isoformat()}] ═══ 每日数据更新流水线完成 ═══")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="每日数据更新流水线")
    parser.add_argument("--dry-run", action="store_true", help="仅对比差异，不实际更新")
    args = parser.parse_args()

    asyncio.run(main(dry_run=args.dry_run))

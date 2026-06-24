#!/usr/bin/env python3
"""
高考志愿狙击手 — 自动化回归测试脚本
========================================
考生档案: 2024届 | 广东 | 555分 | 物化生 | 英120/数86/语110 | 色弱 | 髌骨受伤
目标: 15 条志愿逐条调 API 比对预期状态

启动方式:
  python3 regression_test.py              # 自动启动 mock_server
  python3 regression_test.py --no-server  # mock_server 已在运行

环境: mock_server.py 已接入 enrollment_rules.json KB
"""

import json
import subprocess
import sys
import time
import urllib.request
import argparse

PORT = 8000
BASE_URL = f"http://localhost:{PORT}"

# ── 考生档案 ──
PROFILE = {
    "province": "广东",
    "score": 555,
    "rank": 58000,
    "subjects": "物理,化学,生物",
    "english_score": 120,
    "math_score": 86,
    "vision_status": "色弱",
    "notes": "髌骨受伤，无法剧烈运动"
}

# ── 预期结果对照表 ──
# (编号, 大学, 专业, 预期状态, 触发规则说明)
EXPECTED = [
    (1,  "中山大学",     "临床医学",                "DANGER",  "章程不录色弱，体检色弱→DANGER"),
    (2,  "华南理工大学",  "数据科学与大数据技术",    "WARNING", "数学单科 ≥110 门槛，档案 86→WARNING"),
    (3,  "华南师范大学",  "计算机科学与技术",        "WARNING", "数学单科 ≥105 门槛，档案 86→WARNING"),
    (4,  "华南农业大学",  "农学",                    "WARNING", "色弱不宜就读(WARNING级) + 低偏好农学类"),
    (5,  "复旦大学",     "护理学",                  "WARNING", "无章程限制，通用低偏好关键词→WARNING"),
    (6,  "南方医科大学",  "食品科学与工程",          "DANGER",  "除法学/管理/外语外不录色弱→DANGER"),
    (7,  "华南理工大学",  "环境科学",                "WARNING", "低偏好生化环材 + 章程标注"),
    (8,  "华南农业大学",  "软件工程",                "PASS",    "英语≥90满足(120) + 无体检限制→PASS"),
    (9,  "华南农业大学",  "园艺",                    "WARNING", "色弱不宜就读(WARNING级) + 低偏好农学类"),
    (10, "广州大学",     "网络空间安全",            "PASS",    "正则不匹配网络空间安全于美术学/化工等模式，进入.*全栈规则→PASS"),
    (11, "北京大学",     "临床医学",                "PASS",    "章程: 未发现显性限制→PASS"),
    (12, "北京师范大学",  "数学与应用数学",          "PASS",    "章程: 未发现显性限制→PASS"),
    (13, "东莞理工学院",  "土木工程",                "WARNING", "大学不在KB，通用低偏好关键词(土木)→WARNING"),
    (14, "东莞理工学院",  "护理学",                  "WARNING", "大学不在KB，通用低偏好关键词(护理)→WARNING"),
    (15, "暨南大学",     "护理学",                  "DANGER",  "章程不录色弱 + 低偏好护理类叠加（DANGER优先）"),
]


def start_server():
    """启动 mock_server 并等待就绪"""
    proc = subprocess.Popen(
        [sys.executable, "mock_server.py"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    for _ in range(10):
        try:
            urllib.request.urlopen(f"{BASE_URL}/health", timeout=2)
            return proc
        except Exception:
            time.sleep(0.5)
    proc.kill()
    raise RuntimeError("mock_server 启动超时")


def call_check_risk(profile, targets):
    """调用 POST /api/check-risk"""
    payload = json.dumps({"profile": profile, "targets": targets}).encode()
    req = urllib.request.Request(
        f"{BASE_URL}/api/check-risk",
        data=payload,
        headers={"Content-Type": "application/json"}
    )
    resp = urllib.request.urlopen(req, timeout=15)
    return json.loads(resp.read())


def run_tests():
    targets = [{"university": e[1], "major": e[2]} for e in EXPECTED]
    result = call_check_risk(PROFILE, targets)
    results = result.get("results", [])

    passed = 0
    failed = 0

    print("=" * 100)
    print(f"  高考志愿狙击手 — 自动化回归测试")
    print(f"  考生: 广东 | 555分 | 物化生 | 英120/数86/语110 | 色弱")
    print("=" * 100)
    print()

    for i, (num, univ, major, expect, rule) in enumerate(EXPECTED):
        actual = results[i] if i < len(results) else {}
        actual_status = actual.get("status", "MISSING")
        actual_reason = actual.get("reason", "")

        match = actual_status == expect
        icon = "✅" if match else "❌"
        if match:
            passed += 1
        else:
            failed += 1

        print(f"{icon} #{num:<2} [{actual_status:<7}] {univ:<12} | {major:<20}")
        if not match:
            print(f"          预期: {expect} — {rule}")
            print(f"          实际: {actual_status} — {actual_reason[:90]}")
            print()

    print("-" * 100)
    total = passed + failed
    print(f"  总计: {total} 条 | ✅ PASS: {passed} | ❌ FAIL: {failed}")
    print(f"  通过率: {passed}/{total} = {passed/total*100:.1f}%")
    print()

    # 风险分布
    danger_n = sum(1 for r in results if r.get("status") == "DANGER")
    warn_n = sum(1 for r in results if r.get("status") == "WARNING")
    pass_n = sum(1 for r in results if r.get("status") == "PASS")
    print(f"  风险分布: 🔴 DANGER={danger_n} | 🟡 WARNING={warn_n} | 🟢 PASS={pass_n}")
    print("=" * 100)

    return failed == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-server", action="store_true", help="不启动 mock_server（已在运行）")
    args = parser.parse_args()

    server_proc = None
    try:
        if not args.no_server:
            print("[SETUP] 启动 mock_server...")
            server_proc = start_server()
            print("[SETUP] mock_server 就绪\n")

        success = run_tests()
        sys.exit(0 if success else 1)
    finally:
        if server_proc:
            server_proc.kill()
            print("\n[TEARDOWN] mock_server 已停止")

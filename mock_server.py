#!/usr/bin/env python3
"""
《高考志愿狙击手》Mock 后端服务器 (V2 — 完整 SSE 流式 + Radar API)

纯 Python 标准库实现，无需安装任何第三方包。
启动方式: python3 mock_server.py
默认监听: 0.0.0.0:8765

接口:
  GET  /api/check-risk/stream — SSE 流式探雷（真实 profile + targets 注入日志）
  POST /api/check-risk        — JSON 探雷（保留兼容）
  POST /api/leakage-radar      — 捡漏雷达
  POST /api/profile            — 用户档案
  GET  /health                 — 健康检查
"""
import json
import os
import random
import sys
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# ── 注入 backend 到 sys.path ──
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend"))

from services.risk_checker import _mock_check as check_risk

PORT = 8000

# =============================================================
# Mock 数据
# =============================================================

MOCK_RADAR_DATA = {
    "province": "广东",
    "subject_group": "物理类",
    "total": 8,
    "opportunities": [
        {"university_name":"广州大学","major_name":"网络空间安全","group_code":"11078202","plan_count":50,"opportunity_type":"新增专业","reason":"本年首次单列招生，大众缺乏历史分数参考。"},
        {"university_name":"华南师范大学","major_name":"数字经济","group_code":"10574215","plan_count":40,"opportunity_type":"新增专业","reason":"汕尾校区新设，报考热度极低。"},
        {"university_name":"暨南大学","major_name":"数据科学","group_code":"10559202","plan_count":55,"opportunity_type":"暴增扩招","reason":"计划数从30暴增至55。"},
        {"university_name":"中山大学","major_name":"园艺","group_code":"10558204","plan_count":20,"opportunity_type":"新增专业","reason":"本年首次招生。"},
        {"university_name":"华南理工","major_name":"人工智能","group_code":"10561204","plan_count":45,"opportunity_type":"新增专业","reason":"新兴交叉学科，首年单独招生。"},
        {"university_name":"深圳大学","major_name":"集成电路","group_code":"10590201","plan_count":35,"opportunity_type":"新增专业","reason":"国家战略专业，首年扩编。"},
        {"university_name":"广东工业大学","major_name":"智能制造","group_code":"11845201","plan_count":70,"opportunity_type":"暴增扩招","reason":"计划数从40增至70（增幅75%）。"},
        {"university_name":"华南师大(汕尾)","major_name":"数字经济","group_code":"10574216","plan_count":38,"opportunity_type":"新增专业","reason":"异地校区，往年无数据。"},
    ],
}

# ── 不再维护本地 mock_risk，全部委托给 backend risk_checker ──
# mock_risk 仅作为别名保留，内部调用 _mock_check (接入 enrollment_rules.json)
# 原来的 _BODY_CHECK / _LOW_PREFERENCE 硬编码已移除


def mock_risk(university: str, major: str, profile: dict) -> dict:
    """委托给 risk_checker._mock_check，接入 enrollment_rules.json KB。"""
    return check_risk(profile, university, major)



# =============================================================
# SSE 生成器
# =============================================================

def generate_sse_stream(user_profile: dict, targets: list, use_ai: bool = False) -> str:
    """
    生成完整的 SSE 流，逐目标展示日志 + 最终结果。

    如果 use_ai=True 且 DEEPSEEK_API_KEY 环境变量被设置，
    每个目标会真正调用 DeepSeek API 进行 AI 审查。
    """
    import os
    api_key = os.getenv("DEEPSEEK_API_KEY", "")

    lines = []

    def emit(typ, text=None, data=None):
        payload = {"type": typ}
        if text is not None:
            payload["text"] = text
            payload["ts"] = int(time.time())
        if data is not None:
            payload["data"] = data
        lines.append(f"data: {json.dumps(payload, ensure_ascii=False)}\n\n")

    score = user_profile.get("score", "?")
    province = user_profile.get("province", "?")
    english = user_profile.get("english_score", "?")
    vision = user_profile.get("vision_status", "正常")
    rank = user_profile.get("rank", "?")

    engine_label = "🤖 DeepSeek AI" if (use_ai and api_key) else "📋 智能规则引擎"
    emit("log", f"[INIT] 建立安全连接... {engine_label} 就绪")
    emit("log", f"[PROFILE] 考生档案: 总分{score} | {province} | 英语{english} | 视力{vision} | 位次{rank}")
    emit("log", f"[TARGETS] 本次审查 {len(targets)} 个志愿目标")
    emit("log", "────────────────────────────────")

    for i, t in enumerate(targets):
        univ = t.get("university", "未知大学")
        major = t.get("major", "未知专业")
        emit("log", f">>> [{i+1}/{len(targets)}] 审查: 【{univ}】{major}")
        emit("log", f"   [RAG] 检索《{univ}2026招生章程》全文...")
        emit("log", f"   [MATCH] 核对: 单科成绩 ≥ 门槛? 体检合格? 语种限制?")

    emit("log", "────────────────────────────────")
    emit("log", "[SUMMARY] 正在汇总结果...")
    emit("log", "[COMPLETE] 审查完毕，生成诊断报告...")

    # 生成审查结果
    if use_ai and api_key:
        results = _ai_batch_check(user_profile, targets, api_key)
    else:
        results = [{**t, **mock_risk(t.get("university",""), t.get("major",""), user_profile)} for t in targets]

    danger_n = sum(1 for r in results if r.get("status") == "DANGER")
    warn_n = sum(1 for r in results if r.get("status") == "WARNING")
    pass_n = sum(1 for r in results if r.get("status") == "PASS")
    emit("log", f"[RESULT] 极高风险:{danger_n} | 需关注:{warn_n} | 通过:{pass_n}")

    emit("result", data=results)
    emit("done")

    return "".join(lines)


def _ai_batch_check(user_profile: dict, targets: list, api_key: str) -> list[dict]:
    """
    使用 httpx 同步调用 DeepSeek API 批量审查。
    如果 httpx 不可用或调用失败，回退到 mock_risk。
    """
    try:
        import httpx
    except ImportError:
        return [{**t, **mock_risk(t.get("university",""), t.get("major",""), user_profile)} for t in targets]

    api_url = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    profile_str = json.dumps(user_profile, ensure_ascii=False)

    system_prompt = """你是一位资深的高考志愿填报风险管理专家。
请审查以下志愿目标是否存在退档风险。关注：
1. 体检限制（色盲/色弱报临床/口腔→DANGER）
2. 单科成绩门槛（英语<110报外语类→WARNING）
3. 低偏好专业（土木/农学/护理→WARNING）
4. 无限制→PASS
请返回 JSON: {"status":"DANGER|WARNING|PASS","reason":"...","matched_clause":"..."}"""

    results = []
    for t in targets:
        univ = t.get("university", "")
        major = t.get("major", "")
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"【考生】{profile_str}\n【大学】{univ}\n【专业】{major}\n请返回纯 JSON（不要 Markdown 代码块）:"},
        ]
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.post(api_url, json={
                    "model": model,
                    "messages": messages,
                    "temperature": 0.1,
                    "max_tokens": 500,
                }, headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                })
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"].strip()
                if content.startswith("```"):
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:]
                parsed = json.loads(content)
                results.append({**t, "status": parsed.get("status","UNKNOWN").upper(), "reason": parsed.get("reason",""), "matched_clause": parsed.get("matched_clause","")})
            else:
                results.append({**t, **mock_risk(univ, major, user_profile)})
        except Exception:
            results.append({**t, **mock_risk(univ, major, user_profile)})

    return results


# =============================================================
# HTTP Handler
# =============================================================

class MockHandler(BaseHTTPRequestHandler):
    def _set_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._set_cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_sse(self, text: str):
        body = text.encode("utf-8")
        self.send_response(200)
        self._set_cors()
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length))

    def do_OPTIONS(self):
        self.send_response(204)
        self._set_cors()
        self.end_headers()

    def _serve_static(self, path):
        """Serve static files from project root."""
        import os
        ROOT = os.path.dirname(os.path.abspath(__file__))
        # Security: prevent path traversal
        safe_path = os.path.normpath(path.lstrip('/'))
        file_path = os.path.join(ROOT, safe_path)
        if not file_path.startswith(ROOT):
            self.send_error(403)
            return
        if not os.path.isfile(file_path):
            self.send_error(404)
            return
        ext = os.path.splitext(file_path)[1]
        mime_map = {'.html':'text/html','.js':'application/javascript','.css':'text/css','.json':'application/json','.png':'image/png','.svg':'image/svg+xml','.ico':'image/x-icon'}
        content_type = mime_map.get(ext, 'application/octet-stream')
        with open(file_path, 'rb') as f:
            data = f.read()
        self.send_response(200)
        self._set_cors()
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # Static file serving
        if path == "/" or path == "/demo.html":
            self._serve_static("/demo.html")
            return

        if path == "/health":
            self._send_json({"status": "ok"})

        elif path == "/api/check-risk/stream":
            qs = parse_qs(parsed.query)
            profile_json = qs.get("profile_json", ["{}"])[0]
            targets_json = qs.get("targets_json", ["[]"])[0]
            use_ai = qs.get("use_ai", ["false"])[0] == "true"
            try:
                user_profile = json.loads(profile_json)
                targets = json.loads(targets_json)
            except json.JSONDecodeError:
                self._send_json({"detail": "JSON parse error"}, 400)
                return
            sse_text = generate_sse_stream(user_profile, targets, use_ai=use_ai)
            self._send_sse(sse_text)

        else:
            self._send_json({"detail": "Not Found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        body = self._read_body()

        if path == "/api/check-risk":
            targets = body.get("targets", [])
            user_profile = body.get("profile", {})
            results = [{**t, **mock_risk(t.get("university",""), t.get("major",""), user_profile)} for t in targets]
            self._send_json({"total": len(results), "results": results})

        elif path == "/api/leakage-radar":
            self._send_json(MOCK_RADAR_DATA)

        elif path == "/api/profile":
            self._send_json({"message": "档案已保存", **body})

        else:
            self._send_json({"detail": "Not Found"}, 404)

    def log_message(self, format, *args):
        print(f"[{time.strftime('%H:%M:%S')}] {args[0]}")


# =============================================================
# Main
# =============================================================

if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), MockHandler)
    print(f"""
╔══════════════════════════════════════════════╗
║   🛡️  高考志愿狙击手 Mock Server v0.2      ║
╠══════════════════════════════════════════════╣
║  监听: http://0.0.0.0:{PORT}                   ║
║                                            ║
║  GET  /api/check-risk/stream  SSE 流式探雷  ║
║  POST /api/check-risk         JSON 探雷     ║
║  POST /api/leakage-radar      捡漏雷达      ║
║  POST /api/profile            用户档案      ║
║  GET  /health                 健康检查      ║
║                                            ║
║  🌐 Vue 3 前端: http://localhost:5173         ║
║  📄 或直接打开 demo.html (旧版保持兼容)      ║
╚══════════════════════════════════════════════╝
""")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Mock Server 已停止")
        server.shutdown()

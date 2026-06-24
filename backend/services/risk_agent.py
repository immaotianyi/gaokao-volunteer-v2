"""
志愿审核 AI Agent — 多轮推理 + 工具调用 + 知识检索

架构设计:
  Agent 不是一次性调用 AI，而是:
    1. 理解考生档案 + 志愿目标
    2. 自主选择需要的知识工具（招生章程、体检规则、单科规则、历年数据）
    3. 多轮推理，逐条验证
    4. 输出结构化审核报告（含条款引用、风险等级、详细理由）

可复用设计:
  - BaseAgent: 通用 Agent 基类（可复用到其他场景）
  - RiskAuditAgent: 志愿审核专用 Agent
  - ToolRegistry: 工具注册中心，支持热插拔

调用方式:
  agent = RiskAuditAgent(llm_client=your_llm)
  result = await agent.audit(user_profile, targets)
  # 或者流式:
  async for event in agent.audit_stream(user_profile, targets):
      yield event
"""
import asyncio
import json
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncGenerator, Callable, Optional


# ════════════════════════════════════════════════════════════════
# 基础类型定义
# ════════════════════════════════════════════════════════════════

class RiskLevel(str, Enum):
    PASS = "PASS"
    WARNING = "WARNING"
    DANGER = "DANGER"
    UNKNOWN = "UNKNOWN"


@dataclass
class AuditResult:
    """单个审核结果"""
    university: str
    major: str
    status: RiskLevel
    reason: str
    matched_clause: str = ""
    evidence: list[str] = field(default_factory=list)  # 引用的条款原文
    confidence: float = 1.0  # 置信度 0-1


@dataclass
class ToolResult:
    """工具调用返回"""
    success: bool
    data: Any
    error: str = ""


@dataclass
class AgentEvent:
    """Agent 流式事件"""
    type: str  # "thinking" | "tool_call" | "tool_result" | "conclusion" | "done"
    content: str
    data: Any = None
    ts: float = field(default_factory=time.time)


# ════════════════════════════════════════════════════════════════
# 知识库工具定义
# ════════════════════════════════════════════════════════════════

class ToolRegistry:
    """
    工具注册中心 — 管理所有可用的审核工具。
    支持运行时注册/注销，方便热插拔。
    """

    def __init__(self):
        self._tools: dict[str, dict] = {}
        self._handlers: dict[str, Callable] = {}

    def register(self, name: str, description: str, parameters: dict, handler: Callable):
        """注册一个工具"""
        self._tools[name] = {
            "name": name,
            "description": description,
            "parameters": parameters,
        }
        self._handlers[name] = handler

    def unregister(self, name: str):
        """注销一个工具"""
        self._tools.pop(name, None)
        self._handlers.pop(name, None)

    def get_tools_schema(self) -> list[dict]:
        """获取所有工具的 schema，用于注入 LLM prompt"""
        return list(self._tools.values())

    async def call(self, name: str, **kwargs) -> ToolResult:
        """调用工具"""
        handler = self._handlers.get(name)
        if not handler:
            return ToolResult(success=False, data=None, error=f"未知工具: {name}")
        try:
            if asyncio.iscoroutinefunction(handler):
                result = await handler(**kwargs)
            else:
                result = handler(**kwargs)
            return ToolResult(success=True, data=result)
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))


# ════════════════════════════════════════════════════════════════
# 通用 Agent 基类（可复用）
# ════════════════════════════════════════════════════════════════

class BaseAgent(ABC):
    """
    通用 AI Agent 基类。
    子类只需实现:
      - build_system_prompt(): 构建系统提示词
      - build_task_prompt(): 构建任务提示词
      - parse_response(): 解析 LLM 返回
    """

    def __init__(self, llm_client: Any, max_tool_rounds: int = 5, llm_timeout: float = 30.0):
        self.llm = llm_client
        self.tools = ToolRegistry()
        self.max_tool_rounds = max_tool_rounds
        self.llm_timeout = llm_timeout  # 每次 LLM 调用的超时秒数
        self._conversation_history: list[dict] = []

    def register_tools(self):
        """子类在此注册工具"""
        pass

    @abstractmethod
    def build_system_prompt(self) -> str:
        """构建系统级提示词（角色设定 + 规则）"""
        ...

    @abstractmethod
    def build_task_prompt(self, **kwargs) -> str:
        """构建任务级提示词（具体审核目标）"""
        ...

    @abstractmethod
    def parse_response(self, response: str) -> Any:
        """解析 LLM 输出为结构化数据"""
        ...

    async def _call_llm(self, messages: list[dict]) -> str:
        """
        调用 LLM。带超时保护，防止单次 API 调用阻塞整个请求。
        支持: OpenAI API / Dify / 本地模型 / Mock
        """
        async def _do_call():
            if hasattr(self.llm, "chat"):
                return await self.llm.chat(messages)
            elif hasattr(self.llm, "completion"):
                prompt = "\n".join([m["content"] for m in messages])
                return await self.llm.completion(prompt)
            else:
                raise NotImplementedError("LLM client 必须实现 chat() 或 completion() 方法")

        try:
            return await asyncio.wait_for(_do_call(), timeout=self.llm_timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"LLM 调用超时（>{self.llm_timeout}s），请检查 API 服务状态")

    async def run(self, **task_kwargs) -> Any:
        """
        执行 Agent 主循环:
          1. 构建 system + task prompt
          2. LLM 判断是否需要调用工具
          3. 调用工具获取知识
          4. LLM 综合推理给出结论
          5. 如有必要，继续多轮推理
        """
        system_prompt = self.build_system_prompt()
        task_prompt = self.build_task_prompt(**task_kwargs)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task_prompt},
        ]

        tool_schemas = self.tools.get_tools_schema()
        if tool_schemas:
            tools_desc = json.dumps(tool_schemas, ensure_ascii=False, indent=2)
            messages.append({
                "role": "system",
                "content": f"你可以使用以下工具获取信息:\n{tools_desc}\n\n"
                           f"当需要查询信息时，请严格按 JSON 格式回复:\n"
                           f'{{"action":"tool_call","tool":"工具名","args":{{}}}}\n'
                           f"当推理完成时回复:\n"
                           f'{{"action":"final_answer","result":...}}',
            })

        for _round in range(self.max_tool_rounds):
            try:
                response = await self._call_llm(messages)
            except TimeoutError as e:
                return {"total": 0, "summary": {}, "results": [], "error": str(e)}

            messages.append({"role": "assistant", "content": response})

            # 尝试解析 action
            action = self._extract_action(response)

            if action and action.get("action") == "tool_call":
                tool_name = action.get("tool")
                tool_args = action.get("args", {})
                result = await self.tools.call(tool_name, **tool_args)
                messages.append({
                    "role": "system",
                    "content": f"工具 {tool_name} 返回: {json.dumps(result.data, ensure_ascii=False) if result.success else result.error}",
                })
                continue

            if action and action.get("action") == "final_answer":
                return self.parse_response(action.get("result", response))

            # 未识别 action，尝试直接解析
            return self.parse_response(response)

        # 超过最大轮次，返回最后响应
        return self.parse_response(messages[-1].get("content", ""))

    async def run_stream(self, **task_kwargs) -> AsyncGenerator[AgentEvent, None]:
        """流式执行，逐事件推送"""
        yield AgentEvent(type="thinking", content="正在分析考生档案与志愿目标...")

        system_prompt = self.build_system_prompt()
        task_prompt = self.build_task_prompt(**task_kwargs)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task_prompt},
        ]

        tool_schemas = self.tools.get_tools_schema()
        if tool_schemas:
            tools_desc = json.dumps(tool_schemas, ensure_ascii=False, indent=2)
            messages.append({
                "role": "system",
                "content": f"可用工具:\n{tools_desc}\n\n"
                           f'需要查询时回复 JSON: {{"action":"tool_call","tool":"工具名","args":{{}}}}\n'
                           f'推理完成回复: {{"action":"final_answer","result":...}}',
            })

        for _round in range(self.max_tool_rounds):
            try:
                response = await self._call_llm(messages)
            except TimeoutError as e:
                yield AgentEvent(type="conclusion", content="LLM 调用超时", data={"error": str(e)})
                yield AgentEvent(type="done", content="")
                return

            messages.append({"role": "assistant", "content": response})

            action = self._extract_action(response)

            if action and action.get("action") == "tool_call":
                tool_name = action.get("tool")
                tool_args = action.get("args", {})
                yield AgentEvent(
                    type="tool_call",
                    content=f"调用知识库: {tool_name}",
                    data={"tool": tool_name, "args": tool_args},
                )
                result = await self.tools.call(tool_name, **tool_args)
                yield AgentEvent(
                    type="tool_result",
                    content=f"{tool_name} 返回结果",
                    data=result.data if result.success else {"error": result.error},
                )
                messages.append({
                    "role": "system",
                    "content": f"工具返回: {json.dumps(result.data, ensure_ascii=False) if result.success else result.error}",
                })
                continue

            if action and action.get("action") == "final_answer":
                parsed = self.parse_response(action.get("result", response))
                yield AgentEvent(type="conclusion", content="审核完成", data=parsed)
                yield AgentEvent(type="done", content="")
                return

            parsed = self.parse_response(response)
            yield AgentEvent(type="conclusion", content="审核完成", data=parsed)
            yield AgentEvent(type="done", content="")
            return

        parsed = self.parse_response(messages[-1].get("content", ""))
        yield AgentEvent(type="conclusion", content="审核完成", data=parsed)
        yield AgentEvent(type="done", content="")

    def _extract_action(self, response: str) -> Optional[dict]:
        """从 LLM 响应中提取 JSON action。

        支持格式:
          1. 纯 JSON: {"action":"tool_call",...}
          2. Markdown 代码块: ```json {...} ```
          3. 嵌套在文本中: 一些文字 {"action":"tool_call",...} 更多文字
          4. DeepSeek thinking 模式: 思考内容 + JSON
        """
        import re

        # 1. 尝试直接解析（DeepSeek V4 Flash thinking 模式可能直接返回 JSON）
        try:
            data = json.loads(response)
            if "action" in data:
                return data
        except json.JSONDecodeError:
            pass

        # 2. 提取 Markdown 代码块中的 JSON
        code_block_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', response, re.DOTALL)
        if code_block_match:
            try:
                data = json.loads(code_block_match.group(1).strip())
                if "action" in data:
                    return data
            except json.JSONDecodeError:
                pass

        # 3. 提取任意位置的 JSON 对象（支持嵌套）
        # 找最外层的 { ... }
        brace_depth = 0
        start = -1
        for i, ch in enumerate(response):
            if ch == '{':
                if brace_depth == 0:
                    start = i
                brace_depth += 1
            elif ch == '}':
                brace_depth -= 1
                if brace_depth == 0 and start >= 0:
                    candidate = response[start:i+1]
                    try:
                        data = json.loads(candidate)
                        if "action" in data:
                            return data
                    except json.JSONDecodeError:
                        pass
                    start = -1

        return None


# ════════════════════════════════════════════════════════════════
# 规则加载（单一来源：audit_rules.py）
# ════════════════════════════════════════════════════════════════

def _load_rules():
    """延迟加载 audit_rules，支持多种导入路径。"""
    try:
        from services.audit_rules import (
            BODY_CHECK_RULES,
            SUBJECT_SCORE_RULES,
            LOW_PREFERENCE_RULES,
            SUBJECT_ELECTION_RULES,
            RiskSeverity,
        )
    except ImportError:
        from backend.services.audit_rules import (
            BODY_CHECK_RULES,
            SUBJECT_SCORE_RULES,
            LOW_PREFERENCE_RULES,
            SUBJECT_ELECTION_RULES,
            RiskSeverity,
        )
    return BODY_CHECK_RULES, SUBJECT_SCORE_RULES, LOW_PREFERENCE_RULES, SUBJECT_ELECTION_RULES, RiskSeverity


# ── 工具处理函数（全部使用 audit_rules.py 的 dataclass）───────

def _match_body_check_rule(major: str):
    """在 BODY_CHECK_RULES 中按 trigger_keywords 匹配专业。"""
    rules, _, _, _, _ = _load_rules()
    for rule in rules:
        if any(kw in major for kw in rule.trigger_keywords):
            return {
                "conditions": rule.trigger_conditions.get("vision_status", []),
                "clause": rule.clause,
                "text": rule.clause_text,
                "severity": rule.severity.value,
            }
    return None


def _match_subject_score_rules(major: str) -> list[dict]:
    """在 SUBJECT_SCORE_RULES 中按 keywords 匹配专业。"""
    _, rules, _, _, _ = _load_rules()
    matched = []
    for rule in rules:
        if any(kw in major for kw in rule.keywords):
            matched.append({
                "keywords": rule.keywords,
                "subject": rule.subject,
                "field": rule.score_field,
                "threshold": rule.default_threshold,
                "clause": rule.clause,
                "text": rule.description,
                "severity": "WARNING",
            })
    return matched


def _match_low_preference(major: str) -> Optional[dict]:
    """在 LOW_PREFERENCE_RULES 中按 keywords 匹配专业。"""
    _, _, rules, _, _ = _load_rules()
    for rule in rules:
        if any(kw in major for kw in rule["keywords"]):
            return {"category": rule["category"], "reason": rule["reason"]}
    return None


def _match_subject_election(major: str) -> Optional[str]:
    """在 SUBJECT_ELECTION_RULES 中按 key 匹配专业。"""
    _, _, _, rules, _ = _load_rules()
    for key, val in rules.items():
        if key in major:
            return val
    return None


def tool_search_enrollment_rules(major: str, university: str = "") -> dict:
    """
    检索招生章程规则：体检限制、单科限制、选科要求。
    规则数据全部来自 audit_rules.py（单一来源）。
    """
    return {
        "major": major,
        "university": university or "通用规则（建议查看目标院校招生章程获取个性化条款）",
        "body_check": _match_body_check_rule(major),
        "subject_requirements": _match_subject_score_rules(major),
        "subject_election": _match_subject_election(major),
        "low_preference": _match_low_preference(major),
    }


def tool_check_vision_risk(vision_status: str, major: str) -> dict:
    """专项工具：检查视力/色觉相关风险（规则来自 audit_rules.py）。"""
    if vision_status == "正常":
        return {"risk": False, "message": "视力及色觉正常，无体检限制。"}

    rule = _match_body_check_rule(major)
    if rule:
        return {
            "risk": True,
            "severity": rule["severity"],
            "clause": rule["clause"],
            "detail": rule["text"],
            "message": f"您的体检状况为「{vision_status}」，该专业{rule['text']}",
        }

    return {"risk": False, "message": f"该专业对「{vision_status}」无明确体检限制。"}


def tool_check_subject_score(score: int, threshold: int, subject: str, major: str) -> dict:
    """专项工具：检查单科成绩是否达标。"""
    if score >= threshold:
        return {
            "risk": False,
            "message": f"{subject}单科成绩{score}分，满足{threshold}分门槛。",
        }
    else:
        return {
            "risk": True,
            "message": f"{subject}单科成绩{score}分，未达到该专业通常要求的{threshold}分门槛，存在退档风险。",
            "gap": threshold - score,
        }


def tool_lookup_historical_data(university: str, major: str, province: str) -> dict:
    """专项工具：查询历史录取数据（Mock 实现，实际应查数据库）。"""
    mock_history = {
        "中山大学": {"临床医学": {"2025_rank": 3200, "2025_score": 648, "trend": "稳定"}},
        "华南理工": {"计算机": {"2025_rank": 5800, "2025_score": 632, "trend": "上升"}},
        "深圳大学": {"计算机科学": {"2025_rank": 18000, "2025_score": 595, "trend": "上升"}},
    }

    univ_data = mock_history.get(university, {})
    major_data = univ_data.get(major)

    if major_data:
        return {"found": True, "university": university, "major": major, **major_data}
    else:
        return {
            "found": False,
            "message": f"暂无{university}「{major}」在{province}的历史录取数据，建议参考考试院公布的历年投档线。",
        }


# ════════════════════════════════════════════════════════════════
# 志愿审核专用 Agent
# ════════════════════════════════════════════════════════════════

class RiskAuditAgent(BaseAgent):
    """
    志愿审核 Agent — 继承 BaseAgent，注册志愿审核专用工具。

    支持多种 Prompt 模式:
      - default: 通用审核
      - strict: 严格审查（单科/体检从紧）
      - quick: 快速扫描（仅硬性退档）
      - detail: 详细诊断（含调剂分析 + 录取概率）
    """

    def __init__(self, llm_client: Any = None, max_tool_rounds: int = 3, prompt_mode: str = "default"):
        super().__init__(llm_client, max_tool_rounds)
        self.prompt_mode = prompt_mode
        self.register_tools()

    def register_tools(self):
        """注册志愿审核专用工具"""
        self.tools.register(
            name="search_enrollment_rules",
            description="检索某专业的招生章程规则，包括体检限制、单科成绩要求、选科要求、调剂风险等",
            parameters={"major": "专业名称（如：临床医学）", "university": "大学名称（可选）"},
            handler=tool_search_enrollment_rules,
        )
        self.tools.register(
            name="check_vision_risk",
            description="检查考生的视力/色觉状况是否满足目标专业的体检要求",
            parameters={"vision_status": "考生视力状况（正常/色盲/色弱/近视）", "major": "目标专业名称"},
            handler=tool_check_vision_risk,
        )
        self.tools.register(
            name="check_subject_score",
            description="检查考生单科成绩是否满足目标专业的单科要求",
            parameters={
                "score": "考生该科成绩",
                "threshold": "专业要求的最低分数",
                "subject": "科目名称（英语/数学/语文）",
                "major": "目标专业名称",
            },
            handler=tool_check_subject_score,
        )
        self.tools.register(
            name="lookup_historical_data",
            description="查询某大学某专业的历史录取数据（最低排名、最低分数、趋势）",
            parameters={
                "university": "大学名称",
                "major": "专业名称",
                "province": "省份",
            },
            handler=tool_lookup_historical_data,
        )

    def build_system_prompt(self) -> str:
        try:
            from services.audit_prompts import get_prompt
        except ImportError:
            from backend.services.audit_prompts import get_prompt
        return get_prompt(self.prompt_mode)

    def build_task_prompt(self, **kwargs) -> str:
        user_profile = kwargs.get("user_profile", {})
        targets = kwargs.get("targets", [])

        profile_str = json.dumps(user_profile, ensure_ascii=False, indent=2)
        targets_str = json.dumps(targets, ensure_ascii=False, indent=2)

        return f"""请审查以下考生志愿目标：

【考生档案】
{profile_str}

【志愿列表】
{targets_str}

请按照以下步骤逐条审查：
1. 对每个志愿目标，首先调用 search_enrollment_rules 获取该专业的招生规则。
2. 如果体检状况非"正常"，调用 check_vision_risk 专项检查。
3. 如果单科成绩可能不达标，调用 check_subject_score 逐科核对。
4. 可选：调用 lookup_historical_data 查询历史录取趋势辅助判断。

最终请输出结构化 JSON，格式如下：
{{
  "action": "final_answer",
  "result": {{
    "total": 数量,
    "summary": {{
      "danger": 极高风险数量,
      "warning": 需关注数量,
      "pass": 通过数量
    }},
    "results": [
      {{
        "university": "大学名",
        "major": "专业名",
        "status": "PASS|WARNING|DANGER|UNKNOWN",
        "reason": "详细审核理由",
        "matched_clause": "引用的具体条款",
        "evidence": ["条款原文1", "条款原文2"],
        "confidence": 0.95
      }}
    ]
  }}
}}"""

    def parse_response(self, response: Any) -> dict:
        """解析 LLM 输出为 AuditResult 列表"""
        if isinstance(response, dict) and "results" in response:
            return response

        if isinstance(response, dict) and "result" in response:
            return response["result"]

        if isinstance(response, str):
            try:
                return json.loads(response)
            except json.JSONDecodeError:
                pass

        return {"total": 0, "summary": {}, "results": [], "raw": str(response)}

    async def audit(self, user_profile: dict, targets: list[dict]) -> dict:
        """同步审核接口"""
        return await self.run(user_profile=user_profile, targets=targets)

    async def audit_stream(
        self, user_profile: dict, targets: list[dict]
    ) -> AsyncGenerator[AgentEvent, None]:
        """流式审核接口"""
        async for event in self.run_stream(user_profile=user_profile, targets=targets):
            yield event


# ════════════════════════════════════════════════════════════════
# LLM 客户端实现
# ════════════════════════════════════════════════════════════════

class MockLLMClient:
    """
    Mock LLM 客户端 — 模拟 Agent 多轮推理。
    通过真正调用知识库工具生成审核结果，而非返回固定空壳。

    工作流程:
      第 1 轮: 对每个目标发出 tool_call → search_enrollment_rules
      第 2 轮: 根据规则结果 + 考生档案，逐条判断 DANGER/WARNING/PASS
      最终: 返回结构化 final_answer
    """

    def __init__(self):
        self._tool_phase = 0  # 0=等待工具调用, 1=推理结论

    async def chat(self, messages: list[dict]) -> str:
        """模拟 Agent 多轮推理，调用工具 + 生成审核结果。"""
        # 提取 user message 中的考生档案和志愿目标
        user_profile, targets = self._extract_task(messages)

        if not targets:
            return json.dumps({"action": "final_answer", "result": {"total": 0, "results": []}})

        # 检查是否已经有工具返回（说明这是第 2 轮）
        has_tool_results = any(
            m["role"] == "system" and "工具" in m.get("content", "")
            for m in messages
        )

        if not has_tool_results:
            # 第 1 轮: 对每个目标发出工具调用
            # 实际只对第一个目标发 tool_call（简化模拟）
            t = targets[0]
            return json.dumps({
                "action": "tool_call",
                "tool": "search_enrollment_rules",
                "args": {"major": t.get("major", ""), "university": t.get("university", "")},
            }, ensure_ascii=False)

        # 第 2 轮: 收到工具结果，综合推理生成最终结论
        results = []
        for t in targets:
            major = t.get("major", "")
            university = t.get("university", "")
            result = self._judge(user_profile, university, major)
            results.append(result)

        danger_n = sum(1 for r in results if r["status"] == "DANGER")
        warn_n = sum(1 for r in results if r["status"] == "WARNING")
        pass_n = sum(1 for r in results if r["status"] == "PASS")

        return json.dumps({
            "action": "final_answer",
            "result": {
                "total": len(results),
                "summary": {"danger": danger_n, "warning": warn_n, "pass": pass_n},
                "results": results,
            },
        }, ensure_ascii=False)

    def _extract_task(self, messages: list[dict]) -> tuple[dict, list[dict]]:
        """从 messages 中提取考生档案和志愿目标。"""
        user_profile = {}
        targets = []
        import re
        for m in messages:
            if m["role"] != "user":
                continue
            content = m["content"]
            # 格式: 【考生档案】\n{json}\n\n【志愿列表】\n{json}
            if "【考生档案】" not in content:
                continue
            try:
                # 提取档案 JSON
                profile_match = re.search(r'【考生档案】\s*\n(\{.*?\})\s*\n', content, re.DOTALL)
                if profile_match:
                    user_profile = json.loads(profile_match.group(1))
                # 提取志愿列表 JSON
                targets_match = re.search(r'【志愿列表】\s*\n(\[.*?\])\s*\n', content, re.DOTALL)
                if targets_match:
                    targets = json.loads(targets_match.group(1))
                if user_profile and targets:
                    break
            except (json.JSONDecodeError, IndexError):
                pass
        return user_profile, targets

    def _judge(self, user_profile: dict, university: str, major: str) -> dict:
        """基于 audit_rules 规则 + 考生档案，模拟审核判断。"""
        rules = tool_search_enrollment_rules(major, university)

        vision = user_profile.get("vision_status", "正常")
        english = user_profile.get("english_score") or 0
        math = user_profile.get("math_score") or 0
        chinese = user_profile.get("chinese_score") or 0
        subjects = user_profile.get("subjects", "")

        # 1) 体检硬性退档
        body = rules.get("body_check")
        if body and vision != "正常":
            severity = body.get("severity", "WARNING")
            if severity == "DANGER":
                return {
                    "university": university,
                    "major": major,
                    "status": "DANGER",
                    "reason": f"该专业{body['text']}，您的体检显示为{vision}，存在极高退档风险。",
                    "matched_clause": body.get("clause", ""),
                    "evidence": [body.get("text", "")],
                    "confidence": 0.98,
                }
            else:
                return {
                    "university": university,
                    "major": major,
                    "status": "WARNING",
                    "reason": f"该专业{body['text']}，您的体检显示为{vision}，建议核实目标院校招生章程。",
                    "matched_clause": body.get("clause", ""),
                    "evidence": [body.get("text", "")],
                    "confidence": 0.85,
                }

        # 2) 选科不符
        election = rules.get("subject_election", "")
        if election and "纯文科" in election:
            if subjects and ("历史" in subjects or "地理" in subjects or "政治" in subjects) and "物理" not in subjects:
                return {
                    "university": university,
                    "major": major,
                    "status": "DANGER",
                    "reason": f"该专业{election}，您的选科{subjects}不满足要求，存在极高退档风险。",
                    "matched_clause": "各省教育考试院选科要求公告",
                    "evidence": [election],
                    "confidence": 0.99,
                }

        # 3) 单科成绩不达标
        subj_reqs = rules.get("subject_requirements", [])
        for req in subj_reqs:
            field = req.get("field", "")
            threshold = req.get("threshold", 0)
            subject_name = req.get("subject", "")
            if field == "english_score" and english < threshold:
                return {
                    "university": university,
                    "major": major,
                    "status": "WARNING",
                    "reason": f"该专业通常要求{subject_name}单科不低于{threshold}分，您当前为{english}分，存在退档风险。",
                    "matched_clause": req.get("clause", ""),
                    "evidence": [req.get("text", "")],
                    "confidence": 0.75,
                }
            if field == "math_score" and math < threshold:
                return {
                    "university": university,
                    "major": major,
                    "status": "WARNING",
                    "reason": f"该专业通常要求{subject_name}单科不低于{threshold}分，您当前为{math}分，存在退档风险。",
                    "matched_clause": req.get("clause", ""),
                    "evidence": [req.get("text", "")],
                    "confidence": 0.75,
                }
            if field == "chinese_score" and chinese < threshold:
                return {
                    "university": university,
                    "major": major,
                    "status": "WARNING",
                    "reason": f"该专业可能要求{subject_name}单科不低于{threshold}分，您当前为{chinese}分，建议核实。",
                    "matched_clause": req.get("clause", ""),
                    "evidence": [req.get("text", "")],
                    "confidence": 0.65,
                }

        # 4) 低偏好专业
        low_pref = rules.get("low_preference")
        if low_pref:
            return {
                "university": university,
                "major": major,
                "status": "WARNING",
                "reason": f"该专业属于低偏好调剂方向（{low_pref.get('category', '')}），{low_pref.get('reason', '')}",
                "matched_clause": "",
                "evidence": [],
                "confidence": 0.70,
            }

        # 5) 通过
        return {
            "university": university,
            "major": major,
            "status": "PASS",
            "reason": "未发现显性限制，体检及单科成绩均符合该专业招生章程要求。",
            "matched_clause": "",
            "evidence": [],
            "confidence": 0.90,
        }


class DifyLLMClient:
    """
    Dify LLM 客户端 — 对接 Dify AI 工作流。
    兼容现有的 DIFY_API_URL / DIFY_API_TOKEN 配置。
    """

    def __init__(
        self,
        api_url: str = "",
        api_token: str = "",
        timeout: int = 30,
    ):
        import httpx
        self.api_url = api_url or os.getenv("DIFY_API_URL", "https://api.dify.ai/v1/workflows/run")
        self.api_token = api_token or os.getenv("DIFY_API_TOKEN", "")
        self.timeout = timeout

    async def chat(self, messages: list[dict]) -> str:
        """通过 Dify API 获取响应"""
        import httpx

        # 提取用户问题
        user_content = ""
        for m in reversed(messages):
            if m["role"] == "user":
                user_content = m["content"]
                break

        payload = {
            "inputs": {
                "messages": messages,
                "query": user_content,
            },
            "response_mode": "blocking",
            "user": "gaokao-risk-agent",
        }

        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(self.api_url, json=payload, headers=headers)
            if response.status_code == 200:
                data = response.json()
                outputs = data.get("data", {}).get("outputs", {})
                if isinstance(outputs, dict):
                    return outputs.get("text", outputs.get("result", json.dumps(outputs)))
                return str(outputs)
            else:
                raise Exception(f"Dify API error: {response.status_code}")


class OpenAICompatibleClient:
    """
    OpenAI 兼容客户端 — 支持 OpenAI / 混元 / 通义千问 / DeepSeek 等兼容 API。

    V4 Agent 使用 DeepSeek V4 Flash (deepseek-v4-flash，开启 thinking 模式作为推理引擎)。
    也可指定 deepseek-chat 走 legacy 路径。
    """

    def __init__(
        self,
        api_url: str = "",
        api_key: str = "",
        model: str = "deepseek-v4-flash",
        timeout: int = 60,
    ):
        self.api_url = api_url or os.getenv("LLM_API_URL", "https://api.deepseek.com/v1/chat/completions")
        self.api_key = api_key or os.getenv("LLM_API_KEY", "")
        self.model = model or os.getenv("LLM_MODEL", "deepseek-v4-flash")
        self.timeout = timeout

    async def chat(self, messages: list[dict]) -> str:
        import httpx

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 4096,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(self.api_url, json=payload, headers=headers)
            if response.status_code == 200:
                data = response.json()
                return data["choices"][0]["message"]["content"]
            else:
                raise Exception(f"LLM API error {response.status_code}: {response.text}")


# ════════════════════════════════════════════════════════════════
# 工厂函数 — 快速创建 Agent
# ════════════════════════════════════════════════════════════════

def create_risk_agent(
    provider: str = "mock",
    api_url: str = "",
    api_key: str = "",
    model: str = "",
    prompt_mode: str = "default",
) -> RiskAuditAgent:
    """
    工厂函数：根据配置创建 RiskAuditAgent。

    用法:
      agent = create_risk_agent("mock")                                    # Mock
      agent = create_risk_agent("dify")                                    # Dify
      agent = create_risk_agent("openai", api_key="sk-xxx")                # OpenAI
      agent = create_risk_agent("openai", api_url="...", api_key="...",
                                model="deepseek-chat", prompt_mode="strict")  # DeepSeek 严格模式

    prompt_mode 可选:
      - "default": 通用审核
      - "strict":  严格审查
      - "quick":   快速扫描
      - "detail":  详细诊断
    """
    if provider == "mock" or (provider == "dify" and not (api_key or os.getenv("DIFY_API_TOKEN"))):
        llm = MockLLMClient()
    elif provider == "dify":
        llm = DifyLLMClient(api_url=api_url, api_token=api_key)
    elif provider in ("openai", "hunyuan", "qwen", "deepseek"):
        llm = OpenAICompatibleClient(api_url=api_url, api_key=api_key, model=model)
    else:
        raise ValueError(f"不支持的 LLM provider: {provider}")

    return RiskAuditAgent(llm_client=llm, prompt_mode=prompt_mode)

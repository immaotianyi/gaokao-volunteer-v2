"""
志愿审核 AI Agent — 测试脚本

验证 Agent 的创建、工具调用、流式推理是否正常工作。
启动方式:
  cd backend && python3 -m services.test_agent
  # 或从项目根:
  PYTHONPATH=backend python3 -m services.test_agent
"""
import asyncio
import json
import sys
import os
from pathlib import Path

# 确保 backend 目录在 sys.path 中
_backend_dir = str(Path(__file__).parent.parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from services.risk_agent import (
    create_risk_agent,
    MockLLMClient,
    ToolRegistry,
    tool_search_enrollment_rules,
    tool_check_vision_risk,
    tool_check_subject_score,
)


async def test_tools():
    """测试知识库工具是否正常"""
    print("\n" + "=" * 60)
    print("📋 测试 1: 知识库工具")
    print("=" * 60)

    # 测试体检规则检索
    result = tool_search_enrollment_rules("临床医学")
    print(f"\n✓ search_enrollment_rules('临床医学'):")
    print(f"  体检限制: {result['body_check']['severity'] if result['body_check'] else '无'}")
    print(f"  单科要求: {len(result['subject_requirements'])} 条")
    print(f"  选科要求: {result['subject_election']}")

    # 测试视力检查
    result = tool_check_vision_risk("色盲", "临床医学")
    print(f"\n✓ check_vision_risk('色盲', '临床医学'):")
    print(f"  风险: {result['risk']}, 等级: {result.get('severity', 'N/A')}")
    print(f"  详情: {result.get('detail', 'N/A')[:60]}...")

    # 测试单科检查
    result = tool_check_subject_score(95, 110, "英语", "翻译")
    print(f"\n✓ check_subject_score(95, 110, '英语', '翻译'):")
    print(f"  风险: {result['risk']}, 分差: {result.get('gap', 0)}")

    result = tool_check_subject_score(125, 120, "数学", "数学与应用数学")
    print(f"\n✓ check_subject_score(125, 120, '数学', '数学与应用数学'):")
    print(f"  风险: {result['risk']} (应通过)")


async def test_agent_creation():
    """测试 Agent 创建"""
    print("\n" + "=" * 60)
    print("📋 测试 2: Agent 创建")
    print("=" * 60)

    # Mock Agent
    agent = create_risk_agent("mock")
    print(f"\n✓ Mock Agent: {type(agent).__name__}")
    print(f"  工具数量: {len(agent.tools._tools)}")
    for name in agent.tools._tools:
        print(f"  - {name}")

    # 不同 Prompt 模式
    for mode in ["default", "strict", "quick", "detail"]:
        agent = create_risk_agent("mock", prompt_mode=mode)
        prompt = agent.build_system_prompt()
        print(f"\n✓ Prompt mode={mode}: {len(prompt)} 字符")


async def test_agent_audit():
    """测试 Agent 审核流程"""
    print("\n" + "=" * 60)
    print("📋 测试 3: Agent 审核")
    print("=" * 60)

    agent = create_risk_agent("mock")

    user_profile = {
        "province": "广东",
        "score": 565,
        "rank": 35000,
        "subjects": "物理+化学+生物",
        "english_score": 105,
        "math_score": 118,
        "vision_status": "色弱",
    }

    targets = [
        {"university": "南方医科大学", "major": "临床医学"},
        {"university": "广州大学", "major": "计算机科学"},
        {"university": "华南理工大学", "major": "土木工程"},
        {"university": "中山大学", "major": "园艺"},
    ]

    result = await agent.audit(user_profile=user_profile, targets=targets)
    print(f"\n✓ 审核完成: {json.dumps(result, ensure_ascii=False, indent=2)[:500]}...")


async def test_agent_stream():
    """测试 Agent 流式推理"""
    print("\n" + "=" * 60)
    print("📋 测试 4: Agent 流式推理")
    print("=" * 60)

    agent = create_risk_agent("mock")

    user_profile = {
        "province": "广东",
        "score": 620,
        "rank": 12000,
        "subjects": "物理+化学+地理",
        "english_score": 130,
        "math_score": 135,
        "vision_status": "正常",
    }

    targets = [
        {"university": "中山大学", "major": "临床医学"},
        {"university": "华南理工大学", "major": "人工智能"},
    ]

    print("\n流式事件:")
    async for event in agent.audit_stream(user_profile=user_profile, targets=targets):
        print(f"  [{event.type}] {event.content[:80]}")
        if event.data:
            print(f"          data: {str(event.data)[:100]}")


async def test_rule_based_fallback():
    """测试：当 Agent 异常时的规则引擎回退"""
    print("\n" + "=" * 60)
    print("📋 测试 5: 规则引擎直接调用 (现有逻辑)")
    print("=" * 60)

    from services.risk_checker import _mock_check

    user_profile = {
        "vision_status": "色盲",
        "english_score": 100,
        "math_score": 115,
    }

    test_cases = [
        ("南方医科大学", "临床医学"),
        ("华南理工大学", "计算机科学与技术"),
        ("广州大学", "土木工程"),
        ("深圳大学", "英语"),
    ]

    for univ, major in test_cases:
        result = _mock_check(user_profile, univ, major)
        status_icon = {"DANGER": "🔴", "WARNING": "🟡", "PASS": "🟢"}.get(result["status"], "?")
        print(f"  {status_icon} [{result['status']}] {univ} - {major}")
        print(f"     理由: {result['reason'][:80]}...")


async def main():
    print("╔══════════════════════════════════════════════════════╗")
    print("║   🛡️  志愿审核 AI Agent — 测试套件                  ║")
    print("╚══════════════════════════════════════════════════════╝")

    await test_tools()
    await test_agent_creation()
    await test_agent_audit()
    await test_agent_stream()
    await test_rule_based_fallback()

    print("\n" + "=" * 60)
    print("✅ 全部测试完成！")
    print("=" * 60)
    print("""
Agent 使用方式:

  # 1. Mock 模式（开发测试）
  agent = create_risk_agent("mock")
  result = await agent.audit(user_profile, targets)

  # 2. DeepSeek / OpenAI 模式
  agent = create_risk_agent("openai", api_key="sk-xxx", model="deepseek-chat")
  async for event in agent.audit_stream(user_profile, targets):
      print(event.type, event.content)

  # 3. SSE 流式 API
  GET /api/check-risk/agent-stream?provider=openai&prompt_mode=strict&...

  # 4. 同步 API
  POST /api/check-risk/agent?provider=openai&prompt_mode=default
""")


if __name__ == "__main__":
    asyncio.run(main())

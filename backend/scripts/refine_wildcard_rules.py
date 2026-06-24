#!/usr/bin/env python3
"""
针对性脚本：对 enrollment_rules.json 中仅有通配规则的大学，
从已有章程 TXT 中用 DeepSeek LLM 重新提取精细规则。

只处理 2026 年章程，不处理历史数据。

用法:
  python scripts/refine_wildcard_rules.py          # 处理所有通配规则大学
  python scripts/refine_wildcard_rules.py --limit 5 # 限制数量
  python scripts/refine_wildcard_rules.py --dry-run # 预览
"""
import os
import sys
import json
import re
import time
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
ZSZC_DIR = DATA_DIR / "zszc"
RULES_FILE = DATA_DIR / "enrollment_rules.json"

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"

SYSTEM_PROMPT = """你是一位高考招生政策分析专家。请从以下2026年招生章程中提取结构化的录取限制条件。

请严格按照以下 JSON 格式输出，只返回 JSON，不要任何额外文字：

{
  "university": "大学全名",
  "majors": [
    {
      "major_pattern": "可被正则匹配的专业名关键词，全部专业填 .*",
      "major_name": "人类可读的专业名",
      "body_check": {
        "color_blind": "DANGER|WARNING|null",
        "color_weak": "DANGER|WARNING|null",
        "color_distinguish": "DANGER|WARNING|null",
        "vision": "DANGER|WARNING|null",
        "height": "DANGER|WARNING|null",
        "clause": "章程中的原文条款"
      },
      "single_subject": {
        "english": {"min": 分数, "clause": "原文条款"},
        "math": {"min": 分数, "clause": "原文条款"},
        "chinese": {"min": 分数, "clause": "原文条款"}
      },
      "language_restriction": "仅限英语|仅限德语|仅限日语|null",
      "subject_election": "物理+化学|物理|不限|null",
      "notes": "其他重要限制"
    }
  ]
}

# 提取规则
1. 体检限制：搜索"色盲""色弱""视力""身高""不予录取""不宜就读"
2. 单科成绩：搜索"不低于""不少于""达到""分以上""外语""英语""数学""语文"
3. 语种限制：搜索"仅限""语种""外语语种""英语""日语""德语""俄语""限招"
4. 选科要求：搜索"选考科目""首选科目""再选科目""物理""化学""生物""历史""地理""政治""必选""科目要求"
5. 中外合作：搜索"中外合作""合作办学""不得转专业""只录取""单独投档"
6. 如果没有找到任何限制，body_check/single_subject/language_restriction 均填 null，notes 填"未发现显性限制"

# 重要
- 如果章程对不同专业有不同的限制，必须按专业分别输出多条 majors 条目
- 如果章程对所有专业的限制一致，使用一条 major_pattern: ".*" 的条目
- body_check 中 null 表示无限制。只有原文明确写了限制才填 DANGER 或 WARNING
- 区分"不予录取"（→ DANGER）和"不宜就读"（→ WARNING）
- 必须引用章程原文作为 clause，不要自己编造条款
- 如果章程引用了教育部体检指导意见但没有列出具体专业，在 notes 中标注"""


def load_rules() -> tuple[dict, list]:
    with open(RULES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("meta", {}), data.get("rules", [])


def save_rules(meta: dict, rules: list):
    meta["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    meta["total_universities"] = len(rules)
    with open(RULES_FILE, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "rules": rules}, f, ensure_ascii=False, indent=2)


def get_wildcard_universities(rules: list) -> list[dict]:
    """找出仅有通配规则的大学（2026年）"""
    result = []
    for rule in rules:
        year = rule.get("year", 0)
        if year != 2026:
            continue
        majors = rule.get("majors", [])
        if not majors:
            continue
        if all(m.get("major_pattern") == ".*" for m in majors):
            result.append(rule)
    return result


def get_chapter_text(university_name: str) -> tuple[str, list[str]]:
    """拼接某大学的全部 2026 章程分段"""
    safe_name = re.sub(r'[\\/:*?"<>|]', '_', university_name)
    segments = []
    source_files = []

    pattern = f"{safe_name}_2026招生章程_*.txt"
    for f in sorted(ZSZC_DIR.glob(pattern)):
        with open(f, "r", encoding="utf-8") as fh:
            content = fh.read()
            idx = content.find("=" * 60)
            if idx != -1:
                content = content[idx + 60:].strip()
            segments.append(content)
            source_files.append(f.name)

    return "\n\n".join(segments), source_files


def call_deepseek(chapter_text: str) -> dict | None:
    """调用 DeepSeek API"""
    import requests

    if not DEEPSEEK_API_KEY:
        return None

    # 截断
    max_chars = 50000
    if len(chapter_text) > max_chars:
        chapter_text = chapter_text[:max_chars] + "\n\n[章程过长已截断]"

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"章程全文：\n\n{chapter_text}"},
        ],
        "temperature": 0.1,
        "max_tokens": 4096,
        "response_format": {"type": "json_object"},
    }

    for attempt in range(3):
        try:
            resp = requests.post(DEEPSEEK_API_URL, headers=headers,
                                 json=payload, timeout=120)
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                content = re.sub(r'^```json\s*', '', content)
                content = re.sub(r'\s*```$', '', content)
                return json.loads(content)
            elif resp.status_code == 429:
                wait = min(30 * (attempt + 1), 120)
                print(f"    ⚠️ 限流, 等待{wait}s...")
                time.sleep(wait)
            else:
                print(f"    ⚠️ API {resp.status_code}: {resp.text[:100]}")
                time.sleep(10)
        except Exception as e:
            print(f"    ⚠️ API异常: {e}")
            time.sleep(10)
    return None


def validate_result(result: dict) -> list[str]:
    """验证提取结果"""
    errors = []
    if not result.get("university"):
        errors.append("缺少 university")
    majors = result.get("majors", [])
    if not isinstance(majors, list) or len(majors) == 0:
        errors.append("majors 非空数组")
        return errors
    for i, major in enumerate(majors):
        pattern = major.get("major_pattern", "")
        if pattern:
            try:
                re.compile(pattern)
            except re.error as e:
                errors.append(f"majors[{i}].major_pattern 非法: {e}")
    return errors


def main():
    parser = argparse.ArgumentParser(description="重新提取通配规则的精细规则")
    parser.add_argument("--limit", "-n", type=int, default=0, help="限制数量")
    parser.add_argument("--dry-run", action="store_true", help="预览模式")
    args = parser.parse_args()

    if not DEEPSEEK_API_KEY:
        print("❌ 未配置 DEEPSEEK_API_KEY")
        sys.exit(1)

    meta, rules = load_rules()
    wildcards = get_wildcard_universities(rules)
    print(f"通配规则大学: {len(wildcards)} 所")

    if args.limit > 0:
        wildcards = wildcards[:args.limit]

    if args.dry_run:
        print("\n[Dry Run] 待处理:")
        for w in wildcards:
            uni = w["university"]
            has_txt, _ = get_chapter_text(uni)
            print(f"  - {uni} (TXT: {'✅' if has_txt else '❌'})")
        return

    refined = 0
    for i, wildcard_rule in enumerate(wildcards):
        uni = wildcard_rule["university"]
        print(f"\n[{i+1}/{len(wildcards)}] {uni}")

        chapter_text, source_files = get_chapter_text(uni)
        if not chapter_text:
            print(f"  ⚠️ 无章程TXT, 跳过")
            continue

        print(f"  章程长度: {len(chapter_text)} 字符")

        result = call_deepseek(chapter_text)
        if result is None:
            print(f"  ❌ LLM 调用失败")
            continue

        errors = validate_result(result)
        if errors:
            print(f"  ⚠️ 验证问题: {errors[:3]}")

        # 补充元数据
        result["source_files"] = source_files
        result["year"] = 2026

        # 替换原规则
        for j, r in enumerate(rules):
            if r["university"] == uni and r.get("year") == 2026:
                rules[j] = result
                break

        # 统计
        majors = result.get("majors", [])
        wc = sum(1 for m in majors if m.get("major_pattern") == ".*")
        sp = len(majors) - wc
        print(f"  ✅ 提取: {len(majors)}条 (精细:{sp}, 通配:{wc})")
        refined += 1

        # 每 5 所保存
        if refined % 5 == 0:
            save_rules(meta, rules)
            print(f"  💾 已保存")

        time.sleep(2)

    save_rules(meta, rules)
    print(f"\n✅ 完成: {refined}/{len(wildcards)} 所重新提取")


if __name__ == "__main__":
    main()

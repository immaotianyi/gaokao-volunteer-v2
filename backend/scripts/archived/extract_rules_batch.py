#!/usr/bin/env python3
"""
从章程 TXT 文件中使用 DeepSeek LLM 提取结构化录取规则

用法:
  python scripts/extract_rules_batch.py                    # 处理所有未提取的大学
  python scripts/extract_rules_batch.py --university "北京大学"  # 处理指定大学
  python scripts/extract_rules_batch.py --limit 10          # 限制处理数量
  python scripts/extract_rules_batch.py --dry-run           # 预览模式, 不实际调用API
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

# DeepSeek API 配置
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"

SYSTEM_PROMPT = """你是一位高考招生政策分析专家。请从以下招生章程中提取结构化的录取限制条件。

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
      "notes": "其他重要限制（中外合作不得转专业等）"
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

# 重要注意事项
- 如果章程对不同专业有不同的限制，必须按专业分别输出多条 majors 条目
- 如果章程对所有专业的限制一致，使用一条 major_pattern: ".*" 的条目
- body_check 中 null 表示无限制，不要填默认值。只有原文明确写了限制才填 DANGER 或 WARNING
- single_subject 中如果某科无要求，不要包含该科
- 必须引用章程原文作为 clause，不要自己编造条款
- 区分"不予录取"（→ DANGER）和"不宜就读"（→ WARNING）
- 区分全校性规则和专业性规则：全校性的限制放在 major_pattern: ".*" 的条目中
- 如果章程引用了教育部体检指导意见但没有列出具体专业，在 notes 中标注，不要自己推测哪些专业受限"""


def get_chapter_full_text(university_name: str) -> tuple[str, list[str]]:
    """拼接某大学的所有 2026 章程分段为完整文本"""
    safe_name = re.sub(r'[\\/:*?"<>|]', '_', university_name)
    segments = []
    source_files = []

    for f in sorted(ZSZC_DIR.glob(f"{safe_name}_2026招生章程_*.txt")):
        with open(f, "r", encoding="utf-8") as fh:
            content = fh.read()
            # 去掉头部元数据
            idx = content.find("=" * 60)
            if idx != -1:
                content = content[idx + 60:].strip()
            segments.append(content)
            source_files.append(f.name)

    return "\n\n".join(segments), source_files


def call_deepseek_api(chapter_text: str, university_name: str) -> dict | None:
    """调用 DeepSeek API 提取结构化规则"""
    import requests

    if not DEEPSEEK_API_KEY:
        print(f"  ⚠️ 未配置 DEEPSEEK_API_KEY, 使用通配规则回退")
        return None

    # 截断过长文本 (DeepSeek 64K context, 留足余量)
    max_chars = 50000
    if len(chapter_text) > max_chars:
        chapter_text = chapter_text[:max_chars] + "\n\n[章程过长，已截断]"

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
                # 清理可能的 markdown 包裹
                content = re.sub(r'^```json\s*', '', content)
                content = re.sub(r'\s*```$', '', content)
                return json.loads(content)
            elif resp.status_code == 429:
                wait = min(30 * (attempt + 1), 120)
                print(f"  ⚠️ API 限流, 等待 {wait}s...")
                time.sleep(wait)
            else:
                print(f"  ⚠️ API 错误 {resp.status_code}: {resp.text[:200]}")
                time.sleep(10)
        except Exception as e:
            print(f"  ⚠️ API 调用异常: {e}")
            time.sleep(10)

    return None


def validate_extracted_rule(rule: dict) -> list[str]:
    """验证 LLM 提取的规则, 返回错误列表"""
    errors = []

    if not rule.get("university"):
        errors.append("缺少 university 字段")

    majors = rule.get("majors", [])
    if not isinstance(majors, list) or len(majors) == 0:
        errors.append("majors 必须是非空数组")
        return errors

    for i, major in enumerate(majors):
        prefix = f"majors[{i}]"

        # 检查 major_pattern 是否为合法正则
        pattern = major.get("major_pattern", "")
        if pattern:
            try:
                re.compile(pattern)
            except re.error as e:
                errors.append(f"{prefix}.major_pattern '{pattern}' 非法正则: {e}")

        # 检查 body_check
        body = major.get("body_check", {})
        if body:
            has_restriction = any(
                body.get(k) in ("DANGER", "WARNING")
                for k in ("color_blind", "color_weak", "color_distinguish",
                          "vision", "height")
            )
            clause = body.get("clause", "")
            if has_restriction and not clause:
                errors.append(f"{prefix}.body_check 有限制但 clause 为空")

        # 检查 single_subject
        single = major.get("single_subject", {})
        if single and isinstance(single, dict):
            for subj, detail in single.items():
                if detail and isinstance(detail, dict):
                    min_val = detail.get("min")
                    if min_val is not None:
                        if not isinstance(min_val, (int, float)) or min_val <= 0 or min_val > 150:
                            errors.append(
                                f"{prefix}.single_subject.{subj}.min={min_val} 不合法")

    return errors


def get_extracted_universities(rules: list) -> set:
    """从现有规则中获取已提取的大学集合"""
    return {r.get("university", "") for r in rules if r.get("university")}


def load_existing_rules() -> tuple[dict, list]:
    """加载现有规则"""
    if RULES_FILE.exists():
        with open(RULES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("meta", {}), data.get("rules", [])
    return {"version": "2026.1", "province": "全国"}, []


def save_rules(meta: dict, rules: list):
    """保存规则到 JSON"""
    meta["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    meta["total_universities"] = len(rules)
    output = {"meta": meta, "rules": rules}
    with open(RULES_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)


def get_unprocessed_universities(zszc_dir: Path) -> list[str]:
    """获取所有有章程 TXT 但尚未提取规则的大学"""
    # 获取所有有章程的大学
    uni_set = set()
    for f in zszc_dir.glob("*_2026招生章程_*.txt"):
        name = f.stem.split('_2026')[0]
        uni_set.add(name)

    # 排除已提取的
    meta, rules = load_existing_rules()
    extracted = get_extracted_universities(rules)

    # 文件名是 safe_name, 需要做反向匹配
    # 简化处理：直接按文件名匹配
    remaining = uni_set - extracted

    # 同时检查 safe_name 匹配
    remaining_final = set()
    for uni in remaining:
        # 检查是否有规则已覆盖（模糊匹配）
        covered = False
        for ext_uni in extracted:
            # 简单包含匹配
            if uni in ext_uni or ext_uni in uni:
                covered = True
                break
            # 检查 safe_name 变体
            safe = re.sub(r'[\\/:*?"<>|]', '_', ext_uni)
            if uni == safe:
                covered = True
                break
        if not covered:
            remaining_final.add(uni)

    return sorted(remaining_final)


def fallback_rule(university_name: str, source_files: list[str]) -> dict:
    """生成通配回退规则"""
    return {
        "university": university_name,
        "source_files": source_files,
        "majors": [{
            "major_pattern": ".*",
            "major_name": "全部专业",
            "notes": "章程原文已抓取但自动提取失败，待人工复核"
        }],
        "year": 2026,
    }


def process_university(university_name: str) -> dict | None:
    """处理单个大学的规则提取"""
    print(f"\n{'='*60}")
    print(f"处理: {university_name}")

    # 拼接章程全文
    full_text, source_files = get_chapter_full_text(university_name)
    if not full_text:
        print(f"  ⚠️ 未找到章程 TXT 文件")
        return None

    print(f"  章程长度: {len(full_text)} 字符, 来源文件: {len(source_files)} 个")

    # 调用 LLM
    result = call_deepseek_api(full_text, university_name)

    if result is None:
        print(f"  ⚠️ LLM 调用失败, 使用通配规则回退")
        return fallback_rule(university_name, source_files)

    # 验证
    errors = validate_extracted_rule(result)
    if errors:
        print(f"  ⚠️ 验证发现 {len(errors)} 个问题:")
        for e in errors[:5]:
            print(f"    - {e}")
        # 有错误但仍尝试使用（可能部分有效）

    # 补充元数据
    result["source_files"] = source_files
    result["year"] = 2026

    # 统计
    majors = result.get("majors", [])
    wildcard = sum(1 for m in majors if m.get("major_pattern") == ".*")
    specific = len(majors) - wildcard
    print(f"  提取结果: {len(majors)} 条规则 (通配:{wildcard}, 精细:{specific})")

    return result


def main():
    parser = argparse.ArgumentParser(description="批量从章程提取结构化规则")
    parser.add_argument("--university", "-u", help="处理指定大学")
    parser.add_argument("--limit", "-n", type=int, help="限制处理数量")
    parser.add_argument("--dry-run", action="store_true", help="预览模式")
    parser.add_argument("--force", action="store_true", help="强制重新提取 (覆盖已有规则)")
    args = parser.parse_args()

    meta, rules = load_existing_rules()
    print(f"现有规则: {len(rules)} 所大学")

    if args.university:
        unis_to_process = [args.university]
    else:
        unis_to_process = get_unprocessed_universities(ZSZC_DIR)
        if args.force:
            # 强制模式下处理所有有章程的大学
            all_unis = set()
            for f in ZSZC_DIR.glob("*_2026招生章程_*.txt"):
                name = f.stem.split('_2026')[0]
                all_unis.add(name)
            unis_to_process = sorted(all_unis)

    if args.limit:
        unis_to_process = unis_to_process[:args.limit]

    print(f"待处理: {len(unis_to_process)} 所大学")

    if args.dry_run:
        print("\n[Dry Run] 预览待处理大学:")
        for uni in unis_to_process[:20]:
            print(f"  - {uni}")
        if len(unis_to_process) > 20:
            print(f"  ... 还有 {len(unis_to_process) - 20} 所")
        return

    extraction_failed = []
    processed = 0

    for i, uni_name in enumerate(unis_to_process):
        try:
            result = process_university(uni_name)
            if result:
                # 追加到规则列表
                rules.append(result)
                processed += 1

                # 每处理5所保存一次
                if processed % 5 == 0:
                    save_rules(meta, rules)
                    print(f"  💾 已保存 ({processed} 所)")

            time.sleep(1)  # API 调用间隔
        except Exception as e:
            print(f"  ❌ 处理 {uni_name} 失败: {e}")
            extraction_failed.append({"university": uni_name, "error": str(e)})

    # 最终保存
    save_rules(meta, rules)
    print(f"\n✅ 提取完成: {processed}/{len(unis_to_process)} 成功")

    # 保存失败清单
    if extraction_failed:
        failed_path = DATA_DIR / "extraction_failed.json"
        with open(failed_path, "w", encoding="utf-8") as f:
            json.dump(extraction_failed, f, ensure_ascii=False, indent=2)
        print(f"❌ 失败清单: {failed_path} ({len(extraction_failed)} 所)")


if __name__ == "__main__":
    main()

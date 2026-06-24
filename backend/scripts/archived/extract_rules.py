"""
从招生章程 TXT 文件中自动提取结构化规则。

扫描 backend/data/zszc/ 下所有章程文件，识别:
- 色盲/色弱限制专业
- 单科成绩要求
- 语种限制
- 选科要求

输出: backend/data/enrollment_rules.json
"""
import json
import os
import re
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).parent.parent
ZSCZ_DIR = BASE_DIR / "data" / "zszc"
OUTPUT_PATH = BASE_DIR / "data" / "enrollment_rules.json"


def read_all_segments(university_name: str) -> str:
    """拼接某大学的所有分段 TXT 文件"""
    full_text = ""
    # 查找匹配的文件
    files = sorted(ZSCZ_DIR.glob(f"{university_name}_*招生章程_第*.txt"))
    if not files:
        # 尝试匹配带括号的大学名
        for f in sorted(ZSCZ_DIR.glob("*.txt")):
            if f.stem.startswith(university_name):
                files.append(f)
        files = sorted(set(files))

    for f in files:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                text = fh.read()
                # 去掉文件头元信息
                lines = text.split("\n")
                content_start = 0
                for i, line in enumerate(lines):
                    if line.startswith("# ") or line.startswith("第一章") or "招生章程" in line and "已经由" in line:
                        content_start = i
                        break
                full_text += "\n".join(lines[content_start:]) + "\n"
        except Exception:
            continue
    return full_text


def extract_body_check_rules(text: str) -> dict:
    """
    提取体检限制规则
    返回: {color_blind_majors: [...], color_weak_majors: [...], color_distinguish_majors: [...], notes: str}
    """
    result = {
        "color_blind_majors": [],      # 色盲不予录取
        "color_weak_majors": [],       # 色弱不予录取
        "color_distinguish_majors": [],  # 不能准确识别颜色
        "notes": "",
    }

    # 模式1: "色觉异常II度（俗称色盲）不能录取的专业：..."
    # 模式2: "轻度色觉异常（俗称色弱）不能录取的专业：..."
    # 模式3: 表格形式

    # 提取色弱限制
    weak_patterns = [
        r"轻度色觉异常[^。]*不能录取[^。]*专业[：:](.*?)(?:[。\n]|色觉异常)",
        r"色弱[^。]*不予录取[^。]*专业[：:](.*?)(?:[。\n])",
        r"色弱[^。]*限报[^。]*专业[：:](.*?)(?:[。\n])",
        r"俗称色弱[^。]*不能录取[^。]*专业[：:](.*?)(?:[。\n])",
    ]
    for pat in weak_patterns:
        m = re.search(pat, text, re.DOTALL)
        if m:
            majors = re.split(r"[、，,]", m.group(1).strip())
            result["color_weak_majors"] = [m.strip().rstrip("。；;") for m in majors if m.strip()]
            break

    # 提取色盲限制
    blind_patterns = [
        r"色觉异常II度[^。]*不能录取[^。]*专业[：:](.*?)(?:[。\n]|不能准确识别)",
        r"色觉异常Ⅱ度[^。]*不能录取[^。]*专业[：:](.*?)(?:[。\n]|不能准确识别)",
        r"俗称色盲[^。]*不能录取[^。]*专业[：:](.*?)(?:[。\n])",
        r"色盲[^。]*不予录取[^。]*专业[：:](.*?)(?:[。\n])",
        r"色盲[^。]*不能录取[^。]*专业[：:](.*?)(?:[。\n])",
    ]
    for pat in blind_patterns:
        m = re.search(pat, text, re.DOTALL)
        if m:
            majors = re.split(r"[、，,]", m.group(1).strip())
            result["color_blind_majors"] = [m.strip().rstrip("。；;") for m in majors if m.strip()]
            break

    # 处理 "XX专业，色盲、色弱考生限报" 这种倒装格式（如暨南大学）
    # 以及 "XX专业...色盲、色弱者不予录取" 格式
    if not result["color_blind_majors"] and not result["color_weak_majors"]:
        # 匹配 "专业A、专业B、专业C等N个专业，色盲、色弱考生限报"
        inline_pattern = r"([^。]*?(?:专业|医学|药学|工程|科学|技术)[^。]*?等[^。]*?专业[^。]*?)，[^。]*?色[盲弱][^。]*?色[盲弱][^。]*?(?:限报|不予录取|不能录取)"
        m = re.search(inline_pattern, text)
        if m:
            full_sentence = m.group(0)
            # 找到最后一个 "等N个专业" 的位置（避免括号内的"等"干扰）
            deng_matches = list(re.finditer(r"等\d*个专业", full_sentence))
            if deng_matches:
                # 取最后一个匹配（真正的总结性"等N个专业"）
                before_deng = full_sentence[:deng_matches[-1].start()]
            else:
                before_deng = full_sentence.split("等")[0]

            # 核心策略: 先用括号匹配去除所有括号内容
            # "临床医学（含校本部班、省二医班...）" → "临床医学"
            cleaned = before_deng
            # 反复移除括号内容（处理嵌套情况）
            while re.search(r"[（(][^)）]*[)）]", cleaned):
                cleaned = re.sub(r"[（(][^)）]*[)）]", "", cleaned)

            # 再用顿号分割
            majors_raw = re.split(r"[、，,]", cleaned)
            cleaned_majors = []
            for mj in majors_raw:
                mj = mj.strip().rstrip("。；;")
                # 过滤掉非专业名（如"根据专业特点"、"根据"开头等）
                if mj and len(mj) >= 2 and not mj.startswith("根据") and not mj.startswith("下列"):
                    cleaned_majors.append(mj)
            if cleaned_majors:
                result["color_blind_majors"] = cleaned_majors
                result["color_weak_majors"] = cleaned_majors

    # 提取不能准确识别颜色限制
    distinguish_patterns = [
        r"不能准确识别红[^。]*不能录取[^。]*专业[：:](.*?)(?:[。\n])",
        r"不能准确识别红[^。]*不予录取[^。]*专业[：:](.*?)(?:[。\n])",
    ]
    for pat in distinguish_patterns:
        m = re.search(pat, text, re.DOTALL)
        if m:
            majors = re.split(r"[、，,]", m.group(1).strip())
            result["color_distinguish_majors"] = [m.strip().rstrip("。；;") for m in majors if m.strip()]
            break

    # 处理表格形式 (西安交通大学等)
    # | 1 | 轻度色觉异常（俗称色弱） | 专业A、专业B |
    table_matches = re.findall(r"\|\s*\d+\s*\|\s*(轻度色觉异常[^|]*)\|\s*([^|]+)\s*\|", text)
    for condition, majors_str in table_matches:
        majors = [m.strip() for m in re.split(r"[、，,]", majors_str.strip()) if m.strip()]
        if "色弱" in condition and not result["color_weak_majors"]:
            result["color_weak_majors"] = majors
        if "色盲" in condition and not result["color_blind_majors"]:
            result["color_blind_majors"] = majors

    # 处理电子科技大学格式: 在专业表格中标注 "不录取色觉异常II度（俗称色盲）的考生"
    # 和 "对患有...色觉异常II度...疾病者不予录取"
    if not result["color_blind_majors"] and not result["color_weak_majors"]:
        # 匹配 "\u201cXX专业\u201d" 对患有 "色觉异常II度" 疾病者不予录取
        # 支持三种引号: "" (\u201c\u201d), "" (\u300c\u300d), "" (\x22)
        inline_blind = re.findall(
            r'[\u201c\u300c\x22]([^\u201d\u300d\x22]+?)[\u201d\u300d\x22]\s*专业对患有[^。]*?色觉异常II度[^。]*?(?:不予录取|不能录取)',
            text,
        )
        if inline_blind:
            result["color_blind_majors"] = [m.strip() for m in inline_blind if m.strip()]

        # 匹配 "XX专业" 和 "YY专业" 对患有...色弱...不予录取
        inline_weak = re.findall(
            r'[\u201c\u300c\x22]([^\u201d\u300d\x22]+?)[\u201d\u300d\x22]\s*(?:和)?[\u201c\u300c\x22]([^\u201d\u300d\x22]*?)[\u201d\u300d\x22]?\s*专业对患有[^。]*?(?:轻度色觉异常|色弱)[^。]*?(?:不予录取|不能录取)',
            text,
        )
        if inline_weak:
            for match in inline_weak:
                for mj in match:
                    mj = mj.strip()
                    if mj and mj not in result["color_weak_majors"]:
                        result["color_weak_majors"].append(mj)

        # 匹配表格中专业+体检备注的格式（如电子科技大学招生专业目录）
        # 格式: | 专业名 | ... | 四年 | ... | 说明列含"不录取色觉异常II度" |
        # 需要逐行解析：匹配 | 专业名 | ... | 说明列 |
        for line in text.split("\n"):
            if ("不录取色觉异常" in line) or ("不予录取" in line and "色" in line):
                parts = [p.strip() for p in line.split("|")]
                # 电子科技大学表格格式: | 招生名称 | 学院 | 专业名 | 科类 | 选考 | 学制 | 学费 | 包含专业 | 教学地点 | 说明 |
                # 专业名在第3列 (index 2)，说明列在最后
                # 找包含 "不录取" 或 "不予录取" 的列来确定是说明列
                body_col_idx = None
                for idx, part in enumerate(parts):
                    if "不录取" in part or ("不予录取" in part and "色" in part):
                        body_col_idx = idx
                        break
                if body_col_idx is not None and len(parts) > 2:
                    # 专业名在第3列 (index 2)
                    major_candidate = parts[2].strip() if len(parts) > 2 else ""
                    # 过滤数字、学制、空白等
                    skip_words = ("四年", "五年", "理工", "文史", "物理", "历史", "物理、化学", "", " ", "6500", "6000", "7000", "8000")
                    if major_candidate and len(major_candidate) >= 3 and major_candidate not in skip_words and not major_candidate.isdigit():
                        # 去掉上标等
                        major_candidate = re.sub(r"<sup>.*?</sup>", "", major_candidate)
                        major_candidate = re.sub(r"\s+", "", major_candidate)
                        if "色盲" in line:
                            if major_candidate not in result["color_blind_majors"]:
                                result["color_blind_majors"].append(major_candidate)
                        if "色弱" in line:
                            if major_candidate not in result["color_weak_majors"]:
                                result["color_weak_majors"].append(major_candidate)

    # 提取 notes 中的体检关键句
    check_sentences = re.findall(r"[^。]*?色[盲弱][^。]*?[。\n]", text)
    if check_sentences:
        result["notes"] = "；".join(s.strip() for s in check_sentences[:3])

    return result


def extract_single_subject_requirements(text: str) -> dict:
    """
    提取单科成绩要求
    返回: {english_min: int|None, math_min: int|None, chinese_min: int|None, ...}
    """
    result = {
        "english_min": None,
        "math_min": None,
        "chinese_min": None,
        "notes": "",
    }

    # 英语不低于XX分
    eng_patterns = [
        r"英语[单科成绩]*[^。]*?不低于\s*(\d+)\s*分",
        r"外语[单科成绩]*[^。]*?不低于\s*(\d+)\s*分",
        r"英语成绩[^。]*?不低于\s*(\d+)\s*分",
        r"外语成绩[^。]*?不低于\s*(\d+)\s*分",
    ]
    for pat in eng_patterns:
        m = re.search(pat, text)
        if m:
            result["english_min"] = int(m.group(1))
            break

    # 数学不低于XX分
    math_patterns = [
        r"数学[单科成绩]*[^。]*?不低于\s*(\d+)\s*分",
        r"数学成绩[^。]*?不低于\s*(\d+)\s*分",
    ]
    for pat in math_patterns:
        m = re.search(pat, text)
        if m:
            result["math_min"] = int(m.group(1))
            break

    # 语文不低于XX分
    chinese_patterns = [
        r"语文[单科成绩]*[^。]*?不低于\s*(\d+)\s*分",
        r"语文成绩[^。]*?不低于\s*(\d+)\s*分",
    ]
    for pat in chinese_patterns:
        m = re.search(pat, text)
        if m:
            result["chinese_min"] = int(m.group(1))
            break

    # 收集相关句子
    score_sentences = re.findall(r"[^。]*?单科[^。]*?不低于[^。]*?[。\n]", text)
    if score_sentences:
        result["notes"] = "；".join(s.strip() for s in score_sentences[:3])

    return result


def extract_language_restrictions(text: str) -> dict:
    """
    提取语种限制
    返回: {restricted_majors: [...], notes: str}
    """
    result = {
        "restricted_majors": [],
        "notes": "",
    }

    # "XX专业只招收外语语种为英语的考生"
    lang_matches = re.findall(
        r"([^。，,]*?(?:专业|班|项目)[^。，,]*?)只[招收录取][^。]*?语种[为是]([^。，,的]*?)[的]*考生",
        text,
    )
    for major_part, lang in lang_matches:
        result["restricted_majors"].append({
            "major": major_part.strip().rstrip("等").strip(),
            "language": lang.strip(),
        })

    # "仅限英语语种"
    only_matches = re.findall(r"仅限\s*(英语|日语|俄语|德语|法语)\s*语种", text)
    for lang in only_matches:
        result["restricted_majors"].append({"major": "整体", "language": lang.strip()})

    # 非英语语种谨慎报考
    cautious = re.findall(r"[^。]*?非英语[^。]*?谨慎[^。]*?[。\n]", text)
    if cautious:
        result["notes"] = "；".join(s.strip() for s in cautious[:2])

    return result


def extract_subject_election(text: str) -> dict:
    """
    提取选科要求（粗略提取，精确的选科通常在招生计划中）
    """
    result = {
        "has_requirements": False,
        "notes": "",
    }

    # 物理+化学必选
    if "物理+化学" in text or "物理和化学" in text or "物理、化学" in text:
        result["has_requirements"] = True
    if "物理(必选)" in text or "物理必选" in text or "物理（必选）" in text:
        result["has_requirements"] = True

    # 提取选科相关句子
    election_sentences = re.findall(r"[^。]*?选考[^。]*?[。\n]", text)
    if election_sentences:
        result["notes"] = "；".join(s.strip() for s in election_sentences[:3])

    return result


def extract_notes(text: str) -> str:
    """提取其他重要注意事项（中外合作、校区等）"""
    notes_parts = []

    # 中外合作办学
    coop = re.findall(r"[^。]*?中外合作[^。]*?[。\n]", text)
    if coop:
        notes_parts.append("中外合作: " + "；".join(c.strip() for c in coop[:2]))

    # 校区信息
    campus = re.findall(r"[^。]*?(?:校区[^。]*?(?:培养|就读|教学))[^。]*?[。\n]", text)
    if campus:
        notes_parts.append("校区: " + "；".join(c.strip() for c in campus[:2]))

    # 只录取有专业志愿的考生
    only_volunteer = re.findall(r"[^。]*?(?:护理学|马克思主义|戏剧影视)[^。]*?只[^。]*?填报[^。]*?志愿[^。]*?[。\n]", text)
    if only_volunteer:
        notes_parts.append("特殊录取: " + "；".join(c.strip() for c in only_volunteer[:2]))

    return "；".join(notes_parts) if notes_parts else ""


def _clean_major_name(name: str) -> str:
    """清理专业名，去掉文件头元信息、编号等杂质"""
    name = name.strip()
    # 如果包含大量换行或等号，说明是文件头，跳过
    if "\n" in name or "=====" in name or "大学名称" in name or "段落编号" in name:
        return ""
    # 去掉开头的编号如 "1.", "1、"
    name = re.sub(r"^\d+[\.、\s]+", "", name)
    # 去掉 "等N个专业" 后缀
    name = re.sub(r"等\d*个专业$", "", name)
    # 去掉尾部标点
    name = name.rstrip("。；;，, \t")
    # 过滤掉非专业名的短语
    skip_phrases = [
        "除同轻度色觉异常", "色觉异常II度两类列出专业外", "色觉异常Ⅱ度两类列出专业外",
        "还包括", "不能准确识别", "除1所含专业外", "除2所含专业外",
        "根据专业特点", "下列专业", "以下专业",
    ]
    if any(name.startswith(p) for p in skip_phrases):
        return ""
    if "列出专业外" in name or "所含专业外" in name:
        return ""
    # 如果清理后太短，跳过
    if len(name) < 2:
        return ""
    # 如果包含未闭合的括号（半截），去掉从括号开始的所有内容
    if "（" in name and "）" not in name:
        name = name.split("（")[0].strip()
    if "(" in name and ")" not in name:
        name = name.split("(")[0].strip()
    # 移除闭合的括号内容（反复直到没有括号）
    while re.search(r"[（(][^)）]*[)）]", name):
        name = re.sub(r"[（(][^)）]*[)）]", "", name)
    name = name.strip()
    # 去掉可能残留的右括号
    name = name.rstrip("）)")
    return name


def _make_major_pattern(major_name: str) -> str:
    """
    从专业全名生成模糊匹配的正则。
    对于包含括号的专业名（如 临床医学（侯宗濂班）），同时匹配不带括号的简称。
    """
    major_name = major_name.strip()
    # 提取括号前的内容作为核心匹配
    base = re.sub(r"[（(][^)）]*[)）]", "", major_name).strip()
    if len(base) >= 2:
        return re.escape(base)
    # 没有括号，直接转义
    return re.escape(major_name)


def extract_university_rules(university_name: str, text: str) -> dict:
    """综合提取某大学的所有规则"""
    body_check = extract_body_check_rules(text)
    single_subject = extract_single_subject_requirements(text)
    language = extract_language_restrictions(text)
    subject_election = extract_subject_election(text)
    notes = extract_notes(text)

    # 将体检限制转为 majors 格式
    majors_list = []
    seen = set()

    for major in body_check["color_blind_majors"]:
        cleaned = _clean_major_name(major)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        majors_list.append({
            "major_pattern": _make_major_pattern(cleaned),
            "major_name": cleaned,
            "body_check": {"color_blind": "DANGER", "color_weak": "DANGER", "clause": f"{university_name}2026年招生章程体检补充规定"},
            "notes": "色盲色弱不予录取",
        })

    # 处理色弱限制（仅色弱，不含在色盲里的）
    for major in body_check["color_weak_majors"]:
        cleaned = _clean_major_name(major)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        majors_list.append({
            "major_pattern": _make_major_pattern(cleaned),
            "major_name": cleaned,
            "body_check": {"color_weak": "DANGER", "clause": f"{university_name}2026年招生章程体检补充规定"},
            "notes": "色弱不予录取",
        })

    # 处理不能准确识别颜色限制
    for major in body_check["color_distinguish_majors"]:
        cleaned = _clean_major_name(major)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        majors_list.append({
            "major_pattern": _make_major_pattern(cleaned),
            "major_name": cleaned,
            "body_check": {"color_blind": "DANGER", "color_weak": "DANGER", "color_distinguish": "DANGER", "clause": f"{university_name}2026年招生章程体检补充规定"},
            "notes": "不能准确识别颜色者不予录取",
        })

    # 处理语种限制
    for lang_item in language["restricted_majors"]:
        major = lang_item["major"]
        lang_val = lang_item["language"]
        if major == "整体":
            majors_list.append({
                "major_pattern": ".*",
                "major_name": "全部专业",
                "language_restriction": f"仅限{lang_val}语种",
                "notes": language.get("notes", ""),
            })
        else:
            cleaned = _clean_major_name(major)
            if cleaned:
                majors_list.append({
                    "major_pattern": _make_major_pattern(cleaned),
                    "major_name": cleaned,
                    "language_restriction": f"仅限{lang_val}语种",
                    "notes": language.get("notes", ""),
                })

    # 处理单科成绩
    if any([single_subject["english_min"], single_subject["math_min"], single_subject["chinese_min"]]):
        single_entry = {"major_pattern": ".*", "major_name": "全部专业"}
        ss = {}
        if single_subject["english_min"]:
            ss["english"] = {"min": single_subject["english_min"], "clause": f"{university_name}2026年招生章程"}
        if single_subject["math_min"]:
            ss["math"] = {"min": single_subject["math_min"], "clause": f"{university_name}2026年招生章程"}
        if single_subject["chinese_min"]:
            ss["chinese"] = {"min": single_subject["chinese_min"], "clause": f"{university_name}2026年招生章程"}
        single_entry["single_subject"] = ss
        single_entry["notes"] = single_subject.get("notes", "")
        majors_list.append(single_entry)

    # 如果没有提取到任何 majors，至少保留一个空条目
    if not majors_list:
        majors_list.append({
            "major_pattern": ".*",
            "major_name": "全部专业",
            "notes": notes if notes else "执行教育部通用体检标准，无特殊单科/语种限制",
        })

    return {
        "university": university_name,
        "source_files": [
            f.name for f in sorted(ZSCZ_DIR.glob(f"{university_name}_*招生章程_第*.txt"))
        ] or [f.name for f in sorted(ZSCZ_DIR.glob("*.txt")) if f.stem.startswith(university_name)],
        "majors": majors_list,
    }


def main():
    # 收集所有大学名
    university_names = set()
    for f in ZSCZ_DIR.glob("*.txt"):
        # 从文件名提取大学名: "北京大学_2026招生章程_第1段.txt"
        name = f.stem
        # 去掉年份和段落
        name = re.sub(r"_\d{4}招生章程_第\d+段$", "", name)
        name = re.sub(r"_\d{4}招生章程_第\d+段.*$", "", name)
        university_names.add(name)

    print(f"发现 {len(university_names)} 所高校的章程文件")

    rules = []
    for uname in sorted(university_names):
        print(f"处理: {uname}...")
        text = read_all_segments(uname)
        if not text:
            print(f"  ⚠ 无法读取 {uname} 的章程文本")
            continue
        rule = extract_university_rules(uname, text)
        rules.append(rule)

        # 统计提取结果
        total_majors = len(rule["majors"])
        has_body = any("body_check" in m for m in rule["majors"])
        has_lang = any("language_restriction" in m for m in rule["majors"])
        has_score = any("single_subject" in m for m in rule["majors"])
        print(f"  ✓ {total_majors} 条规则 (体检:{has_body}, 语种:{has_lang}, 单科:{has_score})")

    # 构建最终 JSON
    output = {
        "meta": {
            "version": "2026.1",
            "province": "全国",
            "last_updated": "2026-06-12",
            "source": "教育部阳光高考平台 2026年招生章程原文",
            "total_universities": len(rules),
        },
        "rules": rules,
    }

    # 写入文件
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 已生成 {OUTPUT_PATH}")
    print(f"   共 {len(rules)} 所高校的结构化规则")


if __name__ == "__main__":
    main()

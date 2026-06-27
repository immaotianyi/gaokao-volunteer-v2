"""
招生章程知识库 — 双层检索架构

方案A: 结构化规则库 (enrollment_rules.json) — O(1) 正则匹配
方案B: 章程全文检索 — 读取 TXT 注入 LLM prompt

用法:
    kb = EnrollmentKnowledgeBase()
    rule = kb.query("暨南大学", "临床医学")
    if rule["found"]:
        # 使用结构化规则
    else:
        # fallback: 读取章程全文
        full_text = kb.get_full_articles("暨南大学")
"""
import json
import re
from pathlib import Path
from typing import Any


# 数据目录
DATA_DIR = Path(__file__).parent.parent / "data"
RULES_PATH = DATA_DIR / "enrollment_rules.json"
ZSCZ_DIR = DATA_DIR / "zszc"

# 体检专业关键词 → 通用默认规则（教育部体检指导意见）
# 已升级为从 body_check_defaults.json 加载完整兜底规则
_DEFAULT_BODY_CHECK_MAJORS = {
    "临床医学": ("色盲、色弱者不予录取", "《普通高等学校招生体检工作指导意见》第一条第二款"),
    "口腔医学": ("色盲、色弱者不予录取", "《普通高等学校招生体检工作指导意见》第一条第二款"),
    "麻醉学": ("色盲、色弱者不予录取", "《普通高等学校招生体检工作指导意见》第一条第二款"),
    "医学影像学": ("色盲、色弱者不予录取", "《普通高等学校招生体检工作指导意见》第一条第二款"),
    "法医学": ("色盲、色弱者不予录取", "《普通高等学校招生体检工作指导意见》第一条第二款"),
    "药学": ("色弱、色盲者不宜就读", "《普通高等学校招生体检工作指导意见》第一条第三款"),
    "飞行技术": ("裸眼视力低于5.0者不予录取", "《普通高等学校招生体检工作指导意见》第四款"),
}

# 加载完整兜底规则库
_DEFAULT_RULES_PATH = DATA_DIR / "body_check_defaults.json"
_default_body_check_rules: dict = {}


def _load_default_body_check_rules():
    """懒加载 body_check_defaults.json 兜底规则库"""
    global _default_body_check_rules
    if _default_body_check_rules:
        return _default_body_check_rules
    if _DEFAULT_RULES_PATH.exists():
        try:
            with open(_DEFAULT_RULES_PATH, "r", encoding="utf-8") as f:
                _default_body_check_rules = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return _default_body_check_rules


class EnrollmentKnowledgeBase:
    """
    招生章程知识库

    双层检索:
    1. 优先查 enrollment_rules.json 结构化规则
    2. 未命中时返回 found=False，由调用方决定是否 fallback 到全文
    """

    def __init__(self, rules_path: str | None = None, txt_dir: str | None = None):
        self.rules_path = Path(rules_path) if rules_path else RULES_PATH
        self.txt_dir = Path(txt_dir) if txt_dir else ZSCZ_DIR

        # 加载规则
        self._rules_data: dict[str, Any] = {"rules": []}
        self._university_index: dict[str, list[dict]] = {}
        self._live_cache: dict[str, dict] = {}  # 联网搜索临时缓存
        self._load_rules()

    def _inject_live_result(self, university: str, rules: dict):
        """注入联网搜索结果到临时缓存，供本次会话使用"""
        self._live_cache[university] = rules
        # 同时构建索引
        majors = rules.get("majors", [])
        self._university_index[university] = majors

    def _load_rules(self):
        """加载 enrollment_rules.json 并构建索引"""
        if not self.rules_path.exists():
            print(f"[KB] ⚠ 未找到规则文件: {self.rules_path}")
            return

        try:
            with open(self.rules_path, "r", encoding="utf-8") as f:
                self._rules_data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"[KB] ⚠ 规则文件加载失败: {e}")
            return

        # 构建 university_name → [rule_entries] 索引
        for rule in self._rules_data.get("rules", []):
            uname = rule.get("university", "")
            if uname:
                # 同时用全名和简称建立索引
                self._university_index[uname] = rule.get("majors", [])
                # 如 "北京大学" → 也可以用 "北大" 模糊匹配

        meta = self._rules_data.get("meta", {})
        print(f"[KB] ✓ 已加载 {meta.get('total_universities', 0)} 所高校的招生章程规则")

    def query(self, university: str, major: str) -> dict:
        """
        方案A: 结构化规则检索

        Args:
            university: 大学名称 (如 "暨南大学")
            major: 专业名称 (如 "临床医学")

        Returns:
            {
                "found": bool,
                "university": str,
                "major": str,
                "body_check": {...} | None,
                "single_subject": {...} | None,
                "language_restriction": str | None,
                "subject_election": str | None,
                "notes": str,
                "source": str,
            }
        """
        result = {
            "found": False,
            "university": university,
            "major": major,
            "body_check": None,
            "single_subject": None,
            "language_restriction": None,
            "subject_election": None,
            "low_preference": None,
            "notes": "",
            "source": "",
            "rules_text": "",
        }

        # 1. 精确匹配大学名
        rules = self._university_index.get(university)
        if rules is None:
            # 2. 模糊匹配大学名 (处理简称)
            rules = self._fuzzy_match_university(university)

        if rules is None:
            # 大学未收录，使用通用默认规则
            result = self._apply_default_rules(university, major, result)
            result["rules_text"] = self.get_rule_summary(university, major, _pre_built=result)
            return result

        # 3. 按匹配优先级遍历规则: 专业精确匹配 > 全校通配 .*
        # 关键: 先收集所有命中的规则，然后按"最精确"的一条取字段，
        # 避免 .* 通配规则覆盖专业级豁免规则 (如南方医科法学不招色弱→应PASS)
        matched_rules = []
        for rule_entry in rules:
            pattern = rule_entry.get("major_pattern", ".*")
            try:
                if re.search(pattern, major):
                    matched_rules.append(rule_entry)
            except re.error:
                continue

        if matched_rules:
            result["found"] = True
            result["source"] = f"{university}2026年招生章程 (结构化规则库)"

            # 按精确度排序: 非 .* 的规则 > .* 通配规则
            # 更精确的规则放前面，它的值优先采用
            matched_rules.sort(key=lambda r: 0 if r.get("major_pattern") != ".*" else 1)

            # 只取最精确的规则的字段（不合并，避免通配规则覆盖专业规则）
            best = matched_rules[0]
            result["body_check"] = best.get("body_check")
            result["single_subject"] = best.get("single_subject")
            result["language_restriction"] = best.get("language_restriction")
            result["subject_election"] = best.get("subject_election")
            result["low_preference"] = best.get("low_preference")
            if best.get("notes"):
                result["notes"] = str(best["notes"])

        # 4. 如果结构化规则未命中专业，但大学在索引中，至少返回通用信息
        if not result["found"] and rules:
            result["found"] = True  # 标记为"该大学已收录但该专业无特殊限制"
            result["source"] = f"{university}2026年招生章程 (未发现该专业特殊限制)"
            # 检查是否有全校性规则
            for rule_entry in rules:
                if rule_entry.get("major_pattern") == ".*":
                    if "single_subject" in rule_entry:
                        result["single_subject"] = rule_entry["single_subject"]
                    if "language_restriction" in rule_entry:
                        result["language_restriction"] = rule_entry["language_restriction"]
                    if "notes" in rule_entry:
                        result["notes"] = rule_entry["notes"]
                    break

        # 5. 如果大学不在索引中，使用通用默认规则
        if not result["found"]:
            result = self._apply_default_rules(university, major, result)

        # 补齐 rules_text（传入 _pre_built 避免 get_rule_summary 内部再次调用 query 形成递归）
        result["rules_text"] = self.get_rule_summary(university, major, _pre_built=result)
        return result

    def _fuzzy_match_university(self, name: str) -> list[dict] | None:
        """模糊匹配大学名"""
        # 尝试去掉"大学"、"学院"等后缀
        clean_name = name.replace("大学", "").replace("学院", "").strip()
        for uname, rules in self._university_index.items():
            clean_uname = uname.replace("大学", "").replace("学院", "").strip()
            if clean_name in clean_uname or clean_uname in clean_name:
                return rules
        return None

    def _get_rule_year(self, university: str) -> int | None:
        """从 enrollment_rules.json 中提取某大学的规则年份"""
        for rule_entry in self._rules_data.get("rules", []):
            if rule_entry.get("university", "") == university:
                return rule_entry.get("year")
        return None

    def _apply_default_rules(self, university: str, major: str, result: dict) -> dict:
        """对未收录的大学/专业，应用教育部通用体检指导意见兜底规则库"""
        result["source"] = "教育部《普通高等学校招生体检工作指导意见》(通用默认规则)"

        # 1. 先尝试从完整兜底规则库匹配
        defaults = _load_default_body_check_rules()
        if defaults:
            # 检查 DANGER 级规则（可不予录取）
            for rule in defaults.get("majors_can_reject", {}).get("rules", []):
                for m in rule.get("majors", []):
                    # 关键词匹配：专业名包含规则中的关键词，或规则名包含专业名
                    if m in major or major in m or any(kw in major for kw in m.split("类") if kw):
                        result["found"] = True
                        result["body_check"] = {
                            "severity": rule.get("severity", "DANGER"),
                            "text": rule.get("condition", ""),
                            "clause": rule.get("clause", ""),
                        }
                        result["notes"] = f"{rule.get('condition', '')}者，该专业可不予录取"
                        return result

            # 检查 WARNING 级规则（不宜就读）
            for rule in defaults.get("majors_not_suitable", {}).get("rules", []):
                for m in rule.get("majors", []):
                    if m in major or major in m or any(kw in major for kw in m.split("类") if kw):
                        result["found"] = True
                        result["body_check"] = {
                            "severity": rule.get("severity", "WARNING"),
                            "text": rule.get("condition", ""),
                            "clause": rule.get("clause", ""),
                        }
                        result["notes"] = f"{rule.get('condition', '')}者，该专业不宜就读"
                        return result

        # 2. 回退到旧版精简兜底规则
        for risk_major, (reason, clause) in _DEFAULT_BODY_CHECK_MAJORS.items():
            if risk_major in major:
                result["found"] = True
                result["body_check"] = {
                    "color_blind": "DANGER",
                    "color_weak": "DANGER",
                    "clause": clause,
                }
                result["notes"] = reason
                return result

        return result

    def get_full_articles(self, university: str) -> str:
        """
        方案B: 读取某大学的所有章程 TXT 分段文件并拼接

        Args:
            university: 大学名称

        Returns:
            拼接后的章程全文 (最多 3000 字符)
        """
        full_text = ""
        files = sorted(self.txt_dir.glob(f"{university}_*招生章程_第*.txt"))

        # 如果精确匹配不到，尝试模糊匹配
        if not files:
            clean_name = university.replace("大学", "").replace("学院", "").strip()
            for f in sorted(self.txt_dir.glob("*.txt")):
                f_clean = f.stem.replace("大学", "").replace("学院", "")
                if clean_name in f_clean:
                    files.append(f)
            files = sorted(set(files))

        if not files:
            return ""

        for f in files:
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    content = fh.read()
                    # 跳过文件头元信息 (到第一个 # 或 "第一章" 开始)
                    lines = content.split("\n")
                    content_start = 0
                    for i, line in enumerate(lines):
                        if line.startswith("# ") or "第一章" in line:
                            content_start = i
                            break
                    full_text += "\n".join(lines[content_start:]) + "\n"
            except Exception:
                continue

        # 截取前 3000 字符
        if len(full_text) > 3000:
            full_text = full_text[:3000] + "\n...(章程全文较长，已截取前3000字符)"

        return full_text

    def get_rule_summary(self, university: str, major: str, _pre_built: dict | None = None) -> str:
        """
        生成可供 LLM prompt 使用的规则摘要文本

        Args:
            _pre_built: 已构建好的 query() result dict；传入时直接复用，避免与 query() 互相递归。
                        外部调用方无需传入（保持原签名兼容）。
        """
        rule = _pre_built if _pre_built is not None else self.query(university, major)

        if not rule["found"]:
            # Fallback: 返回全文
            full_text = self.get_full_articles(university)
            if full_text:
                return f"【{university}章程全文（节选）】\n{full_text[:2000]}"
            return f"【{university}】该校章程暂未收录，请依据教育部通用体检指导意见审查。"

        # 提取规则年份
        rule_year = self._get_rule_year(university)

        parts = [f"【{university}真实章程条款 — {rule['source']}】"]
        if rule_year:
            parts[0] += f"\n⚠️ 规则来源年份: {rule_year}年，如有更新请以当年官方章程为准。"

        # 体检限制
        if rule.get("body_check"):
            bc = rule["body_check"]
            clauses = []
            if bc.get("color_blind") == "DANGER":
                clauses.append("色盲不予录取")
            if bc.get("color_weak") == "DANGER":
                clauses.append("色弱不予录取")
            if bc.get("color_distinguish") == "DANGER":
                clauses.append("不能准确识别颜色者不予录取")
            if clauses:
                parts.append(f"体检限制: {'、'.join(clauses)}")
                if bc.get("clause"):
                    parts.append(f"  条款依据: {bc['clause']}")

        # 单科成绩
        if rule.get("single_subject"):
            ss = rule["single_subject"]
            score_parts = []
            if "english" in ss:
                score_parts.append(f"英语≥{ss['english']['min']}分")
            if "math" in ss:
                score_parts.append(f"数学≥{ss['math']['min']}分")
            if "chinese" in ss:
                score_parts.append(f"语文≥{ss['chinese']['min']}分")
            if score_parts:
                parts.append(f"单科成绩要求: {'、'.join(score_parts)}")
                # clause
                for k in ("english", "math", "chinese"):
                    if k in ss and ss[k].get("clause"):
                        parts.append(f"  条款依据: {ss[k]['clause']}")
                        break

        # 语种限制
        if rule.get("language_restriction"):
            parts.append(f"语种限制: {rule['language_restriction']}")

        # 选科要求
        if rule.get("subject_election"):
            parts.append(f"选科要求: {rule['subject_election']}")

        # 低偏好专业
        if rule.get("low_preference"):
            lp = rule["low_preference"]
            parts.append(f"低偏好专业: {lp.get('category', '')} — {lp.get('reason', '')}")

        # 其他注意事项
        if rule.get("notes"):
            parts.append(f"其他: {rule['notes']}")

        return "\n".join(parts)


# 全局单例 (懒加载)
_kb_instance: EnrollmentKnowledgeBase | None = None


def get_knowledge_base() -> EnrollmentKnowledgeBase:
    """获取知识库全局单例"""
    global _kb_instance
    if _kb_instance is None:
        _kb_instance = EnrollmentKnowledgeBase()
    return _kb_instance

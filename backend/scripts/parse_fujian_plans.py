#!/usr/bin/env python3
"""福建 2026 招生计划 PDF 解析脚本。

数据源：福建省教育考试院 2026 招生计划 PDF（物理科目组/历史科目组 × 提前批/本科批/专科批）
输出：追加到 data/plans_2026.csv

字段顺序（与 _common_spec.md 一致）：
  province,subject_group,batch,university_code,university_name,group_code,major_code,
  major_name,plan_count,tuition,lowest_score_2025,lowest_rank_2025,is_new,school_type,
  major_category,subject_requirement,plan_count_prev
"""
import csv
import hashlib
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd
import pdfplumber

BACKEND = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND / "data"
RAW_DIR = DATA_DIR / "raw" / "fujian_2026"
PLANS_CSV = DATA_DIR / "plans_2026.csv"
PROVINCE = "福建"

# 列区间（基于PDF位置分析）
COL_RANGES = {
    "left": (60, 100),          # 院校名 / 专业组代号(4位)
    "major_code": (100, 130),   # 专业代号(3位)
    "name": (130, 270),         # 专业名/选科/章程
    "xuezhi": (270, 300),       # 学制
    "plan": (300, 330),         # 计划人数
    "tuition": (330, 370),      # 学费
    "note": (370, 495),         # 备注
}

# PDF 文件清单
PDF_FILES = [
    # (path, subject_group, batch)
    (RAW_DIR / "plans_physics" / "1本科提前批.pdf", "物理类", "本科提前批"),
    (RAW_DIR / "plans_physics" / "4本科批.pdf", "物理类", "本科批"),
    (RAW_DIR / "plans_physics" / "5高职（专科）提前批.pdf", "物理类", "专科提前批"),
    (RAW_DIR / "plans_physics" / "6高职（专科）批.pdf", "物理类", "专科批"),
    (RAW_DIR / "plans_history" / "1本科提前批.pdf", "历史类", "本科提前批"),
    (RAW_DIR / "plans_history" / "4本科批.pdf", "历史类", "本科批"),
    (RAW_DIR / "plans_history" / "5高职（专科）提前批.pdf", "历史类", "专科提前批"),
    (RAW_DIR / "plans_history" / "6高职（专科）批.pdf", "历史类", "专科批"),
]


def assign_column(x0):
    for col, (lo, hi) in COL_RANGES.items():
        if lo <= x0 < hi:
            return col
    return None


def parse_page_chars(page):
    """用 page.chars 按 height 过滤水印，按列分桶重组行。"""
    chars = page.chars
    # 正常字符 height ≈ 8-9，水印字符 height ≈ 60-70
    normal_chars = [c for c in chars if (c["bottom"] - c["top"]) <= 15]

    # 按 row（top/5 取整）分组
    rows_dict = defaultdict(list)
    for c in normal_chars:
        row_idx = round(c["top"] / 5)
        rows_dict[row_idx].append(c)

    # 合并相邻行（top 差 ≤ 8）
    sorted_keys = sorted(rows_dict.keys())
    merged_rows = []
    for k in sorted_keys:
        chars_in_row = rows_dict[k]
        if not chars_in_row:
            continue
        cur_top = min(c["top"] for c in chars_in_row)
        if merged_rows:
            last_row, last_top = merged_rows[-1]
            if abs(cur_top - last_top) <= 8:
                last_row.extend(chars_in_row)
                continue
        merged_rows.append((list(chars_in_row), cur_top))

    # 按列分桶 + 拼接文本
    result = []
    for chars_in_row, _ in merged_rows:
        col_buckets = defaultdict(list)
        for c in chars_in_row:
            col = assign_column(c["x0"])
            if col is None:
                continue
            col_buckets[col].append(c)
        row_data = {}
        for col, chars_list in col_buckets.items():
            chars_list.sort(key=lambda c: c["x0"])
            text_parts = []
            prev_x1 = None
            for c in chars_list:
                if prev_x1 is not None and c["x0"] - prev_x1 > 3:
                    text_parts.append(" ")
                text_parts.append(c["text"])
                prev_x1 = c["x1"]
            row_data[col] = "".join(text_parts).strip()
        if row_data:
            result.append(row_data)
    return result


HEADER_KEYWORDS = ["年福建省", "普通高校招生计划", "招生计划", "收费标准",
                   "院校代号", "专业代号", "专业名称", "计划人数",
                   "备注", "普通类", "物理科目组", "历史科目组",
                   "本科批", "专科批", "本科提前批", "代号"]


def classify_row(row):
    """识别行类型：university / group / major / header / other。"""
    left = row.get("left", "")
    major_code = row.get("major_code", "")
    name = row.get("name", "")
    plan = row.get("plan", "")

    combined = left + major_code + name

    # 表头/标题行
    if any(kw in combined for kw in HEADER_KEYWORDS):
        return "header", "", ""

    # 招生章程行
    if "招生章程" in combined or "网址" in combined:
        return "header", "", ""

    # 专业组行：left 有4位数字 + (name 含":(" 或 "选考" 或 "不限" 或 "专业组")
    if left and len(left) >= 4 and left[:4].isdigit():
        if any(kw in name + major_code for kw in [":(", "选考", "不限", "专业组", ":999", ":500", ":600", ":800"]):
            return "group", left[:4], name
        # 也可能是组行（无显式标记）
        if ":" in name and "(" in name:
            return "group", left[:4], name

    # 院校行：left 是中文 + 含"大学/学院/学校"
    if left and any(kw in left for kw in ["大学", "学院", "学校"]):
        # 但要排除"专业组"等
        if "专业组" not in left:
            return "university", "", left

    # 专业行：major_code 有2-3位代号（数字或字母+数字）
    if major_code:
        cleaned = major_code.replace(" ", "").replace(":", "")
        if cleaned and 2 <= len(cleaned) <= 3:
            if cleaned[0].isalpha() or cleaned.isdigit():
                return "major", cleaned, name

    # 也可能专业代号在 left 列（3位数字）
    if left and len(left) >= 3 and left[:3].isdigit() and not left[:4].isdigit():
        return "major", left[:3], name

    return "other", "", ""


def parse_subject_requirement(name_text, subject_group):
    """从专业组行的 name 字段提取选科要求，转为标准格式。"""
    # name_text 形如 "500(选考化学)" / "999(不限选考科目)" / "600(选考生物学)"
    base = "物理" if subject_group == "物理类" else "历史"

    # 提取括号内选科要求
    m = re.search(r"\(([^)]+)\)", name_text)
    if not m:
        return base
    req_text = m.group(1).strip()

    if "不限" in req_text:
        return f"{base}+不限"

    # 提取选考科目（"选考化学" / "选考生物学" / "选考物理" / "选考思想政治" / "选考地理"）
    # 福建格式：选考化学 / 选考生物学 / 选考物理或化学 / 选考物理或化学或生物
    subjects = []
    subject_map = {
        "物理": "物理", "化学": "化学", "生物": "生物",
        "思想政治": "政治", "政治": "政治",
        "地理": "地理", "历史": "历史",
    }
    for kw, std in subject_map.items():
        if kw in req_text:
            if std not in subjects:
                subjects.append(std)

    if not subjects:
        return f"{base}+不限"
    return base + "+" + "+".join(subjects)


def infer_major_category(major_name):
    """从专业名推断专业大类。"""
    name = major_name
    # 按优先级匹配
    rules = [
        ("医学", ["医学", "临床", "口腔", "护理", "药学", "中医", "法医", "预防医学", "康复治疗", "医学技术"]),
        ("工学", ["工程", "工学", "计算机", "软件", "电子", "电气", "自动化", "机械", "土木", "建筑",
                  "化工", "材料", "冶金", "能源", "动力", "通信", "信息", "人工智能", "数据科学",
                  "网络安全", "物联网", "机器人", "车辆", "测控", "水利", "测绘", "纺织", "食品",
                  "轻工", "地质", "矿业", "石油", "海洋", "航空航天", "兵器", "核工程", "生物工程",
                  "农业工程", "林业工程", "环境工程", "环境科学", "安全科学", "智能制造", "集成电路",
                  "光电", "交通", "物流", "印刷", "包装"]),
        ("理学", ["数学", "物理", "化学", "生物", "天文", "地理", "大气", "海洋科学", "地球",
                  "统计", "理学", "生态", "心理学", "系统科学"]),
        ("农学", ["农学", "园艺", "植物", "动物", "林学", "园林", "水产", "草学", "兽医",
                  "农业", "茶学", "种子", "智慧农业"]),
        ("文学", ["文学", "语言", "汉语", "英语", "日语", "法语", "德语", "西班牙语", "俄语",
                  "阿拉伯语", "翻译", "新闻", "传播", "广告", "广播", "网络与新媒体"]),
        ("法学", ["法学", "法律", "政治", "社会学", "社会工作", "马克思主义", "公安", "侦查",
                  "知识产权", "信用风险"]),
        ("经济学", ["经济", "金融", "贸易", "保险", "财政", "税收", "投资"]),
        ("管理学", ["管理", "会计", "财务", "市场", "工商管理", "公共管理", "旅游", "物流管理",
                    "电子商务", "信息管理", "工程管理", "工程造价", "国际商务"]),
        ("教育学", ["教育", "体育", "运动", "学前", "小学教育", "特殊教育"]),
        ("艺术学", ["艺术", "音乐", "美术", "设计", "戏剧", "影视", "舞蹈", "播音", "编导",
                    "动画", "摄影", "书法", "表演"]),
        ("历史学", ["历史", "考古", "文物"]),
        ("哲学", ["哲学", "逻辑", "宗教学"]),
    ]
    for cat, keywords in rules:
        for kw in keywords:
            if kw in name:
                return cat
    return "工学"  # 兜底


def parse_group_count(name_text):
    """从专业组行 name 字段提取组人数（如 "500(选考化学)" → 500）。"""
    m = re.match(r":?(\d+)\s*\(", name_text)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    return None


def parse_pdf(pdf_path, subject_group, batch, univ_code_map, school_type_map):
    """解析单个 PDF，返回行列表 + 更新映射表。"""
    if not pdf_path.exists():
        print(f"  ⚠ 跳过（文件不存在）: {pdf_path}")
        return []

    print(f"\n[解析] {pdf_path.name} ({subject_group}/{batch})")
    rows_out = []
    current_university = ""
    current_univ_prop = ""  # 公办/民办
    current_group_code = ""
    current_subject_req = ""

    with pdfplumber.open(str(pdf_path)) as pdf:
        n_pages = len(pdf.pages)
        print(f"  总页数: {n_pages}")

        for page_idx, page in enumerate(pdf.pages):
            try:
                rows = parse_page_chars(page)
            except Exception as e:
                print(f"  [WARN] 第 {page_idx+1} 页解析失败: {e}")
                continue

            for row in rows:
                rtype, code, name = classify_row(row)
                if rtype == "header":
                    continue

                if rtype == "university":
                    # 院校行：提取院校名 + 办学性质
                    # left 字段形如 "福建福耀科技大学" 或 "福建技术师范学院"
                    univ_name = row.get("left", "").strip()
                    # 清洗：去除残留的水印字
                    univ_name = clean_text(univ_name)
                    if univ_name:
                        current_university = univ_name
                        # 从 note 列提取办学性质
                        note = row.get("note", "")
                        if "民办" in note:
                            current_univ_prop = "民办"
                        elif "公办" in note:
                            current_univ_prop = "公办"
                        else:
                            current_univ_prop = ""
                        # 初始化映射
                        if univ_name not in univ_code_map:
                            univ_code_map[univ_name] = gen_univ_code(univ_name)
                        if univ_name not in school_type_map:
                            school_type_map[univ_name] = infer_school_type(
                                univ_name, current_univ_prop)

                elif rtype == "group":
                    # 专业组行
                    current_group_code = code
                    current_subject_req = parse_subject_requirement(name, subject_group)

                elif rtype == "major":
                    # 专业行
                    if not current_university or not current_group_code:
                        # 缺少院校/专业组上下文，跳过
                        continue
                    major_code = code
                    major_name = clean_text(name)
                    plan_count = parse_int(row.get("plan", ""))
                    tuition = parse_int(row.get("tuition", ""))
                    # 学费字段可能混入备注，清洗
                    if tuition is None:
                        # 从 tuition 列提取数字
                        tstr = row.get("tuition", "")
                        m = re.search(r"(\d{3,5})", tstr)
                        if m:
                            tuition = int(m.group(1))

                    if plan_count is None or plan_count <= 0:
                        # 计划人数缺失，跳过
                        continue

                    rows_out.append({
                        "province": "福建",
                        "subject_group": subject_group,
                        "batch": batch,
                        "university_code": univ_code_map[current_university],
                        "university_name": current_university,
                        "group_code": current_group_code,
                        "major_code": major_code,
                        "major_name": major_name,
                        "plan_count": plan_count,
                        "tuition": tuition if tuition else "",
                        "lowest_score_2025": "",
                        "lowest_rank_2025": "",
                        "is_new": 0,
                        "school_type": school_type_map[current_university],
                        "major_category": infer_major_category(major_name),
                        "subject_requirement": current_subject_req,
                        "plan_count_prev": "",
                    })

            if (page_idx + 1) % 50 == 0:
                print(f"  进度: {page_idx+1}/{n_pages} 页, 累计 {len(rows_out)} 专业")

        print(f"  ✓ 完成: {len(rows_out)} 专业")

    return rows_out


def clean_text(text):
    """清洗文本：去除残留水印字、多余空格。"""
    if not text:
        return ""
    # 去除水印单字（出现在文本开头/结尾的水印字）
    watermark = set("院试考育教省普通类本科批物理目组建福年之高校招生计划收费标准人数代号名称学制备注院校专业组")
    # 仅清洗开头/结尾的单字水印
    while text and text[0] in watermark and len(text) > 1:
        # 但要保留"福建"等合法开头
        if text.startswith("福建") or text.startswith("物理") or text.startswith("历史"):
            break
        text = text[1:]
    while text and text[-1] in watermark and len(text) > 1:
        if text.endswith("学院") or text.endswith("大学") or text.endswith("学校"):
            break
        text = text[:-1]
    # 去除中间的水印字（保守：只去除明显的单字水印插入）
    # "数据计算及应用建" → "数据计算及应用"
    # "网络与新媒体教20" → "网络与新媒体"
    # 但要小心"福建"/"物理"等合法词
    # 简单规则：去除文本末尾的水印字+数字组合
    text = re.sub(r"[建教试考育省院]\d*$", "", text)
    text = re.sub(r"\s+", "", text)
    return text.strip()


def parse_int(val):
    if val is None:
        return None
    s = str(val).strip().replace(",", "").replace(" ", "")
    if not s:
        return None
    # 提取第一个数字
    m = re.search(r"\d+", s)
    if m:
        try:
            return int(m.group(0))
        except ValueError:
            return None
    return None


def gen_univ_code(univ_name):
    """生成6位院校代码：FJ + hash前4位。"""
    h = hashlib.md5(univ_name.encode("utf-8")).hexdigest()
    return "FJ" + h[:4].upper()


# 985/211/双一流院校名单（用于推断 school_type）
KEY_UNIVERSITIES = {
    # 985
    "北京大学", "清华大学", "中国人民大学", "北京师范大学", "北京航空航天大学",
    "北京理工大学", "中国农业大学", "中央民族大学", "南开大学", "天津大学",
    "大连理工大学", "东北大学", "吉林大学", "哈尔滨工业大学", "复旦大学",
    "同济大学", "上海交通大学", "华东师范大学", "南京大学", "东南大学",
    "浙江大学", "中国科学技术大学", "厦门大学", "山东大学", "中国海洋大学",
    "武汉大学", "华中科技大学", "湖南大学", "中南大学", "中山大学",
    "华南理工大学", "四川大学", "重庆大学", "电子科技大学", "西安交通大学",
    "西北工业大学", "西北农林科技大学", "兰州大学", "国防科技大学",
    "中央军委国防科技大学",
    # 211（非985）
    "北京交通大学", "北京工业大学", "北京科技大学", "北京化工大学", "北京邮电大学",
    "北京林业大学", "北京中医药大学", "北京外国语大学", "中国传媒大学",
    "中央财经大学", "对外经济贸易大学", "北京体育大学", "中央音乐学院",
    "中国政法大学", "华北电力大学", "内蒙古大学", "辽宁大学", "大连海事大学",
    "延边大学", "东北师范大学", "东北农业大学", "东北林业大学", "上海大学",
    "苏州大学", "南京航空航天大学", "南京理工大学", "中国矿业大学", "河海大学",
    "江南大学", "南京农业大学", "中国药科大学", "南京师范大学", "安徽大学",
    "合肥工业大学", "福州大学", "南昌大学", "中国石油大学", "郑州大学",
    "武汉理工大学", "中国地质大学", "华中师范大学", "华中农业大学",
    "中南财经政法大学", "湖南师范大学", "华南师范大学", "海南大学",
    "广西大学", "西南交通大学", "西南大学", "西南财经大学", "贵州大学",
    "云南大学", "西藏大学", "西北大学", "西安电子科技大学", "长安大学",
    "陕西师范大学", "青海大学", "宁夏大学", "新疆大学", "石河子大学",
    "第二军医大学", "第四军医大学",
    # 双一流（非985/211）
    "中国科学院大学", "上海科技大学", "南方科技大学", "宁波大学", "河南大学",
    "成都理工大学", "南京邮电大学", "南京信息工程大学", "南京中医药大学",
    "南京医科大学", "南京林业大学", "上海海洋大学", "上海体育学院",
    "上海音乐学院", "上海美术学院", "中国美术学院", "西北大学",
    "山西大学", "湘潭大学", "华南农业大学",
    # 福建本省重点
    "福建师范大学", "福建农林大学", "福建医科大学", "福建中医药大学",
    "集美大学", "华侨大学", "福建理工大学", "福建工程学院",
    "闽江学院", "厦门理工学院",
}

# 福建本省普通公办本科
FUJIAN_PUBLIC = {
    "福建技术师范学院", "福建警察学院", "武夷学院", "莆田学院", "三明学院",
    "龙岩学院", "宁德师范学院", "福建商学院", "福建江夏学院",
}


def infer_school_type(univ_name, property_hint):
    """推断院校层次。"""
    if univ_name in KEY_UNIVERSITIES:
        # 区分 985 / 211 / 双一流
        # 简化：985名单优先
        nine_8_5 = {"北京大学", "清华大学", "中国人民大学", "北京师范大学", "北京航空航天大学",
                    "北京理工大学", "中国农业大学", "中央民族大学", "南开大学", "天津大学",
                    "大连理工大学", "东北大学", "吉林大学", "哈尔滨工业大学", "复旦大学",
                    "同济大学", "上海交通大学", "华东师范大学", "南京大学", "东南大学",
                    "浙江大学", "中国科学技术大学", "厦门大学", "山东大学", "中国海洋大学",
                    "武汉大学", "华中科技大学", "湖南大学", "中南大学", "中山大学",
                    "华南理工大学", "四川大学", "重庆大学", "电子科技大学", "西安交通大学",
                    "西北工业大学", "西北农林科技大学", "兰州大学", "国防科技大学"}
        if univ_name in nine_8_5:
            return "985"
        # 双一流
        shuang_yi_liu = {"中国科学院大学", "上海科技大学", "南方科技大学", "宁波大学", "河南大学",
                         "成都理工大学", "南京邮电大学", "南京信息工程大学", "南京中医药大学",
                         "南京医科大学", "南京林业大学", "上海海洋大学", "山西大学", "湘潭大学",
                         "华南农业大学"}
        if univ_name in shuang_yi_liu:
            return "双一流"
        return "211"
    if "民办" in property_hint or "民办" in univ_name:
        return "民办"
    if "独立学院" in univ_name:
        return "独立学院"
    if univ_name in FUJIAN_PUBLIC or "公办" in property_hint:
        if "师范" in univ_name or "农林" in univ_name or "医科" in univ_name:
            return "省属重点"
        return "普通本科"
    return "普通本科"


def load_existing_univ_maps():
    """从现有 plans_2026.csv 加载院校名→代码/类型映射。"""
    univ_code_map = {}
    school_type_map = {}
    if PLANS_CSV.exists():
        df = pd.read_csv(PLANS_CSV, dtype=str)
        for _, row in df.iterrows():
            name = row.get("university_name", "")
            code = row.get("university_code", "")
            stype = row.get("school_type", "")
            if name and code:
                univ_code_map[name] = code
            if name and stype:
                school_type_map[name] = stype
    return univ_code_map, school_type_map


def append_to_csv(new_rows, csv_path):
    """安全追加数据到CSV（去重）。"""
    # #14 root fix: 重定向到 data/raw/{省}_{文件名}，禁止直接写主 CSV
    _raw_dir = DATA_DIR / "raw"
    _raw_dir.mkdir(exist_ok=True)
    csv_path = _raw_dir / f"{PROVINCE}_{csv_path.name}"
    if not new_rows:
        return 0
    new_df = pd.DataFrame(new_rows)
    if csv_path.exists():
        existing = pd.read_csv(csv_path, dtype=str)
        # 去除可能重复的福建行（按全部列去重）
        existing_no_fj = existing[existing["province"] != "福建"]
        merged = pd.concat([existing_no_fj, new_df], ignore_index=True)
    else:
        merged = new_df
    # 空值填空字符串
    merged = merged.fillna("")
    merged.to_csv(csv_path, index=False, encoding="utf-8")
    return len(new_df)


def main():
    print("="*60)
    print("福建 2026 招生计划 PDF 解析")
    print("="*60)

    # 加载现有映射
    univ_code_map, school_type_map = load_existing_univ_maps()
    print(f"已加载 {len(univ_code_map)} 个院校代码映射, {len(school_type_map)} 个 school_type 映射")

    # 解析所有 PDF
    all_rows = []
    for pdf_path, subject_group, batch in PDF_FILES:
        rows = parse_pdf(pdf_path, subject_group, batch, univ_code_map, school_type_map)
        all_rows.extend(rows)

    print(f"\n{'='*60}")
    print(f"解析完成: 共 {len(all_rows)} 行")
    # 统计
    by_sg = defaultdict(int)
    by_batch = defaultdict(int)
    for r in all_rows:
        by_sg[r["subject_group"]] += 1
        by_batch[r["batch"]] += 1
    print(f"按科类: {dict(by_sg)}")
    print(f"按批次: {dict(by_batch)}")

    # 写入 CSV
    n = append_to_csv(all_rows, PLANS_CSV)
    print(f"\n[OK] 追加 {n} 行到 {PLANS_CSV}")

    # 样本预览
    if all_rows:
        print(f"\n样本预览（前5行）:")
        for r in all_rows[:5]:
            print(f"  {r['subject_group']}/{r['batch']} {r['university_name']} 组{r['group_code']} {r['major_code']} {r['major_name']} 计划{r['plan_count']} 学费{r['tuition']} 选科{r['subject_requirement']} 类型{r['school_type']} 大类{r['major_category']}")


if __name__ == "__main__":
    main()

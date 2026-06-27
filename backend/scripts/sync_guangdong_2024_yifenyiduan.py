#!/usr/bin/env python3
"""
同步广东省 2024 年一分一段表

数据源:
  - ZIP: https://eea.gd.gov.cn/attachment/0/552/552702/4445714.zip
  - 内含 16 个 PDF（与 2025 相同结构）

2024 附件编号→科类映射（与 2025 相同：历史在前物理在后）:
  1=历史类, 2=物理类, 3=体育类, 4=美术类, 5=音乐类,
  6=音乐(声乐主项), 7=音乐(器乐主项), 8=音乐表演(声乐), 9=音乐表演(器乐),
  10=舞蹈类, 11=表演(戏剧影视表演), 12=表演(服装表演), 13=编导(戏剧影视导演),
  14=播音(普通话), 15=播音(粤语), 16=书法类

输出: data/yifenyiduan_2024.csv
schema: province, year, subject_group, batch, score, segment_count, cumulative_count
"""
import re
import zipfile
import pdfplumber
import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_DIR = DATA_DIR / "raw" / "gd_2024" / "yifenyiduan"
ZIP_PATH = RAW_DIR / "2024_yifenyiduan.zip"
# #14 root fix: 重定向到 data/raw/广东_yifenyiduan_2024.csv，禁止直接写主 CSV
_RAW_OUT = DATA_DIR / "raw"
_RAW_OUT.mkdir(exist_ok=True)
OUTPUT_CSV = _RAW_OUT / "广东_yifenyiduan_2024.csv"
YEAR = 2024

# 附件编号→科类映射（与 2025 相同）
ATTACHMENT_NO_TO_SUBJECT = {
    1: "历史类",
    2: "物理类",
    3: "体育类",
    4: "美术类",
    5: "音乐类",
    6: "音乐(声乐主项)",
    7: "音乐(器乐主项)",
    8: "音乐表演(声乐)",
    9: "音乐表演(器乐)",
    10: "舞蹈类",
    11: "表演(戏剧影视表演)",
    12: "表演(服装表演)",
    13: "编导(戏剧影视导演)",
    14: "播音(普通话)",
    15: "播音(粤语)",
    16: "书法类",
}


def unzip_and_rename(zip_path: Path, out_dir: Path) -> dict[int, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_map = {}
    with zipfile.ZipFile(str(zip_path), "r") as zf:
        for info in zf.infolist():
            try:
                raw_name = info.filename.encode("cp437")
                decoded_name = raw_name.decode("gbk")
            except (UnicodeDecodeError, UnicodeEncodeError):
                decoded_name = info.filename
            m = re.match(r"\s*(\d{1,2})[\.\、]", decoded_name)
            if not m:
                print(f"  ⚠ 跳过: {decoded_name}")
                continue
            attach_no = int(m.group(1))
            if attach_no not in ATTACHMENT_NO_TO_SUBJECT:
                print(f"  ⚠ 跳过（编号{attach_no}不在映射表）: {decoded_name}")
                continue
            subject = ATTACHMENT_NO_TO_SUBJECT[attach_no]
            eng_name = f"gd_{YEAR}_{attach_no:02d}_{subject.replace('/', '_').replace('(', '_').replace(')', '')}.pdf"
            out_path = out_dir / eng_name
            with zf.open(info) as src, open(out_path, "wb") as dst:
                dst.write(src.read())
            pdf_map[attach_no] = out_path
            print(f"  附件{attach_no} → {eng_name} ({subject})")
    return pdf_map


def clean_cell(val):
    if val is None:
        return None
    s = str(val).strip()
    s = re.sub(r"^[院试考育教省东广\s]+", "", s)
    s = s.replace(",", "")
    if s == "" or s == "-":
        return None
    try:
        return int(float(s))
    except ValueError:
        m = re.match(r"(\d+)", s)
        if m:
            return int(m.group(1))
        return None


def parse_pdf(pdf_path: Path, subject_group: str) -> list[dict]:
    rows = []
    pdf = pdfplumber.open(str(pdf_path))
    for page in pdf.pages:
        tables = page.extract_tables()
        for table in tables:
            for row in table:
                if not row or len(row) < 5:
                    continue
                first = str(row[0]) if row[0] else ""
                if "文化总分" in first or "分数段" in first:
                    continue
                score = clean_cell(row[0])
                bk_segment = clean_cell(row[1])
                bk_cumulative = clean_cell(row[2])
                zk_segment = clean_cell(row[3])
                zk_cumulative = clean_cell(row[4])
                if score is None or score < 0 or score > 750:
                    continue
                if bk_cumulative is not None:
                    rows.append({
                        "province": "广东", "year": YEAR,
                        "subject_group": subject_group, "batch": "本科",
                        "score": score,
                        "segment_count": bk_segment if bk_segment is not None else 0,
                        "cumulative_count": bk_cumulative,
                    })
                if zk_cumulative is not None:
                    rows.append({
                        "province": "广东", "year": YEAR,
                        "subject_group": subject_group, "batch": "专科",
                        "score": score,
                        "segment_count": zk_segment if zk_segment is not None else 0,
                        "cumulative_count": zk_cumulative,
                    })
    pdf.close()
    return rows


def main():
    print("=" * 60)
    print(f"同步广东{YEAR}一分一段表")
    print("=" * 60)

    if not ZIP_PATH.exists():
        print(f"❌ ZIP 不存在: {ZIP_PATH}")
        return

    print("\n--- 1. 解压 ZIP ---")
    pdf_map = unzip_and_rename(ZIP_PATH, RAW_DIR)
    print(f"  共解压 {len(pdf_map)} 个 PDF")

    print("\n--- 2. 解析 PDF ---")
    all_rows = []
    for attach_no, pdf_path in sorted(pdf_map.items()):
        subject = ATTACHMENT_NO_TO_SUBJECT[attach_no]
        rows = parse_pdf(pdf_path, subject)
        print(f"  附件{attach_no} {subject}: {len(rows)}行")
        all_rows.extend(rows)

    print(f"\n  总计: {len(all_rows)} 行")

    print("\n--- 3. 生成 CSV ---")
    df = pd.DataFrame(all_rows)
    # 去重（同科类同批次同分数取最后一条）
    df = df.drop_duplicates(subset=["subject_group", "batch", "score"], keep="last")
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    print(f"✅ 已保存: {OUTPUT_CSV} ({len(df)} 行)")

    # 校验
    print("\n--- 4. 校验 ---")
    for (sg, batch), group in df.groupby(["subject_group", "batch"]):
        group_sorted = group.sort_values("score", ascending=False)
        scores = group_sorted["score"].tolist()
        cumuls = group_sorted["cumulative_count"].tolist()
        is_monotonic = all(cumuls[i] <= cumuls[i+1] for i in range(len(cumuls)-1))
        is_unique = len(scores) == len(set(scores))
        status = "✅" if (is_monotonic and is_unique) else "❌"
        if sg in ("物理类", "历史类"):
            print(f"  {status} {sg}({batch}): {len(group)}行, 分数[{min(scores)}-{max(scores)}], 单调={is_monotonic}, 唯一={is_unique}")

    # 关键数据点校验
    print("\n--- 5. 关键数据点 ---")
    for sg in ["物理类", "历史类"]:
        for batch in ["本科"]:
            sub = df[(df["subject_group"] == sg) & (df["batch"] == batch)]
            for test_score in [440, 500, 550, 600, 650]:
                row = sub[sub["score"] == test_score]
                if not row.empty:
                    print(f"  {sg} {batch} {test_score}分 → 位次 {row.iloc[0]['cumulative_count']}")


if __name__ == "__main__":
    main()

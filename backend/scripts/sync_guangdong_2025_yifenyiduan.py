#!/usr/bin/env python3
"""
同步广东省 2025 年一分一段表（真实数据，替换 generate_yifenyiduan.py 的插值伪造数据）

数据源:
  - ZIP: https://eea.gd.gov.cn/attachment/0/583/583759/4734449.zip
  - 内含 16 个 PDF（普通类历史/物理 + 9 艺体类 + 细分方向）

2025 附件编号→科类映射（注意：与 2026 顺序不同！2025 是历史在前物理在后）:
  1=历史类, 2=物理类, 3=体育类, 4=美术类, 5=音乐类,
  6=音乐(声乐主项), 7=音乐(器乐主项), 8=音乐表演(声乐), 9=音乐表演(器乐),
  10=舞蹈类, 11=表演(戏剧影视表演), 12=表演(服装表演), 13=编导(戏剧影视导演),
  14=播音(普通话), 15=播音(粤语), 16=书法类

PDF 表格结构（5列，同 2026）:
  文化总分 | 本科分数段人数 | 本科累计人数 | 专科分数段人数 | 专科累计人数

输出: data/yifenyiduan_2025.csv（覆盖插值数据）
schema: province, year, subject_group, batch, score, segment_count, cumulative_count
"""
import re
import zipfile
import pdfplumber
import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_DIR = DATA_DIR / "raw" / "gd_2025" / "yifenyiduan"
ZIP_PATH = RAW_DIR / "2025_yifenyiduan.zip"
# #14 root fix: 重定向到 data/raw/广东_yifenyiduan_2025.csv，禁止直接写主 CSV
_RAW_OUT = DATA_DIR / "raw"
_RAW_OUT.mkdir(exist_ok=True)
OUTPUT_CSV = _RAW_OUT / "广东_yifenyiduan_2025.csv"

# 2025 附件编号→科类映射（历史在前！与 2026 不同）
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
    """解压 ZIP（处理 GBK 中文文件名），按附件编号重命名为英文，返回 {附件编号: PDF路径}"""
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_map = {}

    with zipfile.ZipFile(str(zip_path), "r") as zf:
        for info in zf.infolist():
            # ZIP 内文件名是 GBK 编码，zipfile 默认用 cp437 解码，需转回 GBK
            try:
                raw_name = info.filename.encode("cp437")
                decoded_name = raw_name.decode("gbk")
            except (UnicodeDecodeError, UnicodeEncodeError):
                decoded_name = info.filename

            # 提取附件编号（文件名开头 "1.广东..." 或 "01.广东..."）
            m = re.match(r"\s*(\d{1,2})[\.\、]", decoded_name)
            if not m:
                print(f"  ⚠ 跳过（无法识别附件编号）: {decoded_name}")
                continue
            attach_no = int(m.group(1))
            if attach_no not in ATTACHMENT_NO_TO_SUBJECT:
                print(f"  ⚠ 跳过（附件编号 {attach_no} 不在映射表中）: {decoded_name}")
                continue

            # 重命名为英文
            subject = ATTACHMENT_NO_TO_SUBJECT[attach_no]
            eng_name = f"gd_2025_{attach_no:02d}_{subject.replace('/', '_').replace('(', '_').replace(')', '')}.pdf"
            out_path = out_dir / eng_name

            with zf.open(info) as src, open(out_path, "wb") as dst:
                dst.write(src.read())

            pdf_map[attach_no] = out_path
            print(f"  附件{attach_no} → {eng_name} ({subject})")

    return pdf_map


def clean_cell(val):
    """清洗单元格：去除水印噪声字，转整数"""
    if val is None:
        return None
    s = str(val).strip()
    # 去除前缀噪声字（PDF 水印单字：院/试/考/育/教/省/东/广）
    s = re.sub(r"^[院试考育教省东广\s]+", "", s)
    s = s.replace(",", "")
    if s == "" or s == "-":
        return None
    try:
        return int(float(s))
    except ValueError:
        # 可能是 "669（含以上）" 这样的分数
        m = re.match(r"(\d+)", s)
        if m:
            return int(m.group(1))
        return None


def parse_pdf(pdf_path: Path, subject_group: str) -> list[dict]:
    """解析单个 PDF，返回行列表（本科+专科）"""
    rows = []
    pdf = pdfplumber.open(str(pdf_path))
    total_pages = len(pdf.pages)

    for page in pdf.pages:
        tables = page.extract_tables()
        for table in tables:
            for row in table:
                if not row or len(row) < 5:
                    continue
                # 跳过表头
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

                # 本科批
                if bk_cumulative is not None:
                    rows.append({
                        "province": "广东",
                        "year": 2025,
                        "subject_group": subject_group,
                        "batch": "本科",
                        "score": score,
                        "segment_count": bk_segment if bk_segment is not None else 0,
                        "cumulative_count": bk_cumulative,
                    })
                # 专科批
                if zk_cumulative is not None:
                    rows.append({
                        "province": "广东",
                        "year": 2025,
                        "subject_group": subject_group,
                        "batch": "专科",
                        "score": score,
                        "segment_count": zk_segment if zk_segment is not None else 0,
                        "cumulative_count": zk_cumulative,
                    })

    pdf.close()
    return rows


def verify(df: pd.DataFrame):
    """校验数据完整性和单调性"""
    print("\n=== 校验 ===")
    for (sg, batch), group in df.groupby(["subject_group", "batch"]):
        group_sorted = group.sort_values("score", ascending=False)
        scores = group_sorted["score"].tolist()
        cumuls = group_sorted["cumulative_count"].tolist()

        # 单调性：分数降序，累计人数应非递减
        is_monotonic = all(cumuls[i] <= cumuls[i+1] for i in range(len(cumuls)-1))
        # 唯一性：分数不应重复
        is_unique = len(scores) == len(set(scores))

        status = "✅" if (is_monotonic and is_unique) else "❌"
        print(f"  {status} {sg}({batch}): {len(group)}行, 分数范围[{min(scores)}-{max(scores)}], 单调={is_monotonic}, 唯一={is_unique}")


def main():
    print("=" * 60)
    print("同步广东2025一分一段表（真实数据替换插值数据）")
    print("=" * 60)

    # 1. 解压 ZIP
    print("\n--- 1. 解压 ZIP ---")
    if not ZIP_PATH.exists():
        print(f"❌ ZIP 不存在: {ZIP_PATH}")
        return
    pdf_map = unzip_and_rename(ZIP_PATH, RAW_DIR)
    print(f"  共解压 {len(pdf_map)} 个 PDF")

    # 2. 解析每个 PDF
    print("\n--- 2. 解析 PDF ---")
    all_rows = []
    for attach_no, pdf_path in sorted(pdf_map.items()):
        subject = ATTACHMENT_NO_TO_SUBJECT[attach_no]
        rows = parse_pdf(pdf_path, subject)
        print(f"  附件{attach_no} {subject}: {len(rows)}行")
        all_rows.extend(rows)

    print(f"\n  总计: {len(all_rows)} 行")

    # 3. 生成 DataFrame 并去重
    df = pd.DataFrame(all_rows)
    # 去重：同一 (subject_group, batch, score) 取第一行
    before = len(df)
    df = df.drop_duplicates(subset=["subject_group", "batch", "score"], keep="first")
    after = len(df)
    if before != after:
        print(f"  去重: {before} → {after} (删除 {before-after} 行重复)")

    # 4. 校验
    verify(df)

    # 5. 备份旧文件 + 写入新文件
    if OUTPUT_CSV.exists():
        bak = OUTPUT_CSV.with_suffix(".csv.bak_interpolated")
        import shutil
        shutil.copy2(OUTPUT_CSV, bak)
        print(f"\n  旧插值数据已备份: {bak.name}")

    df = df.sort_values(["subject_group", "batch", "score"], ascending=[True, True, False]).reset_index(drop=True)
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    print(f"\n✅ 已写入 {OUTPUT_CSV} ({len(df)} 行)")

    # 6. 汇总
    print("\n--- 汇总 ---")
    for sg in df["subject_group"].unique():
        sub = df[df["subject_group"] == sg]
        for batch in sub["batch"].unique():
            sub_b = sub[sub["batch"] == batch]
            print(f"  {sg}({batch}): {len(sub_b)}行, 分数[{sub_b['score'].min()}-{sub_b['score'].max()}]")


if __name__ == "__main__":
    main()

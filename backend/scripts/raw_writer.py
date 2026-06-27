"""分省 raw 文件写入器（#14 root fix）

所有 sync_{省}_*.py 脚本必须通过本模块写数据，禁止直接写主 CSV。
主 CSV 只能由 merge_all.py 在所有 raw 就绪后一次性重建。

用法（在 sync 脚本的 append_to_csv 中）：
    from scripts.raw_writer import write_raw, redirect_to_raw
    raw_path = redirect_to_raw(csv_filename, PROVINCE)
    # read-concat-drop_duplicates 都基于 raw_path，不碰主 CSV
    merged.to_csv(raw_path, index=False, encoding="utf-8-sig")

或直接写入：
    write_raw("广东", "yifenyiduan_2026.csv", df)
"""
from pathlib import Path
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"

# 主 CSV 文件名集合（禁止 sync 脚本直接写）
MASTER_CSV_NAMES = {
    "plans_2026.csv", "plans_2025.csv", "plans_2024.csv",
    "yifenyiduan_2024.csv", "yifenyiduan_2025.csv", "yifenyiduan_2026.csv",
    "admission_history.csv",
    "control_line_2024.csv", "control_line_2025.csv", "control_line_2026.csv",
}


def redirect_to_raw(csv_filename, province: str) -> Path:
    """把主 CSV 文件名重定向到 data/raw/{省}_{文件名}。

    Args:
        csv_filename: 主 CSV 文件名（如 "yifenyiduan_2026.csv"）或 Path 对象
        province: 省份名（如 "广东"）

    Returns:
        data/raw/{省}_{文件名} 的 Path
    """
    name = Path(csv_filename).name
    if name not in MASTER_CSV_NAMES:
        # 非主 CSV 文件，不重定向（允许直接写中间文件）
        return Path(csv_filename) if not isinstance(csv_filename, Path) else csv_filename
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    return RAW_DIR / f"{province}_{name}"


def write_raw(province: str, data_type: str, df: pd.DataFrame, mode: str = "replace") -> Path:
    """写入分省 raw 文件。

    Args:
        province: 省份名（如 "广东"）
        data_type: 主 CSV 文件名（如 "yifenyiduan_2026.csv"）
        df: 要写入的 DataFrame
        mode: "replace" 覆盖写 | "append" 追加（自动去重）

    Returns:
        写入的 raw 文件 Path
    """
    raw_path = redirect_to_raw(data_type, province)
    if mode == "append" and raw_path.exists():
        try:
            old = pd.read_csv(raw_path, dtype=str)
            merged = pd.concat([old, df.astype(str)], ignore_index=True)
            # 通用去重：保留最后一条
            merged = merged.drop_duplicates(keep="last")
            df = merged
        except Exception as e:
            print(f"[raw_writer] ⚠ 追加模式读取旧 raw 失败，改为覆盖: {e}")
    df.to_csv(raw_path, index=False, encoding="utf-8-sig")
    print(f"[raw_writer] ✓ {province} → {raw_path.name} ({len(df)} 行)")
    return raw_path


def assert_not_master_csv(path, province: str = ""):
    """守卫：检查是否试图直接写主 CSV，是则报错。"""
    name = Path(path).name
    if name in MASTER_CSV_NAMES:
        raise PermissionError(
            f"[raw_writer] 🚫 禁止直接写主 CSV {name}！"
            f"请改用 redirect_to_raw('{name}', '{province}') 写入 data/raw/ 目录，"
            f"然后由 merge_all.py 统一合并。"
        )

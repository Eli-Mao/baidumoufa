"""把原始 zip 解到 data/raw/。分区：**川谷**。

原始压缩包里的文件名是 GBK 编码，用普通解压会得到乱码文件名，
本脚本负责把它们还原成约定的中文文件名。

用法::

    py -3 scripts/prepare_raw_data.py
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"

# 原始压缩包 -> data/raw 下的目标文件名
ZIP_SOURCES = {
    "数据.zip": None,      # 内含 站址.txt / 轨道.txt
    "优先级.zip": None,    # 内含 高/中/低优先级目标.txt
}

EXPECTED = ["轨道.txt", "站址.txt", "高优先级目标.txt", "中优先级目标.txt", "低优先级目标.txt"]


def _fix_name(name: str) -> str:
    """zip 内文件名是 GBK 字节被按 cp437 解释的结果，这里还原。"""
    try:
        return name.encode("cp437").decode("gbk")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name


def extract(zip_path: Path, dest_dir: Path) -> list[Path]:
    written: list[Path] = []
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            target = dest_dir / _fix_name(info.filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open("wb") as fh:
                fh.write(src.read())
            written.append(target)
    return written


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    args = argv if argv is not None else sys.argv[1:]
    if args:
        zips = [Path(a) for a in args]
    else:
        # 默认到赛题汇总目录里去找原始压缩包
        base = PROJECT_ROOT.parent / "开运联合"
        zips = [p for p in (base / n for n in ZIP_SOURCES) if p.exists()]
        if not zips:
            print(f"未找到原始压缩包，请显式传入 zip 路径。\n查找位置：{base}")
            return 1

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for zp in zips:
        written = extract(zp, RAW_DIR)
        for p in written:
            print(f"  {zp.name} -> {p.relative_to(PROJECT_ROOT)}  ({p.stat().st_size} B)")

    missing = [n for n in EXPECTED if not (RAW_DIR / n).exists()]
    if missing:
        print(f"✗ 缺少预期文件: {missing}")
        return 1
    print(f"✓ 原始数据已就位: {RAW_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

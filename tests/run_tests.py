"""统一测试入口（不依赖 pytest，用标准库 unittest）。

    py -3 tests/run_tests.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    suite = unittest.TestLoader().discover(
        str(ROOT / "tests"), pattern="test_*.py", top_level_dir=str(ROOT / "tests")
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(f"\n{'✓ 全部通过' if result.wasSuccessful() else '✗ 存在失败用例'}")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())

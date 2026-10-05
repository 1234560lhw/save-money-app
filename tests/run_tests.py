"""第一步测试入口：不依赖 pytest，直接运行即可。

用法（在项目根目录）::

    .venv\\Scripts\\python.exe tests\\run_tests.py          # 跑全部
    .venv\\Scripts\\python.exe tests\\run_tests.py -v       # 显示每条用例

装了 pytest 也可以用 ``pytest tests -v``。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TESTS_DIR.parent
for path in (str(TESTS_DIR), str(PROJECT_ROOT / "core"), str(PROJECT_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

# Windows 控制台默认 GBK，中文测试名会乱码，统一切到 UTF-8
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

from utils.tempfix import apply as apply_tempfix  # noqa: E402

apply_tempfix()


def build_suite() -> unittest.TestSuite:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for module in ("test_db", "test_stats", "test_goals", "test_ui_layout",
                   "test_balance_and_charts"):
        suite.addTests(loader.loadTestsFromName(module))
    return suite


def main() -> int:
    verbosity = 2 if {"-v", "--verbose"} & set(sys.argv[1:]) else 1
    print("=" * 68)
    print("存钱罐 · 业务逻辑 + 界面结构测试（不需要打开窗口）")
    print("=" * 68)
    runner = unittest.TextTestRunner(verbosity=verbosity, buffer=False)
    result = runner.run(build_suite())
    print("-" * 68)
    print(f"用例总数 {result.testsRun} | 失败 {len(result.failures)} | "
          f"错误 {len(result.errors)} | 跳过 {len(result.skipped)}")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())

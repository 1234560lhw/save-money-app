"""测试公共设施。

* 把 ``core/``、``apps/``（共享 UI）加入 ``sys.path``，让测试能 import 生产代码；
* 套用临时目录兼容补丁（受限沙箱下必需）；
* 每个测试都用独立的临时数据库，互不干扰。
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CORE_DIR = PROJECT_ROOT / "core"
APPS_DIR = PROJECT_ROOT / "apps"
for path in (str(CORE_DIR), str(APPS_DIR), str(PROJECT_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from utils.tempfix import apply as apply_tempfix  # noqa: E402

apply_tempfix()

import db  # noqa: E402
from utils import paths  # noqa: E402


class DatabaseTestCase(unittest.TestCase):
    """带独立临时数据库的测试基类。"""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory(prefix="savemoney-test-")
        self.tmp = Path(self._tmpdir.name)
        self.db_file = self.tmp / "test.db"

        self._env_backup = {
            key: os.environ.get(key)
            for key in ("SAVE_MONEY_DATA_DIR", "SAVE_MONEY_DB_FILE")
        }
        os.environ["SAVE_MONEY_DATA_DIR"] = str(self.tmp)
        os.environ["SAVE_MONEY_DB_FILE"] = str(self.db_file)

        db.reset_runtime_state()
        db.set_database_path(self.db_file)
        db.init_database(force=True)

    def tearDown(self) -> None:
        db.reset_runtime_state()
        db.set_database_path(None)
        for key, value in self._env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._cleanup_tmp()

    def _cleanup_tmp(self) -> None:
        """删掉临时目录。

        Windows 上 sqlite 刚关闭的文件句柄可能还会短暂占用（尤其是故意
        喂了坏文件的用例），因此重试几次，最后仍失败也不让测试报错——
        系统临时目录本身会被回收。
        """
        import gc
        import time

        for attempt in range(3):
            gc.collect()
            try:
                self._tmpdir.cleanup()
                return
            except (PermissionError, OSError):
                time.sleep(0.05 * (attempt + 1))
        try:
            self._tmpdir._finalizer.detach()  # type: ignore[attr-defined]
        except Exception:
            pass

    # ---- 便捷断言 ----

    def assertMoney(self, actual, expected: str, msg: str | None = None) -> None:
        from decimal import Decimal

        self.assertEqual(Decimal(str(actual)), Decimal(expected), msg)


def field_paths() -> dict[str, str]:
    """打印当前路径配置（排错用）。"""
    return paths.describe()

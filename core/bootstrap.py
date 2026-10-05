"""启动引导：统一处理 import 路径与数据库初始化。

桌面端与手机端的入口都先调用 :func:`bootstrap`，避免这段样板代码各写一遍。

为什么需要它
------------
本项目按"共享核心 + 两个前端"组织（见 docs/目录结构.md）：

* ``core/``   共享核心，内部用顶层包名互相导入（``from db... import``）；
* ``apps/``   两个前端，导入共享 UI 时用 ``from _shared import ...``。

因此启动时要把 ``core/`` 和 ``apps/`` 两个目录放进 ``sys.path``。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def ensure_sys_path() -> list[str]:
    """把 ``core/``、``apps/``、项目根目录加入 ``sys.path``，返回新增的路径。

    根目录是为了 ``scripts.*``（演示数据等开发脚本）可导入。
    """
    added: list[str] = []
    for relative in ("core", "apps", "."):
        path = str((PROJECT_ROOT / relative).resolve())
        if path not in sys.path:
            sys.path.insert(0, path)
            added.append(path)
    return added


def enable_utf8_console() -> None:
    """Windows 控制台默认 GBK，中文日志会乱码或报错，统一切到 UTF-8。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass
    os.environ.setdefault("PYTHONUTF8", "1")


def bootstrap(*, data_dir: str | os.PathLike[str] | None = None,
              db_file: str | os.PathLike[str] | None = None,
              seed_demo: bool = False) -> dict[str, object]:
    """准备运行环境：路径 -> 数据库 -> 返回初始化信息。

    ``data_dir`` / ``db_file`` 一般只在开发调试时传（把数据放到工作区内，
    方便随时清空重来）。

    数据目录不可写时会**自动换到下一个候选目录**（见 ``utils/paths.py``），
    只有所有候选都不可用才抛 ``utils.paths.DataDirError``。
    """
    ensure_sys_path()
    enable_utf8_console()

    if data_dir is not None:
        os.environ["SAVE_MONEY_DATA_DIR"] = str(data_dir)
    if db_file is not None:
        os.environ["SAVE_MONEY_DB_FILE"] = str(db_file)

    from utils.tempfix import apply as apply_tempfix

    apply_tempfix()

    import db
    from utils import paths

    # 先把数据目录定下来（会自动挑选可写的候选目录）。
    # 不先确认可写的话，后面会以 "unable to open database file"
    # 这种看不出原因的方式炸掉。
    paths.app_data_dir()

    info = db.init_database(force=True)
    info["paths"] = paths.describe()

    if seed_demo:
        from scripts.demo_data import seed_demo_data  # type: ignore

        info["demo"] = seed_demo_data()

    return info

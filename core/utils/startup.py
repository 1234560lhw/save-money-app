"""启动失败时的友好提示。

为什么需要它
------------
打包后的 exe 由 PyInstaller 的 ``--windowed`` 模式启动，没有控制台，
一旦抛异常用户只会看到一个英文 traceback 弹窗（"Failed to execute script
app_entry ... unable to open database file"），完全不知道该怎么办。

这里做两件事：

1. 启动前先确认数据目录可写，不可写就换成候选目录；
   全都不可写时给出**人话**说明（列出试过哪些目录），而不是崩掉；
2. 提供 :func:`show_error`，在 Windows 上用系统消息框显示，
   其它平台退回控制台输出。

被 :mod:`bootstrap` 与两个入口共同使用。
"""

from __future__ import annotations

import sys


def show_error(title: str, message: str) -> None:
    """弹一个错误提示框（Windows 用系统 MessageBox）。"""
    print(f"[{title}] {message}", file=sys.stderr)
    if not sys.platform.startswith("win"):
        return
    try:  # pragma: no cover - 依赖平台
        import ctypes

        # 0x10 = MB_ICONERROR, 0x0 = MB_OK, 0x40000 = MB_TOPMOST
        ctypes.windll.user32.MessageBoxW(None, message, title, 0x10 | 0x40000)
    except Exception:  # noqa: BLE001
        pass


def prepare_data_dir() -> str | None:
    """确保数据目录可用。

    返回 ``None`` 表示正常；否则返回给用户看的错误说明。
    """
    try:
        from utils import paths

        paths.app_data_dir()
        return None
    except Exception as exc:  # noqa: BLE001 - 兜底所有路径类异常
        from utils import paths

        tried = "\n".join(f"    · {line}" for line in paths.probe_log())
        return (
            "找不到可以保存账本的位置，应用无法启动。\n\n"
            f"已尝试的目录：\n{tried or '    （无）'}\n\n"
            "常见原因：\n"
            "  1. 系统盘权限受限或组策略禁止写入用户目录；\n"
            "  2. 安全软件拦截了本程序的文件写入。\n\n"
            "可以这样解决：\n"
            "  · 把程序放到非系统盘（如 D 盘）再运行；\n"
            "  · 手动指定数据目录：设置环境变量 SAVE_MONEY_DATA_DIR\n"
            "    指向一个可写文件夹后重新启动。\n\n"
            f"技术信息：{type(exc).__name__}: {exc}"
        )

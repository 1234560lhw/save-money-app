"""临时目录兼容补丁。

背景
----
在某些受限沙箱（例如 DSH 的 workspace-write 模式）下，Python 的
``tempfile.mkdtemp()`` 以 mode ``0o700`` 创建目录，Windows 上会得到一张
非常受限的 ACL，导致随后写入该目录内的文件被拒绝（``PermissionError`` /
``WinError 5``）。pip 解包 wheel、读取元数据全部依赖 ``mkdtemp``，于是
``pip install`` 在这种环境下必然失败。

处理办法
--------
以 mode ``0o777`` 创建目录（Windows 上等价于"不设置额外限制"，ACL 完全
继承父目录），只放宽当前进程自己创建的临时目录权限，不触碰任何已存在的
目录，也不改变文件的最终权限。

用法
----
    from utils.tempfix import apply as apply_tempfix
    apply_tempfix()          # 在 import pip / 调用 pip 之前执行

或在命令行直接运行本文件（幂等地打好补丁后返回）。
"""

from __future__ import annotations

import os
import shutil
import tempfile
from typing import Any

_APPLIED = False


def _relaxed_mkdtemp(suffix: str | None = None, prefix: str | None = None,
                     dir: str | None = None) -> str:
    """与 ``tempfile.mkdtemp`` 等价，但用 0o777 创建目录以便权限可继承。"""
    suffix = suffix or ""
    prefix = prefix or tempfile.gettempprefix()
    dir = dir or tempfile.gettempdir()

    names = tempfile._get_candidate_names()  # type: ignore[attr-defined]
    for _ in range(tempfile.TMP_MAX):
        path = os.path.join(dir, prefix + next(names) + suffix)
        try:
            os.mkdir(path, 0o777)
        except FileExistsError:
            continue
        return os.path.abspath(path)
    raise FileExistsError("no usable temporary directory name found")


def apply() -> bool:
    """幂等地打补丁；返回本次调用是否真正做了替换。"""
    global _APPLIED
    if _APPLIED:
        return False
    tempfile.mkdtemp = _relaxed_mkdtemp  # type: ignore[assignment]
    _APPLIED = True
    return True


def use_workspace_temp(root: str) -> str:
    """把 TMP/TEMP/TMPDIR 指向工作区内一个稳定存在的目录。

    只设置环境变量，不做任何权限修改；目录不存在时才创建。
    """
    path = os.path.join(root, ".tmp")
    os.makedirs(path, exist_ok=True)
    for key in ("TMP", "TEMP", "TMPDIR"):
        os.environ[key] = path
    tempfile.tempdir = None  # 让 tempfile 重新读取环境变量
    return path


def show() -> dict[str, Any]:
    """返回当前临时目录状态，便于排查。"""
    return {
        "applied": _APPLIED,
        "tempdir": tempfile.gettempdir(),
        "TMP": os.environ.get("TMP"),
        "TEMP": os.environ.get("TEMP"),
    }


def _selftest() -> int:
    """自检：打补丁后必须能在新建的临时目录里写入文件。"""
    apply()
    try:
        d = tempfile.mkdtemp(prefix="tempfix-selftest-")
        probe = os.path.join(d, "probe.bin")
        with open(probe, "wb") as fh:
            fh.write(b"ok")
        with open(probe, "rb") as fh:
            assert fh.read() == b"ok"
        shutil.rmtree(d, ignore_errors=True)
    except OSError as exc:  # pragma: no cover - 依赖运行环境
        print(f"[tempfix] FAILED: {type(exc).__name__}: {exc}")
        print(f"[tempfix] state: {show()}")
        return 1
    print(f"[tempfix] OK  mkdtemp 可写  state={show()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_selftest())

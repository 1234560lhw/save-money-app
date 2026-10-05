"""把依赖安装进 .venv（绕过受限沙箱下 pip 临时目录不可写的问题）。

为什么需要它
------------
``python -m venv .venv`` 里的 ensurepip 和 ``pip install`` 都会先
``tempfile.mkdtemp()`` 建临时目录再写文件。在受限沙箱下这种目录不可写，
报 ``PermissionError: [Errno 13]``。

这个脚本先用 ``core/utils/tempfix.py`` 打补丁（临时目录按 0o777 创建，
权限可继承），再调用 pip 的 Python API，把包装进 ``.venv``。
它不修改任何系统目录，也不提权。

用法（用宿主 Python 运行，不是 .venv 里的）：
    python scripts/install_deps.py                 # 安装 requirements.txt
    python scripts/install_deps.py flet==0.28.3    # 安装指定包
    python scripts/install_deps.py --only-binary   # 只用预编译 wheel
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VENV_DIR = PROJECT_ROOT / ".venv"
TARGET_SITE = VENV_DIR / "Lib" / "site-packages"
REQUIREMENTS = PROJECT_ROOT / "requirements.txt"


def bootstrap_pip_into_venv() -> int:
    """把 pip 从宿主 Python 的 bundled wheel 装进 .venv（离线，不走网络）。"""
    if (TARGET_SITE / "pip").is_dir():
        print("[deps] .venv 已存在 pip，跳过引导")
        return 0

    import ensurepip
    import tempfile
    import zipfile

    bundled = Path(ensurepip.__file__).parent / "_bundled"
    wheels = sorted(bundled.glob("pip-*.whl"))
    if not wheels:
        print(f"[deps] 找不到内置 pip wheel: {bundled}")
        return 1

    TARGET_SITE.mkdir(parents=True, exist_ok=True)
    for wheel in wheels:
        print(f"[deps] 解包 {wheel.name} -> {TARGET_SITE}")
        with zipfile.ZipFile(wheel) as zf:
            zf.extractall(TARGET_SITE)
    print("[deps] pip 引导完成")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="安装项目依赖到 .venv")
    parser.add_argument("packages", nargs="*", help="要安装的包；默认读 requirements.txt")
    parser.add_argument("-r", "--requirements", action="append", default=[],
                        help="依赖清单文件（可重复传入）")
    parser.add_argument("--only-binary", action="store_true", default=True,
                        help="只接受预编译 wheel（默认开启）")
    parser.add_argument("--no-cache", action="store_true", help="禁用 pip 缓存")
    # 允许把 "-r file" 这种 pip 原生写法透传进来
    args, unknown = parser.parse_known_args(argv)

    if not VENV_DIR.is_dir():
        print(f"[deps] 虚拟环境不存在: {VENV_DIR}")
        print("[deps] 先运行: python -m venv .venv")
        return 1

    sys.path.insert(0, str(PROJECT_ROOT / "core"))
    from utils.tempfix import apply as apply_tempfix, show, use_workspace_temp

    apply_tempfix()
    use_workspace_temp(str(PROJECT_ROOT))
    print(f"[deps] 临时目录: {show()}")

    rc = bootstrap_pip_into_venv()
    if rc != 0:
        return rc

    # 让随后 import 的 pip 一定是 .venv 里的那份
    sys.path.insert(0, str(TARGET_SITE))
    for mod in [m for m in list(sys.modules) if m == "pip" or m.startswith("pip.")]:
        del sys.modules[mod]

    from pip._internal.cli.main import main as pip_main

    requirements = list(args.requirements)
    specs = list(args.packages) + list(unknown)
    if not requirements and not specs:
        requirements = [str(REQUIREMENTS)]

    cmd = ["install", "--target", str(TARGET_SITE), "--upgrade"]
    if args.only_binary:
        cmd.append("--only-binary=:all:")
    if args.no_cache:
        cmd.append("--no-cache-dir")
    cmd += [f"-r{path}" for path in requirements]
    cmd += specs

    print(f"[deps] pip {' '.join(cmd)}")
    return int(pip_main(cmd) or 0)


if __name__ == "__main__":
    raise SystemExit(main())

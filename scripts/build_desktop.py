"""把桌面端打包成独立 exe（PyInstaller）。

为什么选 PyInstaller 而不是 ``flet build windows``
-------------------------------------------------
``flet build`` 会去下载完整的 Flutter SDK（约 1GB）再用 Flutter 重新编译，
产物更"正规"（体积也更大），但首次构建要拉一大堆东西。用户希望桌面端先出
一个能双击运行的 exe，PyInstaller 只需要 pip 装一个包，几十秒就能出结果。

区别要知道：

* PyInstaller 版：把 Python 解释器 + 应用代码 + flet 桌面客户端打在一起，
  体积约 60~120MB，双击即用，**不需要装 Python**；
* ``flet build`` 版：真正的 Flutter 桌面应用，体积更小、启动更快，
  但要先具备 Flutter 工具链。

用法::

    .venv\\Scripts\\python.exe scripts\\build_desktop.py            # 直接打包
    .venv\\Scripts\\python.exe scripts\\build_desktop.py --clean    # 先清掉旧产物
    .venv\\Scripts\\python.exe scripts\\build_desktop.py --console  # 保留控制台窗口（排查启动问题）

产出：``dist\\Flipped的存钱罐\\Flipped的存钱罐.exe``
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENTRY = PROJECT_ROOT / "apps" / "desktop" / "app_entry.py"
ASSETS_DIR = PROJECT_ROOT / "assets"
ICON = ASSETS_DIR / "branding" / "app_icon.ico"
BUILD_DIR = PROJECT_ROOT / "build" / "pyinstaller"
DIST_DIR = PROJECT_ROOT / "dist"

#: 应用显示名（exe 文件名与窗口标题一致）
APP_NAME = "Flipped的存钱罐"
#: PyInstaller 的 --add-data 分隔符用的是 os.pathsep 语义；
#: 本机实测 Windows 上也要用 ":"（用 ";" 会被判成语法错误）。
SEP = ":"


def ensure_pyinstaller() -> bool:
    """确保 PyInstaller 可用（顺带确认 Pillow 存在，图标处理要用）。"""
    try:
        import PyInstaller  # noqa: F401
        return True
    except ImportError:
        pass

    print("[build] 未安装 PyInstaller，正在安装…")
    installer = PROJECT_ROOT / "scripts" / "install_deps.py"
    result = subprocess.run([sys.executable, str(installer), "pyinstaller"],
                            cwd=str(PROJECT_ROOT))
    if result.returncode != 0:
        print("[build] PyInstaller 安装失败")
        return False
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("[build] 安装后仍无法导入 PyInstaller")
        return False
    return True


def build(*, clean: bool, console: bool) -> int:
    if not ENTRY.is_file():
        print(f"[build] 找不到入口文件：{ENTRY}")
        return 1
    if not ICON.is_file():
        print(f"[build] 找不到图标：{ICON}")
        print("[build] 先运行 scripts\\prepare_brand_icon.py 生成图标")
        return 1

    if clean:
        for path in (BUILD_DIR, DIST_DIR / APP_NAME):
            if path.exists():
                print(f"[build] 清理 {path.relative_to(PROJECT_ROOT)}")
                shutil.rmtree(path, ignore_errors=True)

    # flet 的桌面客户端是运行时动态导入的，PyInstaller 静态分析看不到，
    # 必须显式声明，否则打出来的 exe 启动会报找不到客户端。
    hidden_imports = [
        "flet_desktop",
        "flet",
        "flet.core",
    ]
    # 应用自身的包全是"顶层包名"导入（见 docs/目录结构.md），
    # PyInstaller 从 app_entry.py 出发能顺着静态 import 找全，
    # 但 services/db/repositories 里有延迟导入，这里一并显式声明。
    for name in ("db", "db.repositories", "services", "utils", "models",
                 "_shared", "_shared.views"):
        hidden_imports.append(name)

    # (源路径, 打包后的相对目录) —— 分开存，避免路径里出现多个分隔符
    datas: list[tuple[Path, str]] = [(ASSETS_DIR, "assets")]

    # 关键：把 flet_desktop 自带的桌面客户端二进制一起打包。
    # 它不在 .py 依赖图里，PyInstaller 不会自动收集；缺了它 exe 启动时
    # 会去下载/解压到 ~/.flet，用户目录不可写就直接崩。
    try:
        import flet_desktop

        client_dir = Path(flet_desktop.__file__).parent / "app"
        if client_dir.is_dir():
            datas.append((client_dir, "flet_desktop/app"))
            size_mb = sum(f.stat().st_size for f in client_dir.rglob("*")
                          if f.is_file()) / 1024 / 1024
            print(f"[build] 打包内置 Flet 客户端（{size_mb:.0f} MB）")
        else:
            print(f"[build] ⚠ 没找到 Flet 客户端目录：{client_dir}")
            print("[build] ⚠ 打出来的 exe 首次运行会尝试联网下载客户端")
    except ImportError:
        print("[build] ⚠ 未安装 flet_desktop，exe 可能无法启动窗口")

    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--name", APP_NAME,
        "--icon", str(ICON),
        "--distpath", str(DIST_DIR),
        "--workpath", str(BUILD_DIR),
        "--specpath", str(BUILD_DIR),
        "--paths", str(PROJECT_ROOT / "core"),
        "--paths", str(PROJECT_ROOT / "apps"),
    ]
    for source, dest in datas:
        args.append(f"--add-data={source}{SEP}{dest}")
    if not console:
        args.append("--windowed")     # 不弹黑色控制台窗口
    for name in hidden_imports:
        args += ["--hidden-import", name]
    args.append(str(ENTRY))

    print("[build] " + " ".join(args[:6]) + " …")
    result = subprocess.run(args, cwd=str(PROJECT_ROOT))
    if result.returncode != 0:
        print(f"[build] 打包失败（退出码 {result.returncode}）")
        return result.returncode

    exe = DIST_DIR / APP_NAME / f"{APP_NAME}.exe"
    if exe.is_file():
        size_mb = exe.stat().st_size / 1024 / 1024
        print(f"\n[build] ✅ 打包完成：{exe}")
        print(f"[build]    主程序 {size_mb:.1f} MB")
        total = sum(f.stat().st_size for f in exe.parent.rglob("*") if f.is_file())
        print(f"[build]    整个目录 {total / 1024 / 1024:.1f} MB")
        print(f"[build]    双击 {exe.name} 即可运行；数据存在 %APPDATA%\\SaveMoneyApp")
        print("[build]    换电脑时把整个目录拷过去就行")
    else:
        print(f"[build] 构建结束但没找到 exe，检查 {DIST_DIR / APP_NAME}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="打包桌面端 exe")
    parser.add_argument("--clean", action="store_true", help="先清掉旧产物")
    parser.add_argument("--console", action="store_true",
                        help="保留控制台窗口，便于看启动报错")
    args = parser.parse_args(argv)

    if not ensure_pyinstaller():
        return 1
    return build(clean=args.clean, console=args.console)


if __name__ == "__main__":
    raise SystemExit(main())

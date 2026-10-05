"""桌面端（Windows / macOS / Linux）应用入口。

与手机端的唯一区别
------------------
* 窗口尺寸、标题按桌面习惯设置；
* 数据默认放在系统用户数据目录（Windows 为 ``%APPDATA%\\SaveMoneyApp``）；
* 支持 ``--dev`` 把数据放到项目内 ``.devdata/``，方便开发期随便造数据。

界面代码全部来自 ``apps/_shared``，与手机端共用一套。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
for _path in (str(PROJECT_ROOT / "core"), str(PROJECT_ROOT / "apps")):
    if _path not in sys.path:
        sys.path.insert(0, _path)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="存钱罐 · 桌面端")
    parser.add_argument("--dev", action="store_true",
                        help="开发模式：数据放到 .devdata/，并打开热重载")
    parser.add_argument("--demo", action="store_true", help="写入一批演示数据（仅开发用）")
    parser.add_argument("--web", action="store_true",
                        help="在浏览器里预览（等同手机端布局，便于调 UI）")
    parser.add_argument("--port", type=int, default=8550, help="--web 模式下的端口")
    return parser.parse_args(argv)


def _prepare_flet_view() -> None:
    """让打包后的 exe 直接用随包携带的 Flet 桌面客户端。

    背景：``flet_desktop`` 会优先找 ``flet_desktop/app/flet/flet.exe``；
    找不到就尝试解压/下载到 ``~/.flet``。打包后如果既没带上客户端、
    用户目录又不可写，启动就会直接崩（早期版本就是这个问题）。

    这个函数做两件事：
    1. 找到随包携带的客户端目录；
    2. 若用户目录里的版本没装好，就把客户端复制过去，
       这样即使用户把 exe 单独拷到别的机器也能起得来。
    """
    import os
    import shutil

    try:
        import flet_desktop
    except ImportError:  # pragma: no cover - 桌面端一定装了
        return

    bundled = Path(flet_desktop.__file__).parent / "app"
    if not bundled.is_dir():
        return

    # 1) 直接指向随包客户端（最省事，也不写用户目录）
    os.environ.setdefault("FLET_VIEW_PATH", str(bundled))

    # 2) 顺手把客户端同步到 ~/.flet，给"只拷 exe 不带目录"的场景兜底
    try:
        version = getattr(getattr(flet_desktop, "version", None), "version", None)
        if not version:
            return
        target = Path.home() / ".flet" / "bin" / f"flet-{version}" / "flet"
        exe_name = "flet.exe" if sys.platform.startswith("win") else "flet"
        if not (target / exe_name).exists():
            shutil.copytree(bundled / "flet", target, dirs_exist_ok=True)
            print(f"[bootstrap] 已把 Flet 客户端安装到 {target}")
    except (OSError, shutil.Error) as exc:
        # 用户目录不可写不影响使用，FLET_VIEW_PATH 已经兜住了
        print(f"[bootstrap] 跳过往 ~/.flet 安装客户端（{type(exc).__name__}）")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    import flet as ft

    _prepare_flet_view()

    from bootstrap import bootstrap
    from _shared.shell import AppShell
    from utils.paths import APP_TITLE, DataDirError, asset_path
    from utils.startup import prepare_data_dir, show_error

    # 先确认有地方存账本；不可写就换候选目录，全都不可写则给人话提示
    problem = prepare_data_dir()
    if problem:
        show_error(APP_TITLE, problem)
        return 2

    dev_data = PROJECT_ROOT / ".devdata" if args.dev else None
    try:
        info = bootstrap(data_dir=dev_data, seed_demo=args.demo)
    except DataDirError as exc:
        show_error(APP_TITLE, str(exc))
        return 2
    except Exception as exc:  # noqa: BLE001 - 打包后没有控制台，必须弹窗
        show_error(APP_TITLE, f"启动失败：{type(exc).__name__}: {exc}")
        return 3

    def app(page: ft.Page) -> None:
        page.window.width = 420
        page.window.height = 860
        page.window.min_width = 380
        page.window.min_height = 600
        page.window.title_bar_hidden = False
        shell = AppShell(page, app_title=APP_TITLE)
        shell.mount()

    print(f"[{APP_TITLE}] 桌面端启动 | 数据目录：{info['paths']['data_dir']}")
    print(f"[{APP_TITLE}] 数据库：{info['paths']['db_path']}")

    if args.web:
        # 浏览器预览：和手机 App 一样的窄屏布局，方便实时调 UI
        ft.app(target=app, view=ft.AppView.WEB_BROWSER, port=args.port)
    else:
        ft.app(target=app, assets_dir=str(asset_path()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

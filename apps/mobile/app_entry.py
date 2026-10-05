"""手机端（Android / iOS）应用入口。

与桌面端的区别
--------------
* 窗口/页面尺寸按整屏设置（打包成 APK 后就是全屏）；
* 数据放在应用私有目录（Flet 打包后由 ``FLET_APP_STORAGE_DATA`` 指定）；
* 不做桌面专属的窗口尺寸限制。

开发期用 ``python apps/mobile/app_entry.py --web`` 可以在浏览器里
按手机尺寸预览，改代码后刷新即可看到效果。
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
    parser = argparse.ArgumentParser(description="存钱罐 · 手机端")
    parser.add_argument("--dev", action="store_true",
                        help="开发模式：数据放到工作区内，方便清空重来")
    parser.add_argument("--demo", action="store_true", help="写入一批演示数据（仅开发用）")
    parser.add_argument("--web", action="store_true",
                        help="在浏览器里预览（否则以原生窗口运行）")
    parser.add_argument("--port", type=int, default=8551, help="--web 模式下的端口")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    import flet as ft

    from bootstrap import bootstrap
    from _shared.shell import AppShell
    from utils.paths import APP_TITLE, DataDirError, asset_path
    from utils.startup import prepare_data_dir, show_error

    # 先确认有地方存账本（手机端是应用私有目录，一般都可写）
    problem = prepare_data_dir()
    if problem:
        show_error(APP_TITLE, problem)
        return 2

    dev_data = PROJECT_ROOT / ".devdata" / "mobile" if args.dev else None
    try:
        info = bootstrap(data_dir=dev_data, seed_demo=args.demo)
    except DataDirError as exc:
        show_error(APP_TITLE, str(exc))
        return 2
    except Exception as exc:  # noqa: BLE001 - 打包后没有控制台，必须弹窗
        show_error(APP_TITLE, f"启动失败：{type(exc).__name__}: {exc}")
        return 3

    def app(page: ft.Page) -> None:
        # 手机端是全屏应用，这里给出与常见手机一致的视口
        page.window.width = 400
        page.window.height = 800
        shell = AppShell(page, app_title=APP_TITLE, max_content_width=None)
        shell.mount()

    print(f"[{APP_TITLE}] 手机端启动 | 数据目录：{info['paths']['data_dir']}")
    print(f"[{APP_TITLE}] 数据库：{info['paths']['db_path']}")

    if args.web:
        # 浏览器预览：把窗口调成手机尺寸即可看到手机端布局
        print(f"[{APP_TITLE}] 浏览器预览：http://127.0.0.1:{args.port}/")
        ft.app(target=app, view=ft.AppView.WEB_BROWSER, port=args.port)
    else:
        # 默认以原生窗口运行（真机打包后就是全屏原生应用）
        ft.app(target=app, assets_dir=str(asset_path()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

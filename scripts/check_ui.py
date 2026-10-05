"""无头渲染自检：不需要打开窗口，直接把四个页面构建一遍。

用途
----
* 快速发现"控件参数写错""字段名不存在"这类只有运行时才暴露的问题；
* 也可以用来确认业务数据能正确流到界面上。

用法::

    .venv\\Scripts\\python.exe scripts\\check_ui.py
    .venv\\Scripts\\python.exe scripts\\check_ui.py -v     # 打印控件树规模
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
for _path in (str(PROJECT_ROOT / "core"), str(PROJECT_ROOT / "apps")):
    if _path not in sys.path:
        sys.path.insert(0, _path)


class FakeOverlay(list):
    """page.overlay 只需要能 append。"""


class FakePage:
    """最小可用的 Page 替身，只提供页面构建时会用到的属性。"""

    def __init__(self) -> None:
        self.title = ""
        self.theme = None
        self.dark_theme = None
        self.theme_mode = None
        self.padding = 0
        self.spacing = 0
        self.appbar = None
        self.navigation_bar = None
        self.window = type("Window", (), {})()
        self.overlay = FakeOverlay()
        self.opened: list = []
        self.closed: list = []
        self.updates = 0
        self.controls: list = []

    def add(self, *controls):
        self.controls.extend(controls)

    def update(self):
        self.updates += 1

    def open(self, control):
        self.opened.append(control)

    def close(self, control):
        self.closed.append(control)

    def run_task(self, handler):
        return None


def count_controls(node, seen: set[int] | None = None) -> int:
    """递归数一数控件树里有多少个控件（顺便验证树结构可遍历）。"""
    seen = seen if seen is not None else set()
    if node is None or id(node) in seen:
        return 0
    seen.add(id(node))
    total = 1
    children = getattr(node, "controls", None)
    if isinstance(children, (list, tuple)):
        for child in children:
            total += count_controls(child, seen)
    content = getattr(node, "content", None)
    if content is not None:
        total += count_controls(content, seen)
    for attr in ("actions", "destinations", "tabs", "segments"):
        items = getattr(node, attr, None)
        if isinstance(items, (list, tuple)):
            for item in items:
                total += count_controls(item, seen)
    return total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="无头渲染自检")
    parser.add_argument("-v", "--verbose", action="store_true", help="打印控件数量")
    args = parser.parse_args(argv)

    # 关键顺序：先打临时目录补丁，再创建临时目录。
    # 否则 mkdtemp 会用 0700 建目录，在受限环境里后续写入会被拒绝。
    from utils.tempfix import apply as apply_tempfix

    apply_tempfix()

    tmp_root = PROJECT_ROOT / ".tmp"
    tmp_root.mkdir(parents=True, exist_ok=True)
    os.environ["TMP"] = str(tmp_root)
    os.environ["TEMP"] = str(tmp_root)
    tmp = Path(tempfile.mkdtemp(prefix="savemoney-ui-", dir=tmp_root))
    os.environ["SAVE_MONEY_DATA_DIR"] = str(tmp)
    os.environ["SAVE_MONEY_DB_FILE"] = str(tmp / "ui_check.db")

    from bootstrap import bootstrap

    info = bootstrap(seed_demo=True)
    print(f"[check] 数据库：{info['paths']['db_path']}")

    import flet as ft

    from _shared.shell import AppShell

    page = FakePage()
    shell = AppShell(page, app_title="自检")
    failures: list[str] = []

    try:
        shell.mount()
        print("[check] shell.mount() 通过")
    except Exception as exc:  # noqa: BLE001
        import traceback

        print("[check] shell.mount() 失败")
        traceback.print_exc()
        return 1

    names = ["首页仪表盘", "记一笔", "流水列表", "设置"]
    for index, name in enumerate(names):
        try:
            view = shell._view(index)
            view.mark_dirty()
            tree = view.build()
            size = count_controls(tree)
            print(f"[check] {name} 渲染通过（控件数 {size}）" if args.verbose
                  else f"[check] {name} 渲染通过")
        except Exception as exc:  # noqa: BLE001
            import traceback

            failures.append(name)
            print(f"[check] {name} 渲染失败：{type(exc).__name__}: {exc}")
            traceback.print_exc()

    # 顺带验证：改数据后刷新不报错
    try:
        shell.notify_data_changed(message=None)
        print("[check] 数据变更刷新通过")
    except Exception as exc:  # noqa: BLE001
        failures.append("notify_data_changed")
        print(f"[check] 数据变更刷新失败：{type(exc).__name__}: {exc}")

    if failures:
        print(f"[check] 失败项：{', '.join(failures)}")
        return 1
    print("[check] 全部通过 ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

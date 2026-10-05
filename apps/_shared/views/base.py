"""页面基类：统一页面契约。"""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from _shared import theme

if TYPE_CHECKING:  # pragma: no cover
    from _shared.shell import AppShell


class BaseView:
    """所有页面的父类。

    页面只做两件事：``build()`` 产出控件树，``load()`` 从 services 取数据。
    取数出错时统一显示错误卡片，不至于整个应用崩掉。
    """

    def __init__(self, shell: "AppShell"):
        self.shell = shell
        self.page = shell.page
        self.palette = theme.Palette(shell.page)
        self._dirty = True
        self._error: str | None = None

    # ------------------------------------------------------------ 需要子类实现

    def load(self) -> None:
        """从数据库/service 取数。子类覆盖。"""

    def render(self) -> ft.Control:
        """用已取到的数据构建界面。子类覆盖。"""
        raise NotImplementedError

    # ------------------------------------------------------------ 通用逻辑

    def mark_dirty(self) -> None:
        self._dirty = True

    def build(self) -> ft.Control:
        """对外入口：需要时重新取数，然后渲染。"""
        if self._dirty:
            self._error = None
            try:
                self.palette = theme.Palette(self.page)
                self.load()
            except Exception as exc:  # noqa: BLE001 - 页面级兜底，避免整个应用退出
                self._error = f"{type(exc).__name__}: {exc}"
            self._dirty = False
        if self._error:
            return self.error_view(self._error)
        # 这里**只负责排内容**：滚动交给外壳的滚动容器
        # （apps/_shared/shell.py 的 _content_wrapper）。
        # 早期版本在页面上也加了 scroll，但父级不是滚动视图，手势会被吃掉，
        # 手机上表现为"滑不动"。
        return ft.Column(
            [self.render()],
            spacing=0,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )

    def error_view(self, text: str) -> ft.Control:
        from _shared import components as ui

        return ui.card(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.ERROR_OUTLINE, color="#C62828"),
                            ft.Text("页面加载失败", weight=ft.FontWeight.W_600),
                        ],
                        spacing=theme.PAD_S,
                    ),
                    ft.Text(text, size=theme.FONT_SMALL, color=self.palette.muted,
                            selectable=True),
                    ft.Text("如果是第一次运行，可尝试重启应用；数据文件损坏时"
                            "可在「设置 - 数据备份」导入之前的备份。",
                            size=theme.FONT_TINY, color=self.palette.muted),
                ],
                spacing=theme.PAD_S,
            ),
            dark=self.palette.dark,
        )

    # ------------------------------------------------------------ 便捷方法

    def toast(self, text: str, *, error: bool = False) -> None:
        from _shared import components as ui

        ui.message(self.page, text, error=error)

    def changed(self, message: str | None = None) -> None:
        """数据变更后调用：提示 + 刷新当前页。"""
        self.shell.notify_data_changed(message=message)

    def gap(self, size: int = theme.PAD_M) -> ft.Container:
        return ft.Container(height=size)

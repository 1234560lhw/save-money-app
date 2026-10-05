"""应用外壳：底部导航 4 标签 + 页面懒加载 + 全局刷新。

结构
----
::

    ┌──────────────────────────────┐
    │  当前页面内容（可滚动）        │
    ├──────────────────────────────┤
    │ 首页 │ 记一笔 │ 流水 │ 设置   │  <- NavigationBar
    └──────────────────────────────┘

* 页面按需创建，切换过的页面会缓存，切回来只重建内容不丢状态；
* 任何页面改了数据，调用 ``shell.notify_data_changed()``，
  所有页面会重新从数据库取数（单一数据源的简单实现）。
"""

from __future__ import annotations

from typing import Callable

import flet as ft

from _shared import theme
from _shared.views import AddTransactionView, HomeView, SettingsView, TransactionListView
from _shared.views.base import BaseView


class AppShell:
    """把四个页面和底部导航组装起来。"""

    TABS = [
        ("首页", ft.Icons.ACCOUNT_BALANCE_WALLET_OUTLINED, ft.Icons.ACCOUNT_BALANCE_WALLET),
        ("记一笔", ft.Icons.ADD_CIRCLE_OUTLINE, ft.Icons.ADD_CIRCLE),
        ("流水", ft.Icons.RECEIPT_LONG_OUTLINED, ft.Icons.RECEIPT_LONG),
        ("设置", ft.Icons.SETTINGS_OUTLINED, ft.Icons.SETTINGS),
    ]

    def __init__(self, page: ft.Page, *, app_title: str = "存钱罐",
                 max_content_width: int | None = 720,
                 on_new_transaction: Callable[[], None] | None = None):
        self.page = page
        self.app_title = app_title
        self.max_content_width = max_content_width
        self.current_index = 0
        self._views: dict[int, BaseView] = {}
        self._body: ft.Container | None = None
        self._nav: ft.NavigationBar | None = None
        self._bg: ft.Control | None = None
        self._root_stack: ft.Stack | None = None
        #: 最近一次 resize 事件报告的视口尺寸，作为尺寸兜底
        self._last_viewport: tuple[int, int] = (0, 0)

    # ------------------------------------------------------------ 生命周期

    def mount(self) -> None:
        """构建并挂到 page 上。"""
        self.page.title = self.app_title
        self.page.theme = theme.build_theme(dark=False)
        self.page.dark_theme = theme.build_theme(dark=True)
        # 背景交给 _background_layer()，画布本身必须透明才看得见
        self.page.bgcolor = "#00000000"
        self.page.padding = 0
        self.page.spacing = 0
        self.page.appbar = None      # 玻璃风格不用顶部工具栏，标题放进页面内容

        # 恢复上次选择的明暗模式（默认深色：毛玻璃质感在深色下最出效果）
        from services import settings_service

        saved_mode = settings_service.get_value(settings_service.KEY_THEME_MODE) or "dark"
        self.page.theme_mode = (ft.ThemeMode.LIGHT if saved_mode == "light"
                                else ft.ThemeMode.DARK)

        dark = self.page.theme_mode != ft.ThemeMode.LIGHT

        self._body = ft.Container(expand=True)
        self._nav = ft.NavigationBar(
            selected_index=0,
            on_change=self._on_nav_change,
            bgcolor="#00000000",
            elevation=0,
            border=ft.border.only(
                top=ft.BorderSide(1, theme.GLASS_EDGE_DARK if dark else theme.GLASS_EDGE_LIGHT)
            ),
            destinations=[
                ft.NavigationBarDestination(icon=outline, selected_icon=filled, label=label)
                for label, outline, filled in self.TABS
            ],
        )

        self.page.navigation_bar = self._nav
        # 关键：page.add() 是竖直堆叠，背景和内容必须放进同一个 Stack 才能叠放
        self._bg = self._background_layer()
        self._root_stack = ft.Stack([self._bg, self._content_wrapper()])
        # 注意事件名是 on_resized（不是 on_resize）。
        # flet 的事件是动态属性，写错名字不会报错、只会静默失效。
        self.page.on_resized = self._on_page_resize
        self.page.add(self._root_stack)
        self._render_current()
        self._sync_background_size()
        self.page.update()

    # ------------------------------------------------------------ 背景层

    def _size(self) -> tuple[int, int]:
        """当前视口尺寸。

        优先级：**page.width/height**（真实视口，会随窗口/浏览器缩放变化）
        > ``window.width/height``（启动时写死的静态值） > 兜底默认值。

        回归背景：早期只看 ``window.width/height``，而那两个值在浏览器里
        永远是启动参数、不会随 F12 或窗口缩放变化，于是背景层高度固定，
        页面一变大就露出白边。另外 ``page.on_resize`` 这个名字是错的
        （正确为 ``on_resized``），导致尺寸同步回调从未被调用 —— 两个问题
        叠加就是"深色背景没有铺满"。
        """
        def _positive(value: object) -> int:
            try:
                number = int(float(value))  # type: ignore[arg-type]
            except (TypeError, ValueError):
                return 0
            return number if number > 0 else 0

        # 1) 真实视口
        width = _positive(getattr(self.page, "width", 0))
        height = _positive(getattr(self.page, "height", 0))

        # 2) 回退到窗口设定值
        if not width or not height:
            window = getattr(self.page, "window", None)
            width = width or _positive(getattr(window, "width", 0))
            height = height or _positive(getattr(window, "height", 0))

        # 3) 再回退到最近一次 resize 事件报告的尺寸
        if not width or not height:
            width = width or _positive(self._last_viewport[0])
            height = height or _positive(self._last_viewport[1])

        return max(width, 360), max(height, 640)

    def _sync_background_size(self) -> None:
        """把背景层撑到整个窗口。

        背景是 Stack 里的渐变 + 定位光斑，如果不显式给尺寸，Stack 会按
        子控件的自然尺寸撑高，把下面的内容整体顶下去。
        """
        bg = getattr(self, "_bg", None)
        if bg is None:
            return
        width, height = self._size()
        bg.height = height
        if self.max_content_width:
            bg.width = width

    def _on_page_resize(self, event: ft.ControlEvent) -> None:
        """视口尺寸变化：重新铺背景。

        ``WindowResizeEvent`` 自带 width/height（flet 从事件 data 里解析），
        优先用它，比再读一次 page 属性更可靠。
        """
        width = int(getattr(event, "width", 0) or 0)
        height = int(getattr(event, "height", 0) or 0)
        if width > 0 and height > 0:
            self._last_viewport = (width, height)
        self._sync_background_size()
        self.page.update()

    def _background_layer(self) -> ft.Control:
        """整页背景：纯色，跟着主题走（深色主题深底、浅色主题浅底）。

        用户明确要求"不要背景那种圆形的元素"，所以这里不再画渐变和模糊光斑。
        """
        dark = self.page.theme_mode != ft.ThemeMode.LIGHT
        width, height = self._size()
        width = width if self.max_content_width else 0
        return theme.background_layer(dark, width=width, height=height)

    def _toggle_theme(self, _event: ft.ControlEvent) -> None:
        self.toggle_theme()

    def toggle_theme(self) -> None:
        """在浅色 / 深色之间切换，并把选择记进数据库。"""
        from services import settings_service

        self.page.theme_mode = (
            ft.ThemeMode.LIGHT if self.page.theme_mode == ft.ThemeMode.DARK else ft.ThemeMode.DARK
        )
        settings_service.set_value(
            settings_service.KEY_THEME_MODE,
            "dark" if self.page.theme_mode == ft.ThemeMode.DARK else "light",
        )
        # 明暗切换会同时影响背景层与所有玻璃面板，整页重建最不容易残留
        self.rebuild_all()

    def rebuild_all(self) -> None:
        """重建背景层与所有已创建页面（切换主题时用）。"""
        if self._body is None:
            return
        self._bg = self._background_layer()
        if self._root_stack is not None and self._root_stack.controls:
            self._root_stack.controls[0] = self._bg
        for view in self._views.values():
            view.mark_dirty()
        self._render_current()
        self._sync_background_size()
        self.page.update()

    def _content_wrapper(self) -> ft.Control:
        """内容区：跟窗口同宽，底部留出导航栏的高度。

        注意：Flet 没有 CSS 的 ``max-width``。早期版本这里给内容写死宽度，
        结果窗口比它窄时右侧被裁掉（手机上尤其明显）。现在一律跟随窗口宽度，
        靠内边距控制留白。
        """
    def _content_wrapper(self) -> ft.Control:
        """内容区：**滚动容器**，底部留出导航栏高度。

        为什么要在这里承载滚动
        ----------------------
        页面自己的根节点（``BaseView.build()``）是一个 Column。如果滚动只
        设在它身上，它的父级不是滚动视图时，触摸/滚轮的手势会被父级吃掉 ——
        表现就是"手机上滑不动"。所以滚动放在外壳这一层：

            Container(padding=四周留白)
              └─ Column(scroll=AUTO)      <- 滚动手势在这里
                   └─ 页面内容

        注意：flet 0.28.3 的 ``Container`` **没有** ``scroll`` 参数，
        必须用 ``Column``/``ListView`` 之类的可滚动控件来承载。
        """
        padding = ft.padding.only(
            left=theme.PAD_M,
            right=theme.PAD_M,
            top=theme.PAD_S,
            bottom=theme.NAV_HEIGHT + theme.PAD_M,
        )
        return ft.Container(
            content=ft.Column(
                [self._body],
                spacing=0,
                scroll=ft.ScrollMode.AUTO,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
            expand=True,
            padding=padding,
        )

    # ------------------------------------------------------------ 导航

    def _on_nav_change(self, event: ft.ControlEvent) -> None:
        self.current_index = int(event.control.selected_index)
        self._render_current()
        self.page.update()

    def goto(self, index: int) -> None:
        """切换到指定标签（供"记一笔"完成后跳转等使用）。"""
        if not 0 <= index < len(self.TABS):
            return
        self.current_index = index
        if self._nav is not None:
            self._nav.selected_index = index
        self.refresh(only_current=True)
        self.page.update()

    # ------------------------------------------------------------ 渲染

    def _render_current(self) -> None:
        if self._body is None:
            return
        view = self._view(self.current_index)
        self._body.content = view.build()

    def _view(self, index: int) -> BaseView:
        view = self._views.get(index)
        if view is None:
            view = self._create_view(index)
            self._views[index] = view
        return view

    def _create_view(self, index: int) -> BaseView:
        common = {"shell": self}
        if index == 0:
            return HomeView(**common)
        if index == 1:
            return AddTransactionView(**common)
        if index == 2:
            return TransactionListView(**common)
        return SettingsView(**common)

    def refresh(self, *, only_current: bool = False) -> None:
        """让页面重新取数并刷新界面。

        ``only_current=False`` 时会把所有已创建的页面都标记为脏，
        等切过去时再重建（避免看不见的页面做无谓查询）。
        """
        if only_current:
            dirty = [self.current_index]
        else:
            dirty = list(self._views.keys())
        for index in dirty:
            view = self._views.get(index)
            if view is not None:
                view.mark_dirty()
        current = self._views.get(self.current_index)
        if current is not None and self._body is not None:
            self._body.content = current.build()
            self.page.update()

    # ------------------------------------------------------------ 供页面调用

    def notify_data_changed(self, *, message: str | None = None) -> None:
        """数据变更入口：刷新界面 + 可选提示。"""
        if message:
            from _shared.components import message as show_message

            show_message(self.page, message)
        self.refresh(only_current=True)

    def go_add_transaction(self) -> None:
        self.goto(1)

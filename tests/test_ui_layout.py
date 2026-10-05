"""界面结构回归测试（不需要打开窗口）。

防的是几类"只有跑起来才发现"的问题：

* 页面/外壳能否在无头环境下构建成功（控件参数写错会在这里炸）；
* 内容区**不能**写死宽度——早期版本给内容固定 720px，窗口比它窄时
  右侧内容会被裁掉（手机上尤其明显），这个测试锁住该行为；
* 玻璃主题的关键属性（透明画布、模糊、渐变背景）确实生效。
"""

from __future__ import annotations

import unittest

from conftest import DatabaseTestCase

import flet as ft


class FakeOverlay(list):
    pass


class FakeResizeEvent:
    """模拟 flet 的 WindowResizeEvent（自带 width/height）。"""

    def __init__(self, *, width: int, height: int, page=None):
        self.width = width
        self.height = height
        self.page = page
        self.control = None


class FakePage:
    """只提供页面构建所需的最小接口。"""

    def __init__(self, *, width: int = 405, height: int = 822):
        self.title = ""
        self.theme = None
        self.dark_theme = None
        self.theme_mode = None
        self.bgcolor = None
        self.padding = 0
        self.spacing = 0
        self.appbar = None
        self.navigation_bar = None
        #: 真实视口尺寸（会被 resize 事件更新）
        self.width = 0
        self.height = 0
        self.on_resized = None
        self.window = type("Window", (), {"width": width, "height": height})()
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


def walk(node, seen: set[int] | None = None):
    """遍历控件树，产出每个控件。"""
    seen = seen if seen is not None else set()
    if node is None or id(node) in seen:
        return
    seen.add(id(node))
    yield node
    for attr in ("controls", "actions", "destinations", "tabs", "segments"):
        items = getattr(node, attr, None)
        if isinstance(items, (list, tuple)):
            for item in items:
                yield from walk(item, seen)
    content = getattr(node, "content", None)
    if content is not None:
        yield from walk(content, seen)


class TestShellLayout(DatabaseTestCase):

    def _mount(self, width: int = 405, height: int = 822):
        from _shared.shell import AppShell

        page = FakePage(width=width, height=height)
        shell = AppShell(page, app_title="测试", max_content_width=None)
        shell.mount()
        return page, shell

    def test_shell_mounts(self):
        page, _shell = self._mount()
        self.assertEqual(len(page.controls), 1, "背景与内容必须在同一个 Stack 里")
        self.assertIsInstance(page.controls[0], ft.Stack)
        self.assertIsNotNone(page.navigation_bar)
        self.assertGreater(page.updates, 0)

    def test_background_is_solid_theme_color(self):
        """背景必须是纯色（用户要求去掉圆形光斑），且随主题变化。"""
        from _shared import theme

        page, _shell = self._mount()
        root = page.controls[0]
        self.assertEqual(len(root.controls), 2, "Stack 应包含背景层与内容层")
        background, content = root.controls
        self.assertIsInstance(background, ft.Container)
        self.assertEqual(background.bgcolor, theme.BG_SOLID_DARK)
        # 背景上不允许再有渐变或模糊（曾经的圆形光斑）
        self.assertIsNone(getattr(background, "gradient", None))
        self.assertIsNone(getattr(background, "blur", None))
        blobs = [c for c in walk(background)
                 if getattr(c, "border_radius", None) and getattr(c, "bgcolor", None)]
        self.assertEqual(blobs, [], "背景层不应再有圆形色块")
        self.assertIsNotNone(content, "内容层不能为空")

    def test_background_follows_light_theme(self):
        from _shared import theme

        page, shell = self._mount()
        shell.toggle_theme()          # 默认深色 -> 切到浅色
        background = page.controls[0].controls[0]
        self.assertEqual(background.bgcolor, theme.BG_SOLID_LIGHT)

    def test_background_has_explicit_size(self):
        """背景必须有确定尺寸，否则 Stack 会撑高把内容顶下去。"""
        page, _shell = self._mount(width=405, height=822)
        background = page.controls[0].controls[0]
        self.assertEqual(background.height, 822)

    def test_resize_handler_is_registered_with_correct_name(self):
        """resize 回调必须挂在 ``on_resized`` 上。

        回归背景：flet 的事件是动态属性，写成 ``page.on_resize`` 不会报错、
        只会静默失效 —— 表现是缩放窗口/浏览器后背景不跟着铺满，露出白边。
        """
        page, _shell = self._mount()
        self.assertIsNotNone(page.on_resized, "resize 回调没有注册（事件名写错了？）")

    def test_background_follows_viewport_resize(self):
        """视口变大后，背景层要跟着变大（否则底部露出底色）。"""
        page, shell = self._mount(width=405, height=822)
        background = page.controls[0].controls[0]
        self.assertEqual(background.height, 822)

        # 模拟浏览器窗口被拉大：page 尺寸变化 + resize 事件
        page.width = 900
        page.height = 1400
        event = FakeResizeEvent(width=900, height=1400, page=page)
        shell._on_page_resize(event)

        background = page.controls[0].controls[0]
        self.assertEqual(background.height, 1400, "背景高度没有跟随视口变化")

    def test_size_falls_back_to_resize_event(self):
        """page 与 window 都拿不到尺寸时，用最近一次 resize 事件的值。"""
        page, shell = self._mount(width=0, height=0)
        shell._last_viewport = (720, 1280)
        self.assertEqual(shell._size(), (720, 1280))

    def test_content_follows_narrow_window(self):
        """内容区不能写死宽度，否则窄窗口下右侧会被裁掉。"""
        page, _shell = self._mount(width=405, height=822)
        _background, content = page.controls[0].controls
        fixed = [
            control for control in walk(content)
            if isinstance(control, ft.Container)
            and isinstance(getattr(control, "width", None), (int, float))
            and control.width > 405
        ]
        self.assertEqual(fixed, [],
                         f"发现超出窗口宽度的固定宽度容器：{[c.width for c in fixed]}")

    def test_content_has_bottom_padding_for_nav_bar(self):
        """底部要留出导航栏高度，否则最后一条会被悬浮条压住。"""
        from _shared import theme

        page, _shell = self._mount()
        _background, content = page.controls[0].controls
        padding = getattr(content, "padding", None)
        self.assertIsNotNone(padding)
        self.assertGreaterEqual(padding.bottom, theme.NAV_HEIGHT)

    def test_scroll_is_on_the_shell_not_the_page(self):
        """滚动手势必须由外壳的滚动容器承载。

        回归背景：早期把 scroll 设在页面自己的 Column 上，而它的父级不是
        滚动视图，手势被父级吃掉 —— 手机上表现为"页面滑不动"。
        Container 在 flet 0.28.3 里没有 scroll 参数，所以必须是
        ``Container > Column(scroll=...)`` 这个组合。
        """
        page, shell = self._mount()
        _background, content = page.controls[0].controls

        self.assertIsInstance(content, ft.Container)
        # Container 不能有 scroll（0.28.3 不支持），滚动要放在内部的 Column 上
        self.assertFalse(hasattr(content, "scroll") and getattr(content, "scroll", None),
                         "Container 不支持 scroll，别写在这里")
        inner = content.content
        self.assertIsInstance(inner, ft.Column, "外壳内容容器里应当是滚动 Column")
        self.assertEqual(inner.scroll, ft.ScrollMode.AUTO, "外壳的 Column 必须是可滚动的")

        # 页面自己的根节点不应再重复设置滚动（避免嵌套滚动互相抢手势）
        for index in range(4):
            view = shell._view(index)
            view.mark_dirty()
            tree = view.build()
            self.assertIsNone(getattr(tree, "scroll", None),
                              f"第 {index} 个页面又自己设了滚动，会和外层抢手势")

    def test_all_four_views_render(self):
        page, shell = self._mount()
        for index in range(4):
            view = shell._view(index)
            view.mark_dirty()
            self.assertIsNotNone(view.build())

    def test_theme_toggle_rebuilds_background(self):
        """切换主题要换掉背景层（背景色随明暗变化）。"""
        page, shell = self._mount()
        root = page.controls[0]
        before_bg, before_content = root.controls
        dark_before = shell.page.theme_mode

        shell.toggle_theme()

        self.assertNotEqual(shell.page.theme_mode, dark_before, "主题模式应切换")
        self.assertIs(page.controls[0], root, "根 Stack 不应被替换")
        self.assertIsNot(root.controls[0], before_bg, "背景层应被重建")
        self.assertIs(root.controls[1], before_content, "内容层不应被替换")


class TestGlassTheme(unittest.TestCase):

    def test_translucent_tokens_are_eight_digit_hex(self):
        from _shared import theme

        tokens = {
            "GLASS_SURFACE_DARK": theme.GLASS_SURFACE_DARK,
            "GLASS_SURFACE_LIGHT": theme.GLASS_SURFACE_LIGHT,
            "GLASS_LAYER_DARK": theme.GLASS_LAYER_DARK,
            "GLASS_LAYER_LIGHT": theme.GLASS_LAYER_LIGHT,
            "GLASS_BORDER_DARK": theme.GLASS_BORDER_DARK,
            "GLASS_BORDER_LIGHT": theme.GLASS_BORDER_LIGHT,
        }
        for name, value in tokens.items():
            self.assertRegex(value, r"^#[0-9A-Fa-f]{8}$",
                             f"{name} 必须是带透明度的 8 位十六进制颜色")

    def test_background_colors_are_solid(self):
        """背景是 6 位纯色，不带透明度。"""
        from _shared import theme

        for value in (theme.BG_SOLID_DARK, theme.BG_SOLID_LIGHT):
            self.assertRegex(value, r"^#[0-9A-Fa-f]{6}$")

    def test_light_theme_text_is_dark(self):
        """浅色主题下正文色必须够深，否则看不清（用户实际反馈过）。"""
        from _shared import theme

        def luminance(hex_color: str) -> float:
            value = hex_color.lstrip("#")
            r, g, b = (int(value[i:i + 2], 16) for i in (0, 2, 4))
            return (0.299 * r + 0.587 * g + 0.114 * b) / 255

        light_text = theme.scheme(False).on_surface
        light_bg = theme.BG_SOLID_LIGHT
        self.assertLess(luminance(light_text), 0.35,
                        f"浅色主题正文色太浅：{light_text}")
        self.assertGreater(luminance(light_bg) - luminance(light_text), 0.5,
                           "浅色主题的文字与背景对比度不足")
        # 深色主题反过来
        dark_text = theme.scheme(True).on_surface
        self.assertGreater(luminance(dark_text), 0.7,
                           f"深色主题正文色太深：{dark_text}")

    def test_palette_text_colors_follow_mode(self):
        from _shared import theme

        dark_palette = theme.Palette(None)
        light_page = FakePage()
        light_page.theme_mode = ft.ThemeMode.LIGHT
        light_palette = theme.Palette(light_page)

        self.assertEqual(dark_palette.on_surface, theme.TEXT_DARK)
        self.assertEqual(light_palette.on_surface, theme.TEXT_LIGHT)
        self.assertEqual(dark_palette.muted, theme.TEXT_MUTED_DARK)
        self.assertEqual(light_palette.muted, theme.TEXT_MUTED_LIGHT)

    def test_canvas_is_transparent(self):
        """画布不透明的话，背景层根本看不见。"""
        from _shared import theme

        for dark in (False, True):
            built = theme.build_theme(dark)
            self.assertEqual(built.scaffold_bgcolor, "#00000000")
            self.assertEqual(built.canvas_color, "#00000000")

    def test_panel_has_translucency_and_blur(self):
        from _shared import theme

        panel = theme.Palette(None).panel(ft.Text("x"))
        self.assertIsNotNone(panel.blur, "玻璃面板必须有模糊")
        self.assertIsNotNone(panel.shadow, "玻璃面板必须有投影")
        self.assertRegex(panel.bgcolor, r"^#[0-9A-Fa-f]{8}$")

    def test_palette_defaults_to_dark(self):
        from _shared import theme

        self.assertTrue(theme.Palette(None).dark)
        light_page = FakePage()
        light_page.theme_mode = ft.ThemeMode.LIGHT
        self.assertFalse(theme.Palette(light_page).dark)

    def test_fields_and_buttons_are_rounded(self):
        """输入框与按钮必须是圆角（用户反馈直角难看）。"""
        from _shared import theme

        for dark in (False, True):
            style = theme.field_style(dark)
            self.assertGreaterEqual(style["border_radius"], 10,
                                    "输入框圆角太小")
            self.assertIn(style["border"], (ft.InputBorder.OUTLINE, ft.InputBorder.UNDERLINE))
            # 文字色要跟主题走
            expected = theme.TEXT_DARK if dark else theme.TEXT_LIGHT
            self.assertEqual(style["color"], expected)

            button = theme.Palette(None).button()
            # ButtonStyle.shape 在 0.28.x 里是按状态存的字典
            shapes = button.shape if isinstance(button.shape, dict) else {"d": button.shape}
            self.assertTrue(
                all(isinstance(s, ft.RoundedRectangleBorder) for s in shapes.values()),
                f"按钮必须是圆角：{button.shape}",
            )

    def test_transaction_tile_keeps_amount_visible(self):
        """流水行的金额不能被截断逻辑吃掉（分类名可省略，金额必须完整）。"""
        from datetime import date
        from decimal import Decimal

        from _shared import theme
        from _shared.components import transaction_tile
        from models import KIND_EXPENSE, Transaction

        tx = Transaction(
            id=1, kind=KIND_EXPENSE, amount=Decimal("12345.67"), category_id=1,
            happened_on=date(2025, 10, 26), note="测试",
            category_name="人情往来", category_icon="card_giftcard",
            category_color="#F4511E",
        )
        tile = transaction_tile(tx, theme.Palette(None))
        texts = [c.value for c in walk(tile) if isinstance(c, ft.Text)]
        self.assertIn("-¥12,345.67", texts)


if __name__ == "__main__":
    unittest.main(verbosity=2)

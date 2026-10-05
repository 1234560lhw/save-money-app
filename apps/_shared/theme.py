"""视觉主题：颜色、间距、圆角、字体尺寸，以及苹果风格的毛玻璃质感。

设计要点（参考 iOS / macOS 的"半透明材质"）
--------------------------------------------
* **背景是渐变且带光晕的**：纯色背景上做半透明是看不出效果的，
  所以页面底层铺一层柔和渐变 + 几个大范围模糊光斑（`ambient_background`）。
* **卡片是"半透明玻璃"**：低不透明度白色做底 + 1px 高光描边
  （`GLASS_BORDER_*`）+ 柔和投影，叠在渐变背景上就有了玻璃层次。
* **导航栏 / 顶栏是"悬浮玻璃"**：半透明 + `Blur`，内容从下面滚过时透过它。
* 收入绿、支出红是记账软件的通用习惯，**不随风格改动**。

所有色值都集中在这里，页面里不要写死。
"""

from __future__ import annotations

import flet as ft

# ---------------------------------------------------------------- 主色

PRIMARY = "#00897B"          # 存钱罐绿松石色，隐喻"储蓄"
PRIMARY_DARK = "#00695C"
PRIMARY_LIGHT = "#4DB6AC"
ACCENT = "#FFB300"           # 目标进度/提醒用琥珀色

#: 收入 / 支出语义色（浅色主题）
INCOME = "#2E7D32"
EXPENSE = "#D32F2F"
WARNING = "#EF6C00"          # 超支、逾期
MUTED = "#78909C"

#: 深色主题下的语义色（亮度提高，保证对比度）
INCOME_DARK = "#81C784"
EXPENSE_DARK = "#EF5350"
WARNING_DARK = "#FFB74D"
MUTED_DARK = "#90A4AE"

# ---------------------------------------------------------------- 毛玻璃材质
#
# 颜色用 8 位十六进制：前两位是透明度(00~FF)，后六位是 RGB。
# 例如 "#1FFFFFFF" = 白色、透明度 0x1F ≈ 12%。

#: 卡片/面板底色
GLASS_SURFACE_DARK = "#1FFFFFFF"      # 深色主题：白色 12%
GLASS_SURFACE_LIGHT = "#B3FFFFFF"     # 浅色主题：白色 70%
#: 更"厚"的一层（顶栏、导航栏、弹窗）
GLASS_LAYER_DARK = "#2EFFFFFF"        # 白色 18%
GLASS_LAYER_LIGHT = "#D9FFFFFF"       # 白色 85%
#: 卡片内的小色块（指标块、图标底）
GLASS_CHIP_DARK = "#14FFFFFF"         # 白色 8%
GLASS_CHIP_LIGHT = "#66FFFFFF"        # 白色 40%
#: 高光描边：上缘亮、下缘暗，模拟玻璃厚度
GLASS_BORDER_DARK = "#33FFFFFF"
GLASS_BORDER_LIGHT = "#99FFFFFF"
GLASS_EDGE_DARK = "#14FFFFFF"
GLASS_EDGE_LIGHT = "#40FFFFFF"

#: 投影（玻璃要浮起来才像玻璃）
SHADOW_DARK = "#00000059"
SHADOW_LIGHT = "#0F172A1F"

#: 页面背景色（纯色，不用渐变/光斑：用户明确要求背景要么黑要么白）
BG_SOLID_DARK = "#0B1220"
BG_SOLID_LIGHT = "#F4F6FB"

#: 浅色主题下的正文颜色（必须足够深，否则浅背景上看不清）
TEXT_LIGHT = "#16212E"
TEXT_DARK = "#F1F5F9"
#: 次要文字
TEXT_MUTED_LIGHT = "#5A6B7D"
TEXT_MUTED_DARK = "#9FB0C0"
#: 输入框边框
FIELD_BORDER_LIGHT = "#C6D0DC"
FIELD_BORDER_DARK = "#3A4756"

#: 输入框/按钮圆角（用户反馈直角难看，统一改成圆角）
FIELD_RADIUS = 14
BUTTON_RADIUS = 14
CHIP_RADIUS = 20

# ---------------------------------------------------------------- 尺寸

PAD_XS = 4
PAD_S = 8
PAD_M = 16
PAD_L = 24

RADIUS_S = 10
RADIUS_M = 16
RADIUS_L = 22
RADIUS_XL = 28

FONT_HERO = 38               # 总存款大字
FONT_TITLE = 20
FONT_BODY = 15
FONT_SMALL = 13
FONT_TINY = 11

#: 底部导航高度（手机端友好，手指好点）
NAV_HEIGHT = 68

#: 饼图配色（按分类取色，不够用时循环）
CHART_PALETTE = [
    "#E53935", "#FB8C00", "#FDD835", "#43A047", "#00897B",
    "#1E88E5", "#3949AB", "#8E24AA", "#D81B60", "#6D4C41",
    "#00ACC1", "#7CB342",
]
#: 曲线图线条颜色（深色/浅色主题各一档）
CHART_LINE_DARK = "#4DB6AC"
CHART_LINE_LIGHT = "#00897B"

#: 玻璃模糊强度（数值越大越"厚"，也越吃性能）
BLUR_STRONG = 26
BLUR_SOFT = 14
BLUR_BAR = 18


def scheme(dark: bool) -> ft.ColorScheme:
    """返回与主题配套的配色方案。

    浅色主题下 ``on_surface`` 必须是深色，否则文字在浅背景上看不清
    （这是用户实际碰到的问题，改动前请先想清楚对比度）。
    """
    if dark:
        return ft.ColorScheme(
            primary=PRIMARY_LIGHT,
            on_primary="#00251A",
            secondary=ACCENT,
            surface="#161B24",
            on_surface=TEXT_DARK,
            surface_variant="#222834",
            on_surface_variant=TEXT_MUTED_DARK,
            outline="#4A5768",
            error=EXPENSE_DARK,
        )
    return ft.ColorScheme(
        primary=PRIMARY,
        on_primary="#FFFFFF",
        secondary="#E08A00",
        surface="#FFFFFF",
        on_surface=TEXT_LIGHT,
        surface_variant="#EDF1F7",
        on_surface_variant=TEXT_MUTED_LIGHT,
        outline=FIELD_BORDER_LIGHT,
        error=EXPENSE,
    )


def build_theme(dark: bool = False) -> ft.Theme:
    """统一主题：玻璃质感卡片 + 圆角输入框 + 舒适的列表密度。"""
    text_color = TEXT_DARK if dark else TEXT_LIGHT
    muted_color = TEXT_MUTED_DARK if dark else TEXT_MUTED_LIGHT
    field_border = FIELD_BORDER_DARK if dark else FIELD_BORDER_LIGHT
    field_bg = "#1AFFFFFF" if dark else "#F7F9FC"

    return ft.Theme(
        color_scheme=scheme(dark),
        font_family="Microsoft YaHei",
        use_material3=True,
        visual_density=ft.VisualDensity.COMFORTABLE,
        # 画布透明，真正的背景由外壳的纯色层提供
        scaffold_bgcolor="#00000000",
        canvas_color="#00000000",
        card_color=GLASS_SURFACE_DARK if dark else GLASS_SURFACE_LIGHT,
        card_theme=ft.CardTheme(
            elevation=0,
            margin=ft.margin.all(0),
            color=GLASS_SURFACE_DARK if dark else GLASS_SURFACE_LIGHT,
            shape=ft.RoundedRectangleBorder(radius=RADIUS_L),
        ),
        divider_theme=ft.DividerTheme(
            color=GLASS_EDGE_DARK if dark else GLASS_EDGE_LIGHT,
            thickness=1,
            space=1,
        ),
        navigation_bar_theme=ft.NavigationBarTheme(
            height=NAV_HEIGHT,
            bgcolor="#00000000",          # 透明，由外壳自己铺玻璃层
            elevation=0,
            indicator_color=ft.Colors.with_opacity(0.22, PRIMARY_LIGHT if dark else PRIMARY),
            label_behavior=ft.NavigationBarLabelBehavior.ALWAYS_SHOW,
            label_text_style=ft.TextStyle(size=FONT_TINY, color=text_color),
        ),
        appbar_theme=ft.AppBarTheme(
            bgcolor="#00000000",
            elevation=0,
            shadow_color="#00000000",
        ),
        dialog_theme=ft.DialogTheme(
            bgcolor="#1F2733" if dark else "#FFFFFF",
            elevation=0,
            shape=ft.RoundedRectangleBorder(radius=RADIUS_XL),
        ),
        # ---- 圆角按钮（直角被用户点名难看）----
        # 注意：FilledButtonTheme 这类主题直接吃 shape / bgcolor 参数，
        # 不接受 style=ButtonStyle(...)，只有 SegmentedButtonTheme 是 style=。
        filled_button_theme=ft.FilledButtonTheme(
            shape=ft.RoundedRectangleBorder(radius=BUTTON_RADIUS),
            bgcolor=PRIMARY_LIGHT if dark else PRIMARY,
            foreground_color="#FFFFFF",
            elevation=0,
        ),
        outlined_button_theme=ft.OutlinedButtonTheme(
            shape=ft.RoundedRectangleBorder(radius=BUTTON_RADIUS),
            foreground_color=text_color,
            bgcolor="#00000000",
        ),
        text_button_theme=ft.TextButtonTheme(
            shape=ft.RoundedRectangleBorder(radius=BUTTON_RADIUS),
            foreground_color=PRIMARY_LIGHT if dark else PRIMARY,
        ),
        icon_button_theme=ft.IconButtonTheme(
            shape=ft.RoundedRectangleBorder(radius=BUTTON_RADIUS),
        ),
        segmented_button_theme=ft.SegmentedButtonTheme(
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=BUTTON_RADIUS)),
        ),
        # ---- 圆角输入类控件：颜色统一在 field_style() 里定，避免各处写死 ----
        text_theme=ft.TextTheme(
            body_large=ft.TextStyle(size=FONT_BODY + 1, color=text_color),
            body_medium=ft.TextStyle(size=FONT_BODY, color=text_color),
            body_small=ft.TextStyle(size=FONT_SMALL, color=muted_color),
            title_large=ft.TextStyle(size=FONT_TITLE, color=text_color),
            title_medium=ft.TextStyle(size=FONT_BODY + 2, color=text_color),
            label_large=ft.TextStyle(size=FONT_BODY, color=muted_color),
        ),
        hint_color=muted_color,
        indicator_color=PRIMARY_LIGHT if dark else PRIMARY,
        splash_color=ft.Colors.with_opacity(0.10, PRIMARY_LIGHT if dark else PRIMARY),
    )


def field_style(dark: bool, **overrides) -> dict:
    """输入框 / 下拉框的统一外观参数（圆角、边框、文字色）。

    直接展开给 TextField / Dropdown 用::

        ft.TextField(label="金额", **theme.field_style(dark))

    额外参数（如 ``text_size=26``）会覆盖默认值。
    """
    style = {
        "border_radius": FIELD_RADIUS,
        "border": ft.InputBorder.OUTLINE,
        "border_color": FIELD_BORDER_DARK if dark else FIELD_BORDER_LIGHT,
        "focused_border_color": PRIMARY_LIGHT if dark else PRIMARY,
        "color": TEXT_DARK if dark else TEXT_LIGHT,
        "bgcolor": "#1AFFFFFF" if dark else "#F7F9FC",
        "filled": True,
        "text_size": FONT_BODY,
        "label_style": ft.TextStyle(
            size=FONT_SMALL, color=TEXT_MUTED_DARK if dark else TEXT_MUTED_LIGHT
        ),
        "hint_style": ft.TextStyle(
            size=FONT_SMALL, color=TEXT_MUTED_DARK if dark else TEXT_MUTED_LIGHT
        ),
    }
    style.update(overrides)
    return style


# ================================================================ 玻璃材质

def glass_panel(*, dark: bool, strong: bool = False, radius: int = RADIUS_L,
                blur: int | None = None, padding: int | None = None,
                content: ft.Control | None = None) -> ft.Container:
    """一块"毛玻璃"面板。

    ``strong=True`` 用于顶栏/导航栏这种要压在内容之上的层（更厚、更模糊）。
    """
    surface = (GLASS_LAYER_DARK if strong else GLASS_SURFACE_DARK) if dark else \
              (GLASS_LAYER_LIGHT if strong else GLASS_SURFACE_LIGHT)
    border = GLASS_BORDER_DARK if dark else GLASS_BORDER_LIGHT
    shadow = SHADOW_DARK if dark else SHADOW_LIGHT
    sigma = blur if blur is not None else (BLUR_STRONG if strong else BLUR_SOFT)

    container = ft.Container(
        content=content,
        bgcolor=surface,
        border_radius=radius,
        border=ft.border.all(1, border),
        shadow=ft.BoxShadow(
            blur_radius=28 if strong else 18,
            spread_radius=-4,
            color=shadow,
            offset=ft.Offset(0, 8 if strong else 4),
        ),
        padding=padding,
    )
    if sigma:
        container.blur = ft.Blur(sigma, sigma, ft.BlurTileMode.CLAMP)
    return container


def background_color(dark: bool) -> str:
    """整页背景色：深色主题是深色、浅色主题是浅色，纯色不加装饰。

    早期版本这里是渐变 + 圆形模糊光斑，用户反馈"不要背景那种圆形的元素"，
    所以改成纯色。玻璃卡片本身仍保留模糊与描边，层次靠卡片体现。
    """
    return BG_SOLID_DARK if dark else BG_SOLID_LIGHT


def background_layer(dark: bool, *, width: int, height: int) -> ft.Control:
    """铺满窗口的纯色背景层（玻璃卡片就叠在它上面）。"""
    return ft.Container(
        width=width if width else None,
        height=height,
        bgcolor=background_color(dark),
    )


def ambient_background(dark: bool, *, height: int = 1400) -> ft.Container:
    """兼容旧调用：返回纯色背景层。"""
    return ft.Container(height=height, bgcolor=background_color(dark))


def glass_shadow(dark: bool, *, strong: bool = False) -> ft.BoxShadow:
    return ft.BoxShadow(
        blur_radius=28 if strong else 18,
        spread_radius=-4,
        color=SHADOW_DARK if dark else SHADOW_LIGHT,
        offset=ft.Offset(0, 8 if strong else 4),
    )


class Palette:
    """按当前明暗模式取语义色，页面里用 ``palette.income`` 这种写法。"""

    def __init__(self, page: ft.Page | None = None):
        mode = getattr(page, "theme_mode", None) if page is not None else None
        # 没显式设置时按深色处理：毛玻璃质感在深色下最出效果，
        # 外壳挂载时会用数据库里保存的设置覆盖它。
        self.dark = mode != ft.ThemeMode.LIGHT

    @property
    def income(self) -> str:
        return INCOME_DARK if self.dark else INCOME

    @property
    def expense(self) -> str:
        return EXPENSE_DARK if self.dark else EXPENSE

    @property
    def warning(self) -> str:
        return WARNING_DARK if self.dark else WARNING

    @property
    def muted(self) -> str:
        """次要文字色（必须保证在当前背景上看得清）。"""
        return TEXT_MUTED_DARK if self.dark else TEXT_MUTED_LIGHT

    @property
    def primary(self) -> str:
        return PRIMARY_LIGHT if self.dark else PRIMARY

    @property
    def surface_variant(self) -> str:
        return GLASS_CHIP_DARK if self.dark else GLASS_CHIP_LIGHT

    # ---- 玻璃质感相关 ----

    @property
    def glass(self) -> str:
        """卡片底色。"""
        return GLASS_SURFACE_DARK if self.dark else GLASS_SURFACE_LIGHT

    @property
    def glass_layer(self) -> str:
        """更厚的一层（顶栏、导航栏、弹窗）。"""
        return GLASS_LAYER_DARK if self.dark else GLASS_LAYER_LIGHT

    @property
    def glass_chip(self) -> str:
        """卡片内的小色块底色。"""
        return GLASS_CHIP_DARK if self.dark else GLASS_CHIP_LIGHT

    @property
    def glass_border(self) -> str:
        """玻璃高光描边。"""
        return GLASS_BORDER_DARK if self.dark else GLASS_BORDER_LIGHT

    @property
    def glass_edge(self) -> str:
        """卡片内分隔线。"""
        return GLASS_EDGE_DARK if self.dark else GLASS_EDGE_LIGHT

    @property
    def shadow(self) -> ft.BoxShadow:
        return glass_shadow(self.dark)

    @property
    def on_surface(self) -> str:
        """正文色：浅色主题必须够深，否则浅背景上看不清。"""
        return TEXT_DARK if self.dark else TEXT_LIGHT

    @property
    def field_border(self) -> str:
        return FIELD_BORDER_DARK if self.dark else FIELD_BORDER_LIGHT

    def field(self, **overrides) -> dict:
        """输入框/下拉框参数，直接展开使用。

        用法::

            ft.TextField(label="金额", **self.palette.field())
        """
        style = field_style(self.dark)
        style.update(overrides)
        return style

    def button(self, *, danger: bool = False, filled: bool = True) -> ft.ButtonStyle:
        """圆角按钮样式。"""
        return ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=BUTTON_RADIUS),
            color="#FFFFFF" if filled else self.on_surface,
            bgcolor=("#C62828" if danger else self.primary) if filled else None,
            side=None if filled else ft.BorderSide(1, self.field_border),
        )

    def panel(self, content: ft.Control, *, strong: bool = False, radius: int = RADIUS_L,
              blur: int | None = None, padding: int | None = None) -> ft.Container:
        """便捷方法：``palette.panel(内容)`` 得到一块玻璃面板。"""
        return glass_panel(dark=self.dark, strong=strong, radius=radius, blur=blur,
                           padding=padding, content=content)

    def by_kind(self, kind: str) -> str:
        return self.income if kind == "income" else self.expense

    # ---- 图表相关 ----

    @property
    def chart_line(self) -> str:
        """曲线图主线颜色。"""
        return CHART_LINE_DARK if self.dark else CHART_LINE_LIGHT

    @property
    def chart_grid(self) -> str:
        return "#26FFFFFF" if self.dark else "#1A0F172A"

    def chart_color(self, index: int, *, fallback: str | None = None) -> str:
        """按序号从饼图配色里取色。"""
        if fallback:
            return fallback
        return CHART_PALETTE[index % len(CHART_PALETTE)]

    @property
    def axis_label_style(self) -> ft.TextStyle:
        return ft.TextStyle(size=FONT_TINY,
                            color=TEXT_MUTED_DARK if self.dark else TEXT_MUTED_LIGHT)

    @staticmethod
    def kind_icon(kind: str) -> str:
        return ft.Icons.ARROW_DOWNWARD if kind == "income" else ft.Icons.ARROW_UPWARD

"""可复用的小组件。

约定：这里只做"展示"，不做任何金额计算，数据一律由 services 层算好后传进来。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Callable, Sequence

import flet as ft

from _shared import theme
from utils.money import format_money, format_percent, to_decimal


# ---------------------------------------------------------------- 文本

def money_text(value: Decimal | int | str | None, *, size: int = theme.FONT_BODY,
               color: str | None = None, weight: ft.FontWeight | None = None,
               signed: bool = False, symbol: str = "¥",
               text_align: ft.TextAlign | None = None) -> ft.Text:
    """金额文本。所有金额都必须走这里格式化，保证千分位/两位小数一致。"""
    return ft.Text(
        format_money(value, symbol=symbol, signed=signed),
        size=size,
        color=color,
        weight=weight,
        text_align=text_align,
    )


def label_text(text: str, *, size: int = theme.FONT_SMALL,
               color: str | None = None, weight: ft.FontWeight | None = None,
               expand: bool | int = False) -> ft.Text:
    return ft.Text(text, size=size, color=color, weight=weight, expand=expand)


def section_title(title: str, *, trailing: ft.Control | None = None) -> ft.Row:
    """分区标题，右侧可放"查看全部"之类的小按钮。"""
    return ft.Row(
        [
            ft.Text(title, size=theme.FONT_TITLE, weight=ft.FontWeight.W_600),
            ft.Container(expand=True),
            trailing or ft.Container(),
        ],
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def page_header(title: str, *, subtitle: str | None = None,
                trailing: ft.Control | None = None) -> ft.Column:
    """iOS 风格页面大标题（取代了原来的顶部工具栏）。"""
    top = ft.Row(
        [
            ft.Column(
                [
                    ft.Text(title, size=30, weight=ft.FontWeight.BOLD),
                    *([ft.Text(subtitle, size=theme.FONT_SMALL, color=theme.MUTED)]
                      if subtitle else []),
                ],
                spacing=2,
                expand=True,
            ),
            trailing or ft.Container(),
        ],
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
    return ft.Column([top, ft.Container(height=theme.PAD_S)], spacing=0)


# ---------------------------------------------------------------- 容器

def panel(content: ft.Control, *, padding: int = theme.PAD_M,
          bgcolor: str | None = None, border: bool = False,
          dark: bool = False, radius: int = theme.RADIUS_L,
          blur: int | None = None) -> ft.Container:
    """统一玻璃面板样式。"""
    if bgcolor is not None or border:
        # 需要自定义色时退化成普通容器
        return ft.Container(
            content=content,
            padding=padding,
            bgcolor=bgcolor,
            border_radius=radius,
            border=ft.border.all(1, theme.GLASS_BORDER_DARK if dark else theme.GLASS_BORDER_LIGHT)
            if border else None,
        )
    return theme.glass_panel(dark=dark, radius=radius, blur=blur,
                             padding=padding, content=content)


def card(content: ft.Control, *, padding: int = theme.PAD_M,
         dark: bool = False, radius: int = theme.RADIUS_L,
         blur: int | None = None) -> ft.Container:
    """玻璃卡片（最常用的容器）。

    ``dark`` 决定玻璃层的明暗，通常传 ``palette.dark``。
    """
    return theme.glass_panel(dark=dark, radius=radius, blur=blur,
                             padding=padding, content=content)


def empty_state(message: str, *, hint: str | None = None,
                icon: str = ft.Icons.INBOX_OUTLINED,
                action: ft.Control | None = None,
                dark: bool = False) -> ft.Container:
    """空列表提示，避免页面出现大片空白。"""
    children: list[ft.Control] = [
        ft.Icon(icon, size=42, color=ft.Colors.with_opacity(0.5, theme.PRIMARY_LIGHT)),
        ft.Text(message, size=theme.FONT_BODY,
                color=theme.MUTED_DARK if dark else theme.MUTED,
                text_align=ft.TextAlign.CENTER, weight=ft.FontWeight.W_500),
    ]
    if hint:
        children.append(ft.Text(hint, size=theme.FONT_SMALL,
                                color=ft.Colors.with_opacity(0.65, theme.MUTED_DARK if dark
                                                             else theme.MUTED),
                                text_align=ft.TextAlign.CENTER))
    if action is not None:
        children.append(ft.Container(height=theme.PAD_XS))
        children.append(action)
    return theme.glass_panel(
        dark=dark, radius=theme.RADIUS_L, blur=theme.BLUR_SOFT,
        content=ft.Column(children, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                          spacing=theme.PAD_S),
    )


def divider(dark: bool = False) -> ft.Divider:
    return ft.Divider(height=1, thickness=1,
                      color=theme.GLASS_EDGE_DARK if dark else theme.GLASS_EDGE_LIGHT)


# ---------------------------------------------------------------- 数据展示

def stat_tile(title: str, value_text: str, *, color: str | None = None,
              subtitle: str | None = None, icon: str | None = None,
              compact: bool = False,
              col: dict[str, int] | int | None = None) -> ft.Container:
    """指标块（本月收入/支出/结余/储蓄率）。

    ``compact=True`` 会缩小字号与图标，用于手机上三列并排的窄屏幕，
    避免 "¥65,000.00" 这种长金额被横向截断。
    """
    value_size = theme.FONT_BODY + 1 if compact else theme.FONT_TITLE
    head: list[ft.Control] = []
    if icon:
        head.append(ft.Icon(icon, size=12 if compact else 16, color=color))
    head.append(ft.Text(title, size=theme.FONT_TINY if compact else theme.FONT_SMALL,
                        color=ft.Colors.with_opacity(0.75, color or theme.MUTED),
                        max_lines=1, overflow=ft.TextOverflow.ELLIPSIS))
    rows: list[ft.Control] = [
        ft.Row(head, spacing=2, alignment=ft.MainAxisAlignment.CENTER,
               vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ft.Text(value_text, size=value_size, weight=ft.FontWeight.W_600, color=color,
                max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
                text_align=ft.TextAlign.CENTER),
    ]
    if subtitle:
        rows.append(ft.Text(subtitle, size=theme.FONT_TINY,
                            color=ft.Colors.with_opacity(0.6, color or theme.MUTED),
                            max_lines=2, text_align=ft.TextAlign.CENTER))
    container = ft.Container(
        content=ft.Column(rows, spacing=1, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                          alignment=ft.MainAxisAlignment.CENTER),
        padding=ft.padding.symmetric(vertical=theme.PAD_XS, horizontal=2),
        col=col,
    )
    if col is None:
        container.expand = True
    return container


def stat_grid(tiles: Sequence[ft.Control]) -> ft.Control:
    """把指标块排成响应式网格：手机窄屏两列换行，宽屏一行放下。"""
    return ft.ResponsiveRow(
        list(tiles),
        spacing=theme.PAD_XS,
        run_spacing=theme.PAD_XS,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def goal_card(goal, palette: theme.Palette, *,
              on_tap: Callable[[int], None] | None = None) -> ft.Control:
    """存钱目标卡片：进度条 + 已存/目标 + 差额 + 截止日期 + 每月建议。"""
    if goal.is_done:
        bar_color = palette.income
        status_text, status_color = "已达标 🎉", palette.income
    elif goal.is_overdue:
        bar_color = palette.warning
        status_text, status_color = "已逾期", palette.warning
    else:
        bar_color = palette.primary
        status_text, status_color = "进行中", palette.muted

    deadline_text = goal.deadline.strftime("%Y-%m-%d") if goal.deadline else "未设截止日期"
    if goal.deadline and not goal.is_done and goal.days_left is not None:
        if goal.days_left >= 0:
            deadline_text += f"（剩 {goal.days_left} 天）"
        else:
            deadline_text += f"（逾期 {abs(goal.days_left)} 天）"

    if goal.monthly_suggestion > 0:
        suggestion = f"每月建议存入 {format_money(goal.monthly_suggestion)}"
    elif goal.is_done:
        suggestion = "目标已完成"
    else:
        suggestion = "未设截止日期，无法计算每月建议"

    body = ft.Column(
        [
            ft.Row(
                [
                    ft.Text(goal.name, size=theme.FONT_BODY, weight=ft.FontWeight.W_600,
                            expand=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Container(
                        content=ft.Text(status_text, size=theme.FONT_TINY, color=status_color),
                        padding=ft.padding.symmetric(horizontal=theme.PAD_S, vertical=2),
                        border_radius=theme.RADIUS_S,
                        bgcolor=ft.Colors.with_opacity(0.12, status_color),
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.Row(
                [
                    money_text(goal.saved_amount, size=theme.FONT_TITLE,
                               weight=ft.FontWeight.W_600, color=bar_color),
                    ft.Text(" / ", size=theme.FONT_BODY, color=palette.muted),
                    money_text(goal.target_amount, size=theme.FONT_SMALL, color=palette.muted),
                    ft.Container(expand=True),
                    ft.Text(format_percent(goal.progress), size=theme.FONT_SMALL,
                            color=palette.muted),
                ],
                vertical_alignment=ft.CrossAxisAlignment.END,
            ),
            ft.ProgressBar(
                value=float(goal.progress),
                color=bar_color,
                bgcolor=ft.Colors.with_opacity(0.15, bar_color),
                bar_height=8,
                border_radius=theme.RADIUS_S,
            ),
            ft.Row(
                [
                    label_text(f"还差 {format_money(goal.remaining)}", color=palette.muted),
                    ft.Container(expand=True),
                    label_text(deadline_text, color=palette.muted),
                ],
            ),
            label_text(suggestion, size=theme.FONT_TINY, color=palette.muted),
        ],
        spacing=theme.PAD_S,
    )

    container = theme.glass_panel(
        dark=palette.dark, radius=theme.RADIUS_L, blur=theme.BLUR_SOFT,
        padding=theme.PAD_M, content=body,
    )
    # 用进度色描一圈边，让卡片和目标状态呼应
    container.border = ft.border.all(1, ft.Colors.with_opacity(0.28, bar_color))
    if on_tap is not None:
        container.ink = True
        container.on_click = lambda _e: on_tap(goal.goal_id)
    return container


def transaction_tile(tx, palette: theme.Palette, *,
                     on_tap: Callable[[int], None] | None = None,
                     show_date: bool = True) -> ft.Control:
    """流水列表的一行：收入绿色、支出红色。

    金额独占右侧一列，分类与备注在左列换行，窄屏下也不会互相挤压。
    """
    color = palette.by_kind(tx.kind)
    icon_color = tx.category_color or color
    leading = ft.Container(
        content=ft.Icon(tx.category_icon or ft.Icons.CATEGORY, size=19, color=icon_color),
        width=34,
        height=34,
        border_radius=theme.RADIUS_S,
        bgcolor=ft.Colors.with_opacity(0.16, icon_color),
        border=ft.border.all(1, ft.Colors.with_opacity(0.22, icon_color)),
        alignment=ft.alignment.center,
    )

    subtitle_parts: list[str] = []
    if show_date:
        subtitle_parts.append(tx.happened_on.strftime("%m-%d"))
    if tx.note:
        subtitle_parts.append(tx.note)

    tile = ft.Container(
        content=ft.Row(
            [
                leading,
                ft.Column(
                    [
                        ft.Text(tx.category_label, size=theme.FONT_BODY,
                                weight=ft.FontWeight.W_500,
                                max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                        ft.Text(" · ".join(subtitle_parts) or " ",
                                size=theme.FONT_TINY, color=palette.muted,
                                max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    ],
                    spacing=1,
                    expand=True,
                ),
                ft.Text(
                    ("+" if tx.is_income else "-") + format_money(tx.amount),
                    size=theme.FONT_BODY,
                    weight=ft.FontWeight.W_600,
                    color=color,
                    max_lines=1,
                    text_align=ft.TextAlign.RIGHT,
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=theme.PAD_S,
        ),
        padding=ft.padding.symmetric(vertical=theme.PAD_S + 2, horizontal=theme.PAD_S),
        border_radius=theme.RADIUS_M,
    )
    if on_tap is not None:
        tile.ink = True
        tile.on_click = lambda _e: on_tap(tx.id)
    return tile


def info_row(label: str, value: str, *, value_color: str | None = None) -> ft.Row:
    """设置页的"标题 : 值"行。"""
    return ft.Row(
        [
            ft.Text(label, size=theme.FONT_BODY, expand=True),
            ft.Text(value, size=theme.FONT_BODY, color=value_color,
                    max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
        ],
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def chip(text: str, *, selected: bool = False, color: str | None = None,
         on_click: Callable | None = None, dark: bool = False) -> ft.Container:
    """轻量标签按钮，用于月份/分类筛选（玻璃胶囊）。"""
    tint = color or theme.PRIMARY
    if selected:
        bgcolor: str | None = tint
        border_color = ft.Colors.with_opacity(0.45, "#FFFFFF")
    else:
        bgcolor = theme.GLASS_CHIP_DARK if dark else theme.GLASS_CHIP_LIGHT
        border_color = theme.GLASS_BORDER_DARK if dark else theme.GLASS_BORDER_LIGHT
    return ft.Container(
        content=ft.Text(text, size=theme.FONT_SMALL,
                        color="#FFFFFF" if selected else tint,
                        weight=ft.FontWeight.W_500),
        padding=ft.padding.symmetric(horizontal=theme.PAD_M, vertical=7),
        border_radius=20,
        bgcolor=bgcolor,
        border=ft.border.all(1, border_color),
        on_click=on_click,
        ink=True,
    )


def message(page: ft.Page, text: str, *, error: bool = False) -> None:
    """统一的底部提示。"""
    page.open(ft.SnackBar(
        content=ft.Text(text, color="#FFFFFF"),
        bgcolor="#C62828" if error else "#37474F",
        duration=2600,
    ))


def confirm_dialog(page: ft.Page, title: str, message_text: str, *,
                   on_confirm: Callable[[], None],
                   confirm_text: str = "删除",
                   danger: bool = True) -> None:
    """二次确认弹窗，删除类操作统一走这里。"""

    def close(_e=None):
        page.close(dialog)

    def confirm(_e=None):
        page.close(dialog)
        on_confirm()

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(title),
        content=ft.Text(message_text, size=theme.FONT_BODY),
        actions=[
            ft.TextButton("取消", on_click=close),
            ft.FilledButton(
                confirm_text,
                on_click=confirm,
                style=ft.ButtonStyle(bgcolor="#C62828" if danger else None),
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.open(dialog)

# ---------------------------------------------------------------- 图表

def line_chart(series: Sequence[tuple[object, object]], *, palette: theme.Palette,
               height: int = 180, tooltip_prefix: str = "",
               x_label_step: int = 5) -> ft.Control:
    """曲线图：展示数值随时间的变化（如"每天结束时的存款"）。

    ``series`` 是 ``[(x 轴标签, 金额), ...]``。为了避免图表太乱，
    x 轴只每隔 ``x_label_step`` 个点标一次文字。
    """
    points: list[ft.LineChartDataPoint] = []
    labels: list[ft.ChartAxisLabel] = []
    values: list[float] = []
    for index, (label, value) in enumerate(series):
        amount = float(to_decimal(value))
        values.append(amount)
        points.append(ft.LineChartDataPoint(x=index, y=amount))
        if index % x_label_step == 0 or index == len(series) - 1:
            labels.append(ft.ChartAxisLabel(
                value=index,
                label=ft.Text(str(label), size=theme.FONT_TINY,
                              color=palette.muted),
            ))

    if not points:
        return empty_state("还没有数据可画", icon=ft.Icons.SHOW_CHART,
                           dark=palette.dark)

    low, high = min(values), max(values)
    # 上下留 10% 余量，曲线不至于贴着边框；全平时给一个固定区间
    span = high - low
    if span <= 0:
        span = max(abs(high) * 0.1, 1.0)
    min_y = low - span * 0.12
    max_y = high + span * 0.12

    data = ft.LineChartData(
        data_points=points,
        color=palette.chart_line,
        stroke_width=2.5,
        curved=True,
        stroke_cap_round=True,
        below_line_bgcolor=ft.Colors.with_opacity(0.14, palette.chart_line),
    )

    return ft.LineChart(
        data_series=[data],
        height=height,
        min_y=min_y,
        max_y=max_y,
        min_x=0,
        max_x=max(len(points) - 1, 1),
        animate=ft.Animation(260, ft.AnimationCurve.EASE_OUT),
        interactive=True,
        tooltip_bgcolor=ft.Colors.with_opacity(0.92, "#1F2733" if palette.dark else "#FFFFFF"),
        horizontal_grid_lines=ft.ChartGridLines(
            interval=max(span / 3, 1.0), color=palette.chart_grid, width=1),
        left_axis=ft.ChartAxis(
            show_labels=True,
            labels_size=42,
            title_size=12,
            labels=[
                ft.ChartAxisLabel(
                    value=value,
                    label=ft.Text(format_money(value, thousands=False, symbol=tooltip_prefix),
                                  size=theme.FONT_TINY, color=palette.muted),
                )
                for value in (min_y + (max_y - min_y) * ratio for ratio in (0.0, 0.5, 1.0))
            ],
        ),
        bottom_axis=ft.ChartAxis(show_labels=True, labels=labels, labels_size=26),
    )


def pie_chart(stats: Sequence, *, palette: theme.Palette, height: int = 200) -> ft.Control:
    """饼图（圆环）：展示分类占比。

    ``stats`` 是 :class:`models.CategoryStat` 列表（已带 ``share``）。
    """
    if not stats:
        return empty_state("这个月还没有数据", icon=ft.Icons.PIE_CHART_OUTLINE,
                           dark=palette.dark)

    sections: list[ft.PieChartSection] = []
    for index, item in enumerate(stats):
        color = item.color or palette.chart_color(index)
        share = float(item.share or 0) * 100
        sections.append(ft.PieChartSection(
            value=float(item.amount),
            color=color,
            radius=46,
            # 占比太小时不显示文字，否则会糊成一团
            title=f"{share:.0f}%" if share >= 7 else "",
            title_style=ft.TextStyle(size=theme.FONT_TINY, color="#FFFFFF",
                                     weight=ft.FontWeight.W_600),
        ))

    return ft.PieChart(
        sections=sections,
        height=height,
        sections_space=2,
        center_space_radius=34,
        animate=ft.Animation(320, ft.AnimationCurve.EASE_OUT),
    )


def legend_row(stats: Sequence, *, palette: theme.Palette,
               limit: int = 6) -> ft.Control:
    """饼图图例：色块 + 分类名 + 金额 + 占比。"""
    rows: list[ft.Control] = []
    for index, item in enumerate(list(stats)[:limit]):
        color = item.color or palette.chart_color(index)
        percent = format_percent(item.share) if item.share is not None else "—"
        rows.append(ft.Row(
            [
                ft.Container(width=10, height=10, border_radius=3, bgcolor=color),
                ft.Text(item.name, size=theme.FONT_SMALL, expand=True,
                        max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                ft.Text(format_money(item.amount), size=theme.FONT_SMALL,
                        color=palette.on_surface),
                ft.Text(percent, size=theme.FONT_TINY, color=palette.muted, width=46,
                        text_align=ft.TextAlign.RIGHT),
            ],
            spacing=theme.PAD_S,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ))
    if len(stats) > limit:
        rows.append(ft.Text(f"其余 {len(stats) - limit} 个分类略",
                            size=theme.FONT_TINY, color=palette.muted))
    return ft.Column(rows, spacing=theme.PAD_S)

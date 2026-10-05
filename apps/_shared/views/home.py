"""首页仪表盘。

展示内容
--------
* 总存款大字（历史所有收入 − 支出）
* 月份切换：本月总收入、总支出、结余、储蓄率（可回看历史月份）
* 存钱目标卡片列表：进度条、已存/目标、差额、截止日期、每月建议存入
* 最近流水速览

所有数字都来自 ``services`` 层，这里只负责排版。
"""

from __future__ import annotations

import flet as ft

from _shared import components as ui
from _shared import theme
from _shared.views.base import BaseView
from services import goal_service, stats_service
from utils.money import format_money, format_percent


class HomeView(BaseView):

    def __init__(self, shell):
        super().__init__(shell)
        today = stats_service.current_month()
        self.year: int = today[0]
        self.month: int = today[1]
        self.total_balance = None
        self.summary = None
        self.goals: list = []
        self.recent: list = []

    # ------------------------------------------------------------ 取数

    def load(self) -> None:
        from db.repositories import transaction_repo

        self.total_balance = stats_service.total_balance()
        self.starting_balance = stats_service.starting_balance()
        self.transaction_net = stats_service.transaction_net()
        self.summary = stats_service.monthly_summary(self.year, self.month)
        self.goals = goal_service.list_progress()
        self.recent = transaction_repo.recent_transactions(4)

    # ------------------------------------------------------------ 渲染

    def render(self) -> ft.Control:
        return ft.Column(
            [
                ui.page_header(
                    "Flipped的存钱罐",
                    subtitle="记一笔、看进度、管目标",
                    trailing=ft.IconButton(
                        icon=ft.Icons.CONTRAST,
                        tooltip="切换浅色/深色",
                        on_click=lambda _e: self.shell.toggle_theme(),
                    ),
                ),
                self._hero_card(),
                self.gap(theme.PAD_M),
                self._month_switch(),
                self.gap(theme.PAD_S),
                self._stats_grid(),
                self.gap(theme.PAD_M),
                self._goals_section(),
                self.gap(theme.PAD_M),
                self._recent_section(),
                self.gap(theme.PAD_L),
            ],
            spacing=0,
        )

    # -------------------------------------------------- 总存款大字

    def _hero_card(self) -> ft.Control:
        negative = self.total_balance < 0
        color = self.palette.expense if negative else self.palette.income

        # 有初始财产时把构成写清楚，避免用户看到总存款对不上自己的预期
        if self.starting_balance:
            hint = (f"初始财产 {format_money(self.starting_balance)} "
                    f"+ 收支净额 {format_money(self.transaction_net)}")
        elif negative:
            hint = "支出大于收入，注意控制"
        else:
            hint = "所有收入减去所有支出"

        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.SAVINGS_OUTLINED, size=18, color=self.palette.muted),
                            ft.Text("总存款", size=theme.FONT_SMALL, color=self.palette.muted),
                        ],
                        spacing=theme.PAD_XS,
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                    ui.money_text(
                        self.total_balance,
                        size=theme.FONT_HERO,
                        weight=ft.FontWeight.BOLD,
                        color=color,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Text(hint, size=theme.FONT_TINY, color=self.palette.muted,
                            text_align=ft.TextAlign.CENTER),
                ],
                spacing=theme.PAD_XS,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.padding.symmetric(vertical=theme.PAD_L, horizontal=theme.PAD_M),
            border_radius=theme.RADIUS_L,
            gradient=ft.LinearGradient(
                begin=ft.alignment.top_left,
                end=ft.alignment.bottom_right,
                colors=[ft.Colors.with_opacity(0.16, color),
                        ft.Colors.with_opacity(0.04, color)],
            ),
        )

    # -------------------------------------------------- 月份切换

    def _month_switch(self) -> ft.Control:
        is_current = (self.year, self.month) == stats_service.current_month()
        return ft.Row(
            [
                ft.IconButton(
                    icon=ft.Icons.CHEVRON_LEFT,
                    tooltip="上一个月",
                    on_click=lambda _e: self._shift_month(-1),
                ),
                ft.Text(f"{self.year} 年 {self.month} 月", size=theme.FONT_BODY,
                        weight=ft.FontWeight.W_600, expand=True,
                        text_align=ft.TextAlign.CENTER),
                ft.IconButton(
                    icon=ft.Icons.CHEVRON_RIGHT,
                    tooltip="下一个月",
                    disabled=is_current,
                    on_click=lambda _e: self._shift_month(1),
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def _shift_month(self, delta: int) -> None:
        self.year, self.month = stats_service.shift_month(self.year, self.month, delta)
        self.changed()

    # -------------------------------------------------- 四个指标

    def _stats_grid(self) -> ft.Control:
        summary = self.summary
        rate_text = format_percent(summary.savings_rate)
        rate_hint = "本月无收入，无法计算" if summary.savings_rate is None else None
        balance_color = self.palette.income if summary.balance >= 0 else self.palette.expense
        rate_color = self.palette.muted if summary.savings_rate is None else (
            self.palette.income if summary.savings_rate >= 0 else self.palette.expense
        )

        # 手机上宽度只有 380 左右，四块并排会把金额挤断行：
        # 用响应式网格，窄屏两列换行、宽屏一行放下。
        tile_col = {"xs": 6, "sm": 3}
        grid = ui.stat_grid([
            ui.stat_tile("收入", format_money(summary.income), color=self.palette.income,
                         icon=ft.Icons.ARROW_DOWNWARD, compact=True, col=tile_col),
            ui.stat_tile("支出", format_money(summary.expense), color=self.palette.expense,
                         icon=ft.Icons.ARROW_UPWARD, compact=True, col=tile_col),
            ui.stat_tile("结余", format_money(summary.balance), color=balance_color,
                         icon=ft.Icons.ACCOUNT_BALANCE, compact=True, col=tile_col),
            ui.stat_tile("储蓄率", rate_text, color=rate_color,
                         subtitle=rate_hint, icon=ft.Icons.PERCENT, compact=True, col=tile_col),
        ])
        return ui.card(grid, padding=theme.PAD_S, dark=self.palette.dark)

    # -------------------------------------------------- 存钱目标

    def _goals_section(self) -> ft.Control:
        add_button = ft.TextButton(
            "新增目标",
            icon=ft.Icons.ADD,
            on_click=lambda _e: self._open_goal_dialog(),
        )
        header = ui.section_title("存钱目标", trailing=add_button)

        if not self.goals:
            body: ft.Control = ui.empty_state(
                "还没有存钱目标",
                hint="设一个目标（比如买电脑、旅游），首页就能看到进度和每月该存多少",
                icon=ft.Icons.FLAG_OUTLINED,
                action=ft.FilledButton("新建第一个目标",
                                       on_click=lambda _e: self._open_goal_dialog()),
                dark=self.palette.dark,
            )
        else:
            body = ft.Column(
                [ui.goal_card(goal, self.palette, on_tap=self._open_goal_dialog)
                 for goal in self.goals],
                spacing=theme.PAD_S,
            )
        return ft.Column([header, self.gap(theme.PAD_S), body], spacing=0)

    def _open_goal_dialog(self, goal_id: int | None = None) -> None:
        """首页也能直接编辑目标，复用设置页的同一个对话框。"""
        from _shared.views.settings import GoalEditorDialog

        GoalEditorDialog(self, goal_id=goal_id).open()

    # -------------------------------------------------- 最近流水

    def _recent_section(self) -> ft.Control:
        header = ui.section_title(
            "最近流水",
            trailing=ft.TextButton(
                "查看全部",
                icon=ft.Icons.CHEVRON_RIGHT,
                on_click=lambda _e: self.shell.goto(2),
            ),
        )
        if not self.recent:
            body: ft.Control = ui.empty_state(
                "还没有记过账",
                hint="点底部「记一笔」开始记录第一笔收入或支出",
                icon=ft.Icons.RECEIPT_LONG_OUTLINED,
                action=ft.FilledButton("去记一笔", on_click=lambda _e: self.shell.goto(1)),
                dark=self.palette.dark,
            )
        else:
            rows: list[ft.Control] = []
            for index, tx in enumerate(self.recent):
                if index:
                    rows.append(ui.divider(dark=self.palette.dark))
                rows.append(ui.transaction_tile(tx, self.palette))
            body = ui.card(ft.Column(rows, spacing=0), padding=0, dark=self.palette.dark)
        return ft.Column([header, self.gap(theme.PAD_S), body], spacing=0)

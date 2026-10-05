"""流水列表页面。

* 按时间倒序展示，收入绿色、支出红色
* 点击单条：编辑 / 删除（删除有二次确认）
* 按月份筛选，头部显示该月收入、支出、结余、笔数
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import flet as ft

from _shared import components as ui
from _shared import theme
from _shared.views.base import BaseView
from db.repositories import category_repo, transaction_repo
from db.repositories.transaction_repo import (
    TransactionError,
    TransactionFilter,
    TransactionInput,
)
from errors import AppError
from models import KIND_EXPENSE, KIND_INCOME, kind_label
from services import stats_service
from utils.money import format_money, parse_money

ALL_MONTHS = "all"


class TransactionListView(BaseView):

    def __init__(self, shell):
        super().__init__(shell)
        today = stats_service.current_month()
        self.filter_year: int | None = today[0]
        self.filter_month: int | None = today[1]
        self.transactions: list = []
        self.total_count = 0
        self.summary_income = None
        self.summary_expense = None
        # 图表：曲线图看趋势，饼图看分类占比
        self.chart_mode = "line"          # line | pie
        self.pie_kind = KIND_EXPENSE      # 饼图当前看支出还是收入
        self.series: list = []
        self.category_stats: list = []

    # ------------------------------------------------------------ 取数

    def load(self) -> None:
        flt = TransactionFilter(year=self.filter_year, month=self.filter_month)
        self.transactions = transaction_repo.list_transactions(flt)
        self.total_count = transaction_repo.count_transactions(flt)

        if self.filter_year and self.filter_month:
            year, month = self.filter_year, self.filter_month
            summary = stats_service.monthly_summary(year, month)
            self.summary_income, self.summary_expense = summary.income, summary.expense
        else:
            year, month = stats_service.current_month()
            self.summary_income = stats_service.total_income()
            self.summary_expense = stats_service.total_expense()

        # 图表数据：每次刷新都重新取，保证流水一变图表就跟着变
        self.series = stats_service.daily_balance_series(year, month)
        self.category_stats = stats_service.category_breakdown(year, month, self.pie_kind)

    # ------------------------------------------------------------ 渲染

    def render(self) -> ft.Control:
        return ft.Column(
            [
                self._header(),
                self.gap(theme.PAD_M),
                self._month_filter(),
                self.gap(theme.PAD_M),
                self._summary_card(),
                self.gap(theme.PAD_M),
                self._chart_card(),
                self.gap(theme.PAD_M),
                self._list_section(),
                self.gap(theme.PAD_L),
            ],
            spacing=0,
        )

    def _header(self) -> ft.Control:
        return ui.page_header(
            "流水明细",
            subtitle=f"共 {self.total_count} 笔",
            trailing=ft.FilledButton("记一笔", icon=ft.Icons.ADD,
                                     on_click=lambda _e: self.shell.goto(1)),
        )

    # -------------------------------------------------- 图表

    def _chart_card(self) -> ft.Control:
        """曲线图 / 饼图切换。

        数据在 ``load()`` 里每次重新取，所以**记一笔、改一笔、删一笔之后
        图表都会跟着刷新**（不需要联网，全部本地计算）。
        """
        tabs = ft.SegmentedButton(
            segments=[
                ft.Segment(value="line", label=ft.Text("曲线图"),
                           icon=ft.Icon(ft.Icons.SHOW_CHART)),
                ft.Segment(value="pie", label=ft.Text("饼图"),
                           icon=ft.Icon(ft.Icons.PIE_CHART_OUTLINE)),
            ],
            selected={self.chart_mode},
            on_change=self._on_chart_mode_change,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=theme.BUTTON_RADIUS)),
        )

        if self.chart_mode == "line":
            period = ("全部流水" if self.filter_year is None
                      else f"{self.filter_year} 年 {self.filter_month} 月")
            body: ft.Control = ft.Column(
                [
                    ft.Text(f"{period} · 每天结束时的存款",
                            size=theme.FONT_SMALL, color=self.palette.muted),
                    self.gap(theme.PAD_S),
                    ui.line_chart(self.series, palette=self.palette, height=190),
                    ft.Text("金额为当天结束时的累计存款（含初始财产与往日结余）",
                            size=theme.FONT_TINY, color=self.palette.muted),
                ],
                spacing=0,
            )
        else:
            kind_switch = ft.SegmentedButton(
                segments=[
                    ft.Segment(value=KIND_EXPENSE, label=ft.Text("支出")),
                    ft.Segment(value=KIND_INCOME, label=ft.Text("收入")),
                ],
                selected={self.pie_kind},
                on_change=self._on_pie_kind_change,
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=theme.BUTTON_RADIUS)),
            )
            total = sum((item.amount for item in self.category_stats), Decimal("0"))
            body = ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text(f"{kind_label(self.pie_kind)}构成 · 共 {format_money(total)}",
                                    size=theme.FONT_SMALL, color=self.palette.muted,
                                    expand=True),
                            kind_switch,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    self.gap(theme.PAD_S),
                    ft.Row(
                        [
                            ft.Container(content=ui.pie_chart(self.category_stats,
                                                              palette=self.palette, height=190),
                                         expand=True),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                    self.gap(theme.PAD_S),
                    ui.legend_row(self.category_stats, palette=self.palette, limit=6),
                ],
                spacing=0,
            )

        return ui.card(
            ft.Column([ft.Row([tabs]), self.gap(theme.PAD_M), body], spacing=0),
            dark=self.palette.dark,
        )

    def _on_chart_mode_change(self, event: ft.ControlEvent) -> None:
        selected = event.control.selected or set()
        if selected:
            self.chart_mode = next(iter(selected))
        self.changed()

    def _on_pie_kind_change(self, event: ft.ControlEvent) -> None:
        selected = event.control.selected or set()
        if selected:
            self.pie_kind = next(iter(selected))
        self.changed()

    def _month_filter(self) -> ft.Control:
        months = transaction_repo.available_months(limit=12)
        current = stats_service.current_month()
        if current not in months:
            months = [current, *months]

        chips: list[ft.Control] = [
            ui.chip(
                "全部",
                selected=self.filter_year is None,
                on_click=lambda _e: self._set_month(None, None),
            )
        ]
        for year, month in months:
            selected = (self.filter_year == year and self.filter_month == month)
            chips.append(ui.chip(
                f"{year}/{month:02d}",
                selected=selected,
                on_click=self._make_month_handler(year, month),
            ))
        return ft.Row(chips, spacing=theme.PAD_S, wrap=True, scroll=ft.ScrollMode.AUTO)

    def _make_month_handler(self, year: int, month: int):
        def handler(_event) -> None:
            self._set_month(year, month)

        return handler

    def _set_month(self, year: int | None, month: int | None) -> None:
        self.filter_year, self.filter_month = year, month
        self.changed()

    def _summary_card(self) -> ft.Control:
        balance = (self.summary_income or 0) - (self.summary_expense or 0)
        label = "全部流水" if self.filter_year is None else f"{self.filter_year} 年 {self.filter_month} 月"
        tile_col = {"xs": 4, "sm": 4}
        grid = ui.stat_grid([
            ui.stat_tile("收入", format_money(self.summary_income),
                         color=self.palette.income, compact=True, col=tile_col),
            ui.stat_tile("支出", format_money(self.summary_expense),
                         color=self.palette.expense, compact=True, col=tile_col),
            ui.stat_tile("结余", format_money(balance),
                         color=self.palette.income if balance >= 0
                         else self.palette.expense, compact=True, col=tile_col),
        ])
        return ui.card(
            ft.Column(
                [
                    ft.Text(label, size=theme.FONT_SMALL, color=self.palette.muted),
                    ft.Container(height=theme.PAD_S),
                    grid,
                ],
                spacing=0,
            ),
            padding=theme.PAD_S,
            dark=self.palette.dark,
        )

    def _list_section(self) -> ft.Control:
        if not self.transactions:
            return ui.empty_state(
                "这个时间段还没有流水",
                hint="换个月份看看，或者点「记一笔」新增一条",
                icon=ft.Icons.RECEIPT_LONG_OUTLINED,
                action=ft.FilledButton("去记一笔", on_click=lambda _e: self.shell.goto(1)),
                dark=self.palette.dark,
            )

        rows: list[ft.Control] = []
        last_date: date | None = None
        for tx in self.transactions:
            if tx.happened_on != last_date:
                last_date = tx.happened_on
                rows.append(ft.Container(
                    content=ft.Text(self._date_label(last_date), size=theme.FONT_TINY,
                                    color=self.palette.muted),
                    padding=ft.padding.only(left=theme.PAD_M, top=theme.PAD_S,
                                            bottom=theme.PAD_XS),
                ))
            rows.append(ui.transaction_tile(tx, self.palette, on_tap=self._open_editor,
                                            show_date=False))
        return ui.card(ft.Column(rows, spacing=0), padding=0, dark=self.palette.dark)

    @staticmethod
    def _date_label(value: date) -> str:
        weekday = "一二三四五六日"[value.weekday()]
        today = date.today()
        if value == today:
            return f"今天 · {value.strftime('%Y-%m-%d')}"
        if (today - value).days == 1:
            return f"昨天 · {value.strftime('%Y-%m-%d')}"
        return f"{value.strftime('%Y-%m-%d')} 周{weekday}"

    # ------------------------------------------------------------ 编辑 / 删除

    def _open_editor(self, transaction_id: int) -> None:
        from _shared.views.edit_transaction import TransactionEditorDialog

        TransactionEditorDialog(self, transaction_id).open()

    def _open_delete_confirm(self, transaction_id: int) -> None:
        from _shared.views.edit_transaction import TransactionEditorDialog

        TransactionEditorDialog(self, transaction_id).confirm_delete()

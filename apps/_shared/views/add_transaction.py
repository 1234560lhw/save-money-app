"""记一笔页面。

* 收入 / 支出切换（切换后分类下拉自动过滤）
* 金额输入：手机上唤起数字键盘
* 分类下拉（带图标与颜色）、备注、日期选择
* 表单校验：负数、非数字、为空都会被拦下并给出中文提示
* 可一键把该笔金额存入某个存钱目标（记账与攒钱联动）
"""

from __future__ import annotations

from datetime import date

import flet as ft

from _shared import components as ui
from _shared import theme
from _shared.views.base import BaseView
from db.repositories import category_repo, transaction_repo
from db.repositories.transaction_repo import TransactionInput
from errors import AppError
from models import KIND_EXPENSE, KIND_INCOME
from services import goal_service
from utils.money import format_money, parse_money


class AddTransactionView(BaseView):

    def __init__(self, shell):
        super().__init__(shell)
        # 表单状态：放在实例上，切换标签回来内容还在
        self.kind = KIND_EXPENSE
        self.amount_text = ""
        self.category_id: int | None = None
        self.note_text = ""
        self.happened_on: date = date.today()
        self.goal_id: int | None = None
        self.categories: list = []
        self.goals: list = []

        # 常驻控件（只创建一次，避免重建丢失输入焦点）
        # 外观参数来自 theme.field_style()，保证跟随明暗主题且是圆角
        self.amount_field = ft.TextField(
            label="金额",
            hint_text="0.00",
            prefix_text="¥",
            keyboard_type=ft.KeyboardType.NUMBER,
            on_change=self._on_amount_change,
            autofocus=False,
            **theme.field_style(self.palette.dark, text_size=26),
        )
        self.note_field = ft.TextField(
            label="备注（可选）",
            hint_text="例如：和朋友吃饭",
            max_length=100,
            on_change=lambda e: setattr(self, "note_text", e.control.value or ""),
            **theme.field_style(self.palette.dark),
        )
        self.category_dropdown = ft.Dropdown(
            label="分类",
            options=[],
            on_change=self._on_category_change,
            **theme.field_style(self.palette.dark),
        )
        self.goal_dropdown = ft.Dropdown(
            label="存入存钱目标（可选）",
            options=[ft.dropdown.Option(key="", text="不关联目标")],
            value="",
            on_change=self._on_goal_change,
            **theme.field_style(self.palette.dark),
        )
        self.date_button = ft.OutlinedButton(
            icon=ft.Icons.CALENDAR_MONTH,
            on_click=self._pick_date,
            style=self.palette.button(filled=False),
        )
        self.date_picker = ft.DatePicker(
            first_date=date(2000, 1, 1),
            last_date=date(2100, 12, 31),
            on_change=self._on_date_picked,
        )
        self.type_switch = ft.SegmentedButton(
            segments=[
                ft.Segment(value=KIND_EXPENSE, label=ft.Text("支出"),
                           icon=ft.Icon(ft.Icons.ARROW_UPWARD)),
                ft.Segment(value=KIND_INCOME, label=ft.Text("收入"),
                           icon=ft.Icon(ft.Icons.ARROW_DOWNWARD)),
            ],
            selected={KIND_EXPENSE},
            on_change=self._on_kind_change,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=theme.BUTTON_RADIUS)),
        )

    # ------------------------------------------------------------ 取数

    def load(self) -> None:
        self.categories = category_repo.list_categories(self.kind)
        self.goals = goal_service.list_progress()
        # 分类被删掉后要清空选中，避免保存时引用不存在的分类
        if self.category_id is not None and all(c.id != self.category_id for c in self.categories):
            self.category_id = None

    # ------------------------------------------------------------ 渲染

    def render(self) -> ft.Control:
        self._sync_theme()
        self._sync_type_switch()
        self._sync_category_options()
        self._sync_goal_options()
        self._sync_date_button()
        self.amount_field.value = self.amount_text
        self.note_field.value = self.note_text

        return ft.Column(
            [
                ui.page_header("记一笔", subtitle="收入和支出都可以记，金额不能为负"),
                self.gap(theme.PAD_S),
                ft.Row([self.type_switch], alignment=ft.MainAxisAlignment.CENTER),
                self.gap(theme.PAD_M),
                self.amount_field,
                self.gap(theme.PAD_S),
                self._quick_amounts(),
                self.gap(theme.PAD_M),
                self.category_dropdown,
                self.gap(theme.PAD_M),
                self.date_button,
                self.gap(theme.PAD_M),
                self.note_field,
                self.gap(theme.PAD_M),
                self.goal_dropdown,
                self.gap(theme.PAD_L),
                self._save_button(),
                self.gap(theme.PAD_S),
                ft.Text("保存后表单会自动清空，方便连续记账。",
                        size=theme.FONT_TINY, color=self.palette.muted,
                        text_align=ft.TextAlign.CENTER),
                self.gap(theme.PAD_L),
            ],
            spacing=0,
        )

    # -------------------------------------------------- 各控件同步

    def _sync_theme(self) -> None:
        """把明暗主题同步到输入框/按钮上。

        控件是常驻实例（避免重建丢焦点），所以主题切换后必须自己把
        颜色与圆角刷一遍，否则浅色模式下文字仍是浅色，看不清。
        """
        style = self.palette.field()
        for field in (self.amount_field, self.note_field,
                      self.category_dropdown, self.goal_dropdown):
            field.border_radius = style["border_radius"]
            field.border = style["border"]
            field.border_color = style["border_color"]
            field.focused_border_color = style["focused_border_color"]
            field.color = style["color"]
            field.bgcolor = style["bgcolor"]
            field.label_style = style["label_style"]
            field.hint_style = style["hint_style"]
        self.date_button.style = self.palette.button(filled=False)
        self.type_switch.style = ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=theme.BUTTON_RADIUS)
        )

    def _sync_type_switch(self) -> None:
        self.type_switch.selected = {self.kind}

    def _sync_category_options(self) -> None:
        self.category_dropdown.options = [
            ft.dropdown.Option(
                key=str(cat.id),
                text=cat.name,
                content=ft.Row(
                    [
                        ft.Icon(cat.icon or ft.Icons.CATEGORY, size=18, color=cat.color),
                        ft.Text(cat.name, size=theme.FONT_BODY),
                    ],
                    spacing=theme.PAD_S,
                    tight=True,
                ),
            )
            for cat in self.categories
        ]
        self.category_dropdown.value = str(self.category_id) if self.category_id else None

    def _sync_goal_options(self) -> None:
        options = [ft.dropdown.Option(key="", text="不关联目标")]
        for goal in self.goals:
            options.append(ft.dropdown.Option(
                key=str(goal.goal_id),
                text=f"{goal.name}（还差 {format_money(goal.remaining)}）",
            ))
        self.goal_dropdown.options = options
        self.goal_dropdown.value = str(self.goal_id) if self.goal_id else ""

    def _sync_date_button(self) -> None:
        today = date.today()
        label = self.happened_on.strftime("%Y-%m-%d")
        if self.happened_on == today:
            label += "（今天）"
        self.date_button.text = label

    def _quick_amounts(self) -> ft.Control:
        """常用金额快捷输入，手机上少敲几次键盘。"""
        presets = ["10", "20", "50", "100", "200", "500"]
        return ft.Row(
            [
                ui.chip(f"{value}", on_click=self._make_preset_handler(value),
                        dark=self.palette.dark)
                for value in presets
            ],
            spacing=theme.PAD_S,
            wrap=True,
        )

    def _make_preset_handler(self, value: str):
        def handler(_event) -> None:
            self.amount_text = value
            self.amount_field.value = value
            self.page.update()

        return handler

    def _save_button(self) -> ft.FilledButton:
        """保存按钮：圆角 + 跟随主题的主色。"""
        return ft.FilledButton(
            "保存",
            icon=ft.Icons.CHECK,
            height=48,
            on_click=self._save,
            style=self.palette.button(),
        )

    # -------------------------------------------------- 事件

    def _on_kind_change(self, event: ft.ControlEvent) -> None:
        selected = event.control.selected or set()
        if selected:
            self.kind = next(iter(selected))
        self.category_id = None
        self.categories = category_repo.list_categories(self.kind)
        self._sync_category_options()
        self.page.update()

    def _on_amount_change(self, event: ft.ControlEvent) -> None:
        self.amount_text = event.control.value or ""

    def _on_category_change(self, event: ft.ControlEvent) -> None:
        value = event.control.value
        self.category_id = int(value) if value else None

    def _on_goal_change(self, event: ft.ControlEvent) -> None:
        value = event.control.value
        self.goal_id = int(value) if value else None

    def _pick_date(self, _event: ft.ControlEvent) -> None:
        self.date_picker.value = self.happened_on
        self.page.open(self.date_picker)

    def _on_date_picked(self, event: ft.ControlEvent) -> None:
        value = event.control.value
        if isinstance(value, str):
            try:
                value = date.fromisoformat(value[:10])
            except ValueError:
                value = None
        if value:
            self.happened_on = value if isinstance(value, date) else date.today()
        self._sync_date_button()
        self.page.update()

    # -------------------------------------------------- 保存

    def _save(self, _event: ft.ControlEvent) -> None:
        try:
            amount = parse_money(self.amount_text, field="金额")
        except AppError as exc:
            self.toast(str(exc), error=True)
            return

        if self.category_id is None:
            self.toast("请选择一个分类", error=True)
            return

        try:
            created = transaction_repo.create_transaction(TransactionInput(
                kind=self.kind,
                amount=amount,
                category_id=self.category_id,
                happened_on=self.happened_on,
                note=self.note_text,
            ))
        except AppError as exc:
            self.toast(str(exc), error=True)
            return

        message = f"已记录{'收入' if created.is_income else '支出'} {format_money(created.amount)}"

        # 关联存钱目标：直接把金额存进去
        if self.goal_id:
            try:
                goal = goal_service.deposit(self.goal_id, amount)
                message += f"，已存入「{goal.name}」"
            except AppError as exc:
                self.toast(f"流水已保存，但存入目标失败：{exc}", error=True)

        self._reset_form()
        self.changed(message)

    def _reset_form(self) -> None:
        self.amount_text = ""
        self.note_text = ""
        self.goal_id = None
        self.category_id = None
        self.happened_on = date.today()
        self.amount_field.value = ""
        self.note_field.value = ""

    def reset_to_income(self) -> None:
        """供外部（如设置页模板）切到收入模式。"""
        self.kind = KIND_INCOME
        self.category_id = None
        self.mark_dirty()

"""单条流水的编辑 / 删除弹窗。

从流水列表点进来，可以改类型、金额、分类、日期、备注，或者删除这条记录。
删除走二次确认，避免误触。
"""

from __future__ import annotations

from datetime import date

import flet as ft

from _shared import components as ui
from _shared import theme
from db.repositories import category_repo, transaction_repo
from db.repositories.transaction_repo import TransactionInput
from errors import AppError
from models import KIND_EXPENSE, KIND_INCOME
from utils.money import format_money, money_to_db, parse_money


class TransactionEditorDialog:
    """编辑一条流水。``view`` 是调用它的页面，用来刷新列表。"""

    def __init__(self, view, transaction_id: int):
        self.view = view
        self.page = view.page
        self.palette = view.palette
        self.transaction = transaction_repo.get_transaction(transaction_id)
        self.error_text: str | None = None

        if self.transaction is None:
            self.amount_field = self.note_field = None  # type: ignore[assignment]
            self.category_dropdown = self.kind_switch = None  # type: ignore[assignment]
            self.date_button = self.date_picker = None  # type: ignore[assignment]
            self.dialog = None  # type: ignore[assignment]
            return

        tx = self.transaction
        self.kind = tx.kind
        self.happened_on = tx.happened_on
        self.category_id = tx.category_id
        self.categories = category_repo.list_categories(self.kind)
        self.amount_field = ft.TextField(
            label="金额", value=money_to_db(tx.amount), prefix_text="¥",
            keyboard_type=ft.KeyboardType.NUMBER, autofocus=True,
            on_change=self._clear_error,
            **theme.field_style(self.palette.dark),
        )
        self.note_field = ft.TextField(
            label="备注", value=tx.note, max_length=100, on_change=self._clear_error,
            **theme.field_style(self.palette.dark),
        )
        self.category_dropdown = ft.Dropdown(
            label="分类", value=str(tx.category_id) if tx.category_id else None,
            options=self._category_options(),
            **theme.field_style(self.palette.dark),
        )
        self.kind_switch = ft.SegmentedButton(
            segments=[
                ft.Segment(value=KIND_EXPENSE, label=ft.Text("支出")),
                ft.Segment(value=KIND_INCOME, label=ft.Text("收入")),
            ],
            selected={self.kind},
            on_change=self._on_kind_change,
        )
        self.date_button = ft.OutlinedButton(
            icon=ft.Icons.CALENDAR_MONTH, text=self.happened_on.strftime("%Y-%m-%d"),
            on_click=self._pick_date,
        )
        self.date_picker = ft.DatePicker(
            first_date=date(2000, 1, 1), last_date=date(2100, 12, 31),
            value=self.happened_on, on_change=self._on_date_picked,
        )
        self.error_control = ft.Text("", size=theme.FONT_SMALL, color=self.palette.expense)

        self.dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("编辑流水"),
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Row([self.kind_switch], alignment=ft.MainAxisAlignment.CENTER),
                        self.amount_field,
                        self.category_dropdown,
                        self.date_button,
                        self.note_field,
                        self.error_control,
                    ],
                    spacing=theme.PAD_S,
                    tight=True,
                    scroll=ft.ScrollMode.AUTO,
                ),
                width=380,
            ),
            actions=[
                ft.TextButton("删除", icon=ft.Icons.DELETE_OUTLINE,
                              on_click=lambda _e: self.confirm_delete(),
                              style=ft.ButtonStyle(color=self.palette.expense)),
                ft.TextButton("取消", on_click=lambda _e: self.close()),
                ft.FilledButton("保存", icon=ft.Icons.CHECK, on_click=self._save),
            ],
            actions_alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

    # ------------------------------------------------------------ 基础

    def _category_options(self) -> list:
        return [
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

    def open(self) -> None:
        if self.transaction is None:
            ui.message(self.page, "这条流水已经不存在了", error=True)
            self.view.changed()
            return
        self.page.open(self.dialog)

    def close(self) -> None:
        self.page.close(self.dialog)

    def _clear_error(self, _event=None) -> None:
        if self.error_text:
            self.error_text = None
            self.error_control.value = ""
            self.page.update()

    def _show_error(self, text: str) -> None:
        self.error_text = text
        self.error_control.value = text
        self.page.update()

    # ------------------------------------------------------------ 事件

    def _on_kind_change(self, event: ft.ControlEvent) -> None:
        selected = event.control.selected or set()
        if selected:
            self.kind = next(iter(selected))
        self.categories = category_repo.list_categories(self.kind)
        self.category_dropdown.options = self._category_options()
        self.category_dropdown.value = None
        self.category_id = None
        self.page.update()

    def _pick_date(self, _event: ft.ControlEvent) -> None:
        self.page.open(self.date_picker)

    def _on_date_picked(self, event: ft.ControlEvent) -> None:
        value = event.control.value
        if isinstance(value, str):
            try:
                value = date.fromisoformat(value[:10])
            except ValueError:
                value = None
        if isinstance(value, date):
            self.happened_on = value
        self.date_button.text = self.happened_on.strftime("%Y-%m-%d")
        self.page.update()

    # ------------------------------------------------------------ 保存 / 删除

    def _save(self, _event: ft.ControlEvent) -> None:
        try:
            amount = parse_money(self.amount_field.value, field="金额")
        except AppError as exc:
            self._show_error(str(exc))
            return

        category_value = self.category_dropdown.value
        if not category_value:
            self._show_error("请选择一个分类")
            return

        try:
            updated = transaction_repo.update_transaction(
                self.transaction.id,
                TransactionInput(
                    kind=self.kind,
                    amount=amount,
                    category_id=int(category_value),
                    happened_on=self.happened_on,
                    note=self.note_field.value or "",
                ),
            )
        except AppError as exc:
            self._show_error(str(exc))
            return

        self.close()
        self.view.changed(
            f"已更新：{'收入' if updated.is_income else '支出'} {format_money(updated.amount)}"
        )

    def confirm_delete(self) -> None:
        if self.transaction is None:
            return
        tx = self.transaction

        def do_delete() -> None:
            deleted = transaction_repo.delete_transaction(tx.id)
            if deleted:
                self.view.changed(f"已删除一笔{'收入' if tx.is_income else '支出'} "
                                  f"{format_money(tx.amount)}")
            else:
                self.view.changed("这条流水已经不存在了")

        ui.confirm_dialog(
            self.page,
            "删除这笔流水？",
            f"{tx.happened_on.strftime('%Y-%m-%d')}　"
            f"{'收入' if tx.is_income else '支出'} {format_money(tx.amount)}"
            f"（{tx.category_label}）\n删除后无法恢复，总存款会随之变化。",
            on_confirm=do_delete,
        )

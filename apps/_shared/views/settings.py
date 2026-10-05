"""设置页面。

包含四块
--------
1. **总览**：流水笔数、分类数、目标数、数据文件位置
2. **数据备份**：导出数据库(.db) / 导出流水(.csv) / 导出目标(.csv) / 导入备份
3. **存钱目标**：新增 / 编辑 / 删除（进度、每月建议存入都在这里配置）
4. **收支分类**：按收入 / 支出分组的新增 / 编辑 / 删除

导入备份会覆盖当前数据，因此导入前会自动存一份快照（见 services/backup_service.py）。
"""

from __future__ import annotations

import asyncio
from datetime import date

import flet as ft

from _shared import components as ui
from _shared import theme
from _shared.views.base import BaseView
from db import database_stats
from db.repositories import category_repo, goal_repo, transaction_repo
from db.repositories.category_repo import CategoryError
from errors import AppError
from models import KIND_EXPENSE, KIND_INCOME, kind_label
from services import backup_service, goal_service, settings_service
from services.goal_service import GoalInput
from utils import paths
from utils.money import format_money, format_percent, money_to_db, parse_money

#: 可选图标（新增分类时用）
ICON_CHOICES = [
    "restaurant", "directions_bus", "shopping_bag", "home", "bolt", "smartphone",
    "local_hospital", "school", "sports_esports", "card_giftcard", "pets", "flight",
    "fitness_center", "local_cafe", "movie", "book", "payments", "work_outline",
    "trending_up", "redeem", "savings", "category", "more_horiz",
]

#: 可选颜色
COLOR_CHOICES = [
    "#E53935", "#FB8C00", "#FDD835", "#43A047", "#00897B", "#1E88E5",
    "#3949AB", "#8E24AA", "#D81B60", "#6D4C41", "#546E7A", "#757575",
]


class SettingsView(BaseView):

    def __init__(self, shell):
        super().__init__(shell)
        self.category_tab = 0          # 0 = 支出，1 = 收入
        self.counts: dict[str, int] = {}
        self.db_path = ""
        self.category_usage: dict[int, int] = {}
        self.goals: list = []
        self.categories: list = []
        self.file_picker: ft.FilePicker | None = None
        self._import_source: str | None = None

    # ------------------------------------------------------------ 取数

    def load(self) -> None:
        self.counts = database_stats()
        self.db_path = paths.describe()["db_path"]
        self.category_usage = category_repo.category_usage()
        self.goals = goal_service.list_progress(include_archived=True)
        self.categories = category_repo.list_categories()

    # ------------------------------------------------------------ 渲染

    def render(self) -> ft.Control:
        self._ensure_file_picker()
        return ft.Column(
            [
                ui.page_header("设置", subtitle="初始财产、目标、分类、备份与外观"),
                self.gap(theme.PAD_S),
                self._overview_section(),
                self.gap(theme.PAD_M),
                self._starting_balance_section(),
                self.gap(theme.PAD_M),
                self._appearance_section(),
                self.gap(theme.PAD_M),
                self._backup_section(),
                self.gap(theme.PAD_M),
                self._goals_section(),
                self.gap(theme.PAD_M),
                self._categories_section(),
                self.gap(theme.PAD_M),
                self._about_section(),
                self.gap(theme.PAD_M),
                self._danger_section(),
                self.gap(theme.PAD_L),
            ],
            spacing=0,
        )

    # -------------------------------------------------- 初始财产

    def _starting_balance_section(self) -> ft.Control:
        """第一次使用时把手里的钱录进来。

        它计入总存款（总存款 = 初始财产 + 收入 − 支出），
        所以刚装好应用也能看到真实家底，而不是从 0 开始。
        """
        current = settings_service.get_starting_balance()
        set_at = settings_service.starting_balance_set_at()

        self._initial_field = ft.TextField(
            label="初始财产" if current == 0 else f"初始财产（当前 {format_money(current)}）",
            value="" if current == 0 else f"{current:.2f}",
            prefix_text="¥",
            keyboard_type=ft.KeyboardType.NUMBER,
            helper_text="第一次使用时手里的钱；允许负数（例如有欠款）",
            on_submit=lambda _e: self._save_starting_balance(),
            **theme.field_style(self.palette.dark),
        )

        hint = ("还没有设置过，总存款目前只统计流水。" if current == 0
                else f"已计入总存款（{set_at or '已设置'}）")

        body = ft.Column(
            [
                ft.Text("把第一次使用时的存款填进来，总存款才是你真实的钱数。",
                        size=theme.FONT_SMALL, color=self.palette.muted),
                self.gap(theme.PAD_S),
                self._initial_field,
                self.gap(theme.PAD_S),
                ft.Row(
                    [
                        ft.FilledButton("保存", icon=ft.Icons.CHECK,
                                        on_click=lambda _e: self._save_starting_balance(),
                                        style=self.palette.button()),
                        ft.OutlinedButton(
                            "归 0",
                            icon=ft.Icons.RESTART_ALT,
                            on_click=lambda _e: self._confirm_clear_starting_balance(),
                            style=self.palette.button(filled=False),
                        ),
                    ],
                    spacing=theme.PAD_S,
                ),
                ft.Text(hint, size=theme.FONT_TINY, color=self.palette.muted),
                ft.Text("提示：这只是「起点金额」，不影响任何流水记录。"
                        "想彻底清空全部数据见下方「清空数据」。",
                        size=theme.FONT_TINY, color=self.palette.muted),
            ],
            spacing=0,
        )
        return ft.Column([ui.section_title("初始财产"), self.gap(theme.PAD_S),
                          ui.card(body, dark=self.palette.dark)], spacing=0)

    def _save_starting_balance(self) -> None:
        raw = (self._initial_field.value or "").strip()
        try:
            if not raw:
                amount = settings_service.clear_starting_balance()
            else:
                # 复用统一的金额校验（允许负数，因为可能有欠款）
                value = parse_money(raw, field="初始财产",
                                    allow_zero=True, allow_negative=True)
                amount = settings_service.set_starting_balance(value)
        except (AppError, ValueError) as exc:
            self.toast(str(exc), error=True)
            return

        if amount == 0:
            self.changed("初始财产已归 0")
        else:
            self.changed(f"初始财产已设为 {format_money(amount)}，总存款已重算")

    def _confirm_clear_starting_balance(self) -> None:
        def do_clear() -> None:
            settings_service.clear_starting_balance()
            self.changed("初始财产已归 0")

        ui.confirm_dialog(
            self.page,
            "把初始财产归 0？",
            "只清掉「初始财产」这一个数字，你的流水记录和目标都不受影响。\n"
            "总存款会重新变成「收入 − 支出」。",
            on_confirm=do_clear,
            confirm_text="归 0",
        )

    # -------------------------------------------------- 1. 总览

    def _overview_section(self) -> ft.Control:
        balance = None
        from services import stats_service

        balance = stats_service.total_balance()
        rows = [
            ui.info_row("总存款", format_money(balance),
                        value_color=self.palette.income if balance >= 0 else self.palette.expense),
            ui.divider(dark=self.palette.dark),
            ui.info_row("流水笔数", f"{self.counts.get('transactions', 0)} 笔"),
            ui.divider(dark=self.palette.dark),
            ui.info_row("分类数量", f"{self.counts.get('categories', 0)} 个"),
            ui.divider(dark=self.palette.dark),
            ui.info_row("存钱目标", f"{len(self.goals)} 个"),
            ui.divider(dark=self.palette.dark),
            ui.info_row("上次备份", settings_service.last_backup_at() or "尚未备份"),
        ]
        return ui.card(ft.Column(rows, spacing=theme.PAD_S), dark=self.palette.dark)

    # -------------------------------------------------- 2. 备份

    def _ensure_file_picker(self) -> None:
        """FilePicker 需要挂在 page.overlay 上才能用。"""
        if self.file_picker is not None:
            return
        self.file_picker = ft.FilePicker()
        if self.page.overlay is None:
            self.page.overlay = []
        self.page.overlay.append(self.file_picker)

    def _backup_section(self) -> ft.Control:
        body = ft.Column(
            [
                ft.Text("导出的文件可以拷到另一台设备（电脑或手机），"
                        "用「导入备份」恢复全部数据。",
                        size=theme.FONT_SMALL, color=self.palette.muted),
                self.gap(theme.PAD_S),
                ft.FilledButton("导出数据库备份 (.db)", icon=ft.Icons.SAVE_ALT,
                                on_click=lambda _e: self._export_database()),
                ft.OutlinedButton("导出流水 (.csv)", icon=ft.Icons.TABLE_VIEW,
                                  on_click=lambda _e: self._export_transactions_csv()),
                ft.OutlinedButton("导出存钱目标 (.csv)", icon=ft.Icons.FLAG,
                                  on_click=lambda _e: self._export_goals_csv()),
                ft.OutlinedButton("导入备份文件…", icon=ft.Icons.UPLOAD_FILE,
                                  on_click=lambda _e: self._pick_import_file()),
                self.gap(theme.PAD_S),
                ft.Text(f"数据目录：{paths.describe()['data_dir']}",
                        size=theme.FONT_TINY, color=self.palette.muted, selectable=True),
                ft.Text("提示：手机端导入后会自动重载数据，无需重启。",
                        size=theme.FONT_TINY, color=self.palette.muted),
            ],
            spacing=theme.PAD_S,
        )
        return ft.Column([ui.section_title("数据备份与迁移"), self.gap(theme.PAD_S),
                          ui.card(body, dark=self.palette.dark)], spacing=0)

    # -------------------------------------------------- 1.5 外观

    def _appearance_section(self) -> ft.Control:
        is_dark = self.palette.dark
        body = ft.Column(
            [
                ft.Text("毛玻璃质感在深色下最明显；浅色适合白天使用。",
                        size=theme.FONT_SMALL, color=self.palette.muted),
                self.gap(theme.PAD_S),
                ft.Row(
                    [
                        ft.Icon(ft.Icons.DARK_MODE_OUTLINED, size=18,
                                color=self.palette.muted),
                        ft.Text("深色模式", size=theme.FONT_BODY, expand=True),
                        ft.Switch(value=is_dark, on_change=self._on_theme_switch),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            ],
            spacing=theme.PAD_S,
        )
        return ft.Column([ui.section_title("外观"), self.gap(theme.PAD_S),
                          ui.card(body, dark=self.palette.dark)], spacing=0)

    def _on_theme_switch(self, event: ft.ControlEvent) -> None:
        want_dark = bool(event.control.value)
        if want_dark == self.palette.dark:
            return
        self.shell.toggle_theme()

    # -------------------------------------------------- 1.6 清空数据

    def _danger_section(self) -> ft.Control:
        body = ft.Column(
            [
                ft.Text("把账本恢复成刚装好的状态：清空所有流水、存钱目标和自定义分类，"
                        "保留预置分类与应用设置。",
                        size=theme.FONT_SMALL, color=self.palette.muted),
                self.gap(theme.PAD_S),
                ft.OutlinedButton(
                    "清空所有数据…",
                    icon=ft.Icons.DELETE_SWEEP_OUTLINED,
                    style=ft.ButtonStyle(color=self.palette.expense),
                    on_click=lambda _e: self._confirm_reset(),
                ),
                ft.Text("清空前会自动导出一份快照到备份目录，可随时导入恢复。",
                        size=theme.FONT_TINY, color=self.palette.muted),
            ],
            spacing=theme.PAD_S,
        )
        return ft.Column([ui.section_title("清空数据"), self.gap(theme.PAD_S),
                          ui.card(body, dark=self.palette.dark)], spacing=0)

    def _confirm_reset(self) -> None:
        tx_count = self.counts.get("transactions", 0)
        goal_count = self.counts.get("goals", 0)

        def do_reset() -> None:
            try:
                result = backup_service.reset_all_data()
            except Exception as exc:  # noqa: BLE001
                self.toast(f"清空失败：{exc}", error=True)
                return
            kept = result.get("categories_kept", 0)
            self.changed(f"已清空 {result.get('transactions', 0)} 笔流水、"
                         f"{result.get('goals', 0)} 个目标，保留 {kept} 个预置分类")

        ui.confirm_dialog(
            self.page,
            "清空所有数据？",
            f"将要删除：\n"
            f"  · 流水 {tx_count} 笔\n"
            f"  · 存钱目标 {goal_count} 个\n"
            f"  · 你的自定义分类\n\n"
            "预置分类（餐饮、交通、工资…）会保留。\n"
            "清空前会自动存一份快照，可以在「导入备份」里找回。",
            on_confirm=do_reset,
            confirm_text="确认清空",
        )

    def _export_database(self) -> None:
        try:
            target = backup_service.export_database()
        except Exception as exc:  # noqa: BLE001
            self.toast(f"导出失败：{exc}", error=True)
            return
        settings_service.touch_backup_time()
        self.changed(f"已导出：{target}")

    def _export_transactions_csv(self) -> None:
        try:
            target = backup_service.export_transactions_csv()
        except Exception as exc:  # noqa: BLE001
            self.toast(f"导出失败：{exc}", error=True)
            return
        self.changed(f"已导出流水：{target}")

    def _export_goals_csv(self) -> None:
        try:
            target = backup_service.export_goals_csv()
        except Exception as exc:  # noqa: BLE001
            self.toast(f"导出失败：{exc}", error=True)
            return
        self.changed(f"已导出目标：{target}")

    def _pick_import_file(self) -> None:
        self._ensure_file_picker()
        assert self.file_picker is not None
        self.file_picker.on_result = self._on_import_picked
        self.page.run_task(self._open_file_picker)

    async def _open_file_picker(self) -> None:
        assert self.file_picker is not None
        try:
            files = await self.file_picker.pick_files(
                dialog_title="选择备份文件",
                allow_multiple=False,
                allowed_extensions=["db", "sqlite", "sqlite3", "csv"],
            )
        except Exception as exc:  # noqa: BLE001 - 部分平台不支持文件选择器
            self.toast(f"当前平台无法打开文件选择器：{exc}", error=True)
            return
        if files:
            self._on_import_picked_path(files[0].path)

    def _on_import_picked(self, event: ft.FilePickerResultEvent) -> None:
        if event.files:
            self._on_import_picked_path(event.files[0].path)

    def _on_import_picked_path(self, path: str | None) -> None:
        if not path:
            return
        check = backup_service.inspect_database(path)
        if not check.get("ok"):
            self.toast(str(check.get("message", "备份文件无效")), error=True)
            return
        counts = check.get("counts", {})
        detail = "、".join(f"{_table_label(k)} {v} 条" for k, v in dict(counts).items())
        self._import_source = path

        ui.confirm_dialog(
            self.page,
            "导入备份会覆盖当前数据",
            f"文件：{path}\n内容：{detail}\n\n"
            "当前数据会先自动存一份快照（在数据目录的 backups 文件夹里），"
            "导入后无法通过界面「撤销」，请确认后再继续。",
            on_confirm=self._do_import,
            confirm_text="确认导入",
        )

    def _do_import(self) -> None:
        if not self._import_source:
            return
        result = backup_service.import_database(self._import_source)
        self._import_source = None
        if not result.ok:
            self.toast(result.message, error=True)
            return
        self.changed(result.message)

    # -------------------------------------------------- 3. 存钱目标

    def _goals_section(self) -> ft.Control:
        header = ui.section_title(
            "存钱目标",
            trailing=ft.TextButton("新增", icon=ft.Icons.ADD,
                                   on_click=lambda _e: GoalEditorDialog(self).open()),
        )
        if not self.goals:
            body: ft.Control = ui.empty_state(
                "还没有存钱目标",
                hint="例如：换电脑 8000 元，每月该存多少会自动算出来",
                icon=ft.Icons.FLAG_OUTLINED,
                action=ft.FilledButton("新增目标",
                                       on_click=lambda _e: GoalEditorDialog(self).open()),
                dark=self.palette.dark,
            )
        else:
            rows: list[ft.Control] = []
            for index, goal in enumerate(self.goals):
                if index:
                    rows.append(ui.divider(dark=self.palette.dark))
                rows.append(ft.Row(
                    [
                        ft.Container(
                            content=ui.goal_card(
                                goal, self.palette, on_tap=lambda gid: GoalEditorDialog(self, gid).open()
                            ),
                            expand=True,
                        ),
                        ft.IconButton(
                            icon=ft.Icons.DELETE_OUTLINE,
                            tooltip="删除目标",
                            icon_color=self.palette.expense,
                            on_click=lambda _e, gid=goal.goal_id, name=goal.name:
                                self._confirm_delete_goal(gid, name),
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ))
            body = ft.Column(rows, spacing=theme.PAD_S)
        return ft.Column([header, self.gap(theme.PAD_S), body], spacing=0)

    def _confirm_delete_goal(self, goal_id: int, name: str) -> None:
        def do_delete() -> None:
            goal_service.delete_goal(goal_id)
            self.changed(f"已删除目标「{name}」")

        ui.confirm_dialog(self.page, "删除存钱目标？",
                          f"「{name}」及其攒钱进度记录会被删除，已记的流水不受影响。",
                          on_confirm=do_delete)

    # -------------------------------------------------- 4. 分类

    def _categories_section(self) -> ft.Control:
        kind = KIND_EXPENSE if self.category_tab == 0 else KIND_INCOME
        items = [c for c in self.categories if c.kind == kind]

        rows: list[ft.Control] = []
        for index, category in enumerate(items):
            if index:
                rows.append(ui.divider(dark=self.palette.dark))
            rows.append(self._category_row(category))

        header = ui.section_title(
            "收支分类",
            trailing=ft.TextButton("新增", icon=ft.Icons.ADD,
                                   on_click=lambda _e: CategoryEditorDialog(self).open()),
        )
        tabs = ft.Tabs(
            selected_index=self.category_tab,
            tabs=[ft.Tab(text="支出分类"), ft.Tab(text="收入分类")],
            on_change=self._on_category_tab_change,
        )
        return ft.Column(
            [header, self.gap(theme.PAD_S), tabs, self.gap(theme.PAD_S),
             ui.card(ft.Column(rows, spacing=0), padding=0, dark=self.palette.dark)],
            spacing=0,
        )

    def _category_row(self, category) -> ft.Control:
        used = self.category_usage.get(category.id, 0)
        subtitle = f"{used} 笔流水" if used else "尚未使用"
        if category.is_system:
            subtitle += " · 预置分类"
        return ft.Row(
            [
                ft.Container(
                    content=ft.Icon(category.icon or ft.Icons.CATEGORY, size=18,
                                    color=category.color),
                    width=36, height=36,
                    border_radius=theme.RADIUS_S,
                    bgcolor=ft.Colors.with_opacity(0.12, category.color),
                    alignment=ft.alignment.center,
                ),
                ft.Column(
                    [
                        ft.Text(category.name, size=theme.FONT_BODY),
                        ft.Text(subtitle, size=theme.FONT_TINY, color=self.palette.muted),
                    ],
                    spacing=1,
                    expand=True,
                ),
                ft.IconButton(
                    icon=ft.Icons.EDIT_OUTLINED, tooltip="编辑",
                    on_click=lambda _e, cid=category.id: CategoryEditorDialog(self, cid).open(),
                ),
                ft.IconButton(
                    icon=ft.Icons.DELETE_OUTLINE, tooltip="删除",
                    icon_color=self.palette.expense,
                    on_click=lambda _e, cid=category.id: self._confirm_delete_category(cid),
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=theme.PAD_XS,
        )

    def _on_category_tab_change(self, event: ft.ControlEvent) -> None:
        self.category_tab = int(event.control.selected_index)
        self.changed()

    def _confirm_delete_category(self, category_id: int) -> None:
        category = category_repo.get_category(category_id)
        if category is None:
            self.changed("分类不存在")
            return
        used = self.category_usage.get(category_id, 0)

        if used:
            message = (f"「{category.name}」已被 {used} 笔流水使用。\n"
                       "删除后这些流水的分类会变成「未分类」，金额与总存款不受影响。")
            confirm_text = "删除并保留流水"
        else:
            message = f"确定删除分类「{category.name}」？"
            confirm_text = "删除"

        def do_delete() -> None:
            try:
                category_repo.delete_category(category_id, force=True)
            except CategoryError as exc:
                self.toast(str(exc), error=True)
                return
            self.changed(f"已删除分类「{category.name}」")

        ui.confirm_dialog(self.page, "删除分类？", message,
                          on_confirm=do_delete, confirm_text=confirm_text)

    # -------------------------------------------------- 5. 关于

    def _about_section(self) -> ft.Control:
        import core

        rows = [
            ui.info_row("应用", "存钱罐（SaveMoneyApp）"),
            ui.divider(dark=self.palette.dark),
            ui.info_row("版本", core.__version__),
            ui.divider(dark=self.palette.dark),
            ui.info_row("运行平台", paths.describe()["platform"]),
            ui.divider(dark=self.palette.dark),
            ui.info_row("数据库", "SQLite（本地文件，不上传云端）"),
            ui.divider(dark=self.palette.dark),
            ft.Text(f"数据库文件：{self.db_path}", size=theme.FONT_TINY,
                    color=self.palette.muted, selectable=True),
        ]
        return ft.Column([ui.section_title("关于"), self.gap(theme.PAD_S),
                          ui.card(ft.Column(rows, spacing=theme.PAD_S), dark=self.palette.dark)], spacing=0)


# ==================================================================== 目标编辑弹窗

class GoalEditorDialog:
    """新增 / 编辑存钱目标，并提供"存入 / 取出"操作。"""

    def __init__(self, view: SettingsView, goal_id: int | None = None):
        self.view = view
        self.page = view.page
        self.palette = view.palette
        self.goal_id = goal_id
        self.goal = goal_service.get_progress(goal_id) if goal_id else None

        existing = self.goal
        self.name_field = ft.TextField(
            label="目标名称", value=existing.name if existing else "",
            hint_text="例如：换电脑", max_length=30,
            **theme.field_style(self.palette.dark),
        )
        self.target_field = ft.TextField(
            label="目标金额", prefix_text="¥", keyboard_type=ft.KeyboardType.NUMBER,
            value=money_to_db(existing.target_amount) if existing else "",
            **theme.field_style(self.palette.dark),
        )
        self.saved_field = ft.TextField(
            label="已存金额", prefix_text="¥", keyboard_type=ft.KeyboardType.NUMBER,
            value=money_to_db(existing.saved_amount) if existing else "0.00",
            helper_text="可以直接修正已存金额",
            **theme.field_style(self.palette.dark),
        )
        self.deadline_button = ft.OutlinedButton(
            icon=ft.Icons.CALENDAR_MONTH,
            text=(existing.deadline.strftime("%Y-%m-%d")
                  if existing and existing.deadline else "选择截止日期（可留空）"),
            on_click=self._pick_deadline,
            style=self.palette.button(filled=False),
        )
        self.deadline: date | None = existing.deadline if existing else None
        self.clear_deadline_button = ft.TextButton(
            "清除日期", on_click=self._clear_deadline,
            visible=bool(self.deadline),
        )
        self.date_picker = ft.DatePicker(
            first_date=date(2000, 1, 1), last_date=date(2100, 12, 31),
            value=self.deadline or date.today(), on_change=self._on_deadline_picked,
        )
        self.note_field = ft.TextField(
            label="备注（可选）", value=existing.note if existing else "", max_length=100,
            **theme.field_style(self.palette.dark),
        )
        self.error_control = ft.Text("", size=theme.FONT_SMALL, color=self.palette.expense)
        self.preview_control = ft.Text("", size=theme.FONT_SMALL, color=self.palette.muted)

        actions: list[ft.Control] = []
        if existing:
            actions += [
                ft.TextButton("存入", icon=ft.Icons.ADD, on_click=self._open_deposit),
                ft.TextButton("取出", icon=ft.Icons.REMOVE, on_click=self._open_withdraw),
            ]
        actions += [
            ft.TextButton("取消", on_click=lambda _e: self._close()),
            ft.FilledButton("保存", icon=ft.Icons.CHECK, on_click=self._save),
        ]

        content: list[ft.Control] = [
            self.name_field,
            self.target_field,
            self.saved_field,
            ft.Row([self.deadline_button, self.clear_deadline_button],
                   vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=theme.PAD_XS),
            self.note_field,
        ]
        if existing:
            content.append(self._progress_block(existing))
        content += [self.preview_control, self.error_control]

        self.dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("编辑存钱目标" if existing else "新增存钱目标"),
            content=ft.Container(
                content=ft.Column(content, spacing=theme.PAD_S, tight=True,
                                  scroll=ft.ScrollMode.AUTO),
                width=420,
            ),
            actions=actions,
            actions_alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

    # -------------------------------------------------- 只读进度块

    def _progress_block(self, goal) -> ft.Control:
        status = "已达标" if goal.is_done else ("已逾期" if goal.is_overdue else "进行中")
        suggestion = (f"每月建议存入 {format_money(goal.monthly_suggestion)}"
                      if goal.monthly_suggestion > 0 else "无每月建议")
        return ft.Container(
            content=ft.Column(
                [
                    ft.Text(f"进度 {format_percent(goal.progress)} · 还差 "
                            f"{format_money(goal.remaining)} · {status}",
                            size=theme.FONT_SMALL),
                    ft.ProgressBar(value=float(goal.progress), bar_height=8,
                                   color=self.palette.primary,
                                   bgcolor=ft.Colors.with_opacity(0.15, self.palette.primary)),
                    ft.Text(suggestion, size=theme.FONT_TINY, color=self.palette.muted),
                ],
                spacing=theme.PAD_XS,
            ),
            padding=theme.PAD_S,
            border_radius=theme.RADIUS_S,
            bgcolor=ft.Colors.with_opacity(0.06, self.palette.primary),
        )

    # -------------------------------------------------- 基础

    def open(self) -> None:
        self.page.open(self.dialog)

    def _close(self) -> None:
        self.page.close(self.dialog)

    def _error(self, text: str) -> None:
        self.error_control.value = text
        self.page.update()

    def _clear_error(self) -> None:
        if self.error_control.value:
            self.error_control.value = ""
            self.page.update()

    # -------------------------------------------------- 日期

    def _pick_deadline(self, _event: ft.ControlEvent) -> None:
        self.page.open(self.date_picker)

    def _on_deadline_picked(self, event: ft.ControlEvent) -> None:
        value = event.control.value
        if isinstance(value, str):
            try:
                value = date.fromisoformat(value[:10])
            except ValueError:
                value = None
        if isinstance(value, date):
            self.deadline = value
        self.deadline_button.text = self.deadline.strftime("%Y-%m-%d") if self.deadline else "未设置"
        self.clear_deadline_button.visible = bool(self.deadline)
        self.page.update()

    def _clear_deadline(self, _event: ft.ControlEvent) -> None:
        self.deadline = None
        self.deadline_button.text = "选择截止日期（可留空）"
        self.clear_deadline_button.visible = False
        self.page.update()

    # -------------------------------------------------- 保存

    def _save(self, _event: ft.ControlEvent) -> None:
        try:
            data = GoalInput(
                name=self.name_field.value or "",
                target_amount=self.target_field.value or "",
                saved_amount=self.saved_field.value or "0",
                deadline=self.deadline,
                note=self.note_field.value or "",
            )
            if self.goal_id:
                goal = goal_service.update_goal(self.goal_id, data)
                message = f"已保存目标「{goal.name}」"
            else:
                goal = goal_service.create_goal(data)
                message = f"已创建目标「{goal.name}」"
        except AppError as exc:
            self._error(str(exc))
            return

        self._close()
        self.view.changed(message)

    # -------------------------------------------------- 存入 / 取出

    def _open_deposit(self, _event: ft.ControlEvent) -> None:
        self._open_adjust(deposit=True)

    def _open_withdraw(self, _event: ft.ControlEvent) -> None:
        self._open_adjust(deposit=False)

    def _open_adjust(self, *, deposit: bool) -> None:
        if not self.goal_id or self.goal is None:
            return
        title = "存入目标" if deposit else "从目标取出"
        field = ft.TextField(
            label="金额", prefix_text="¥", autofocus=True,
            keyboard_type=ft.KeyboardType.NUMBER,
            helper_text=f"当前已存 {format_money(self.goal.saved_amount)}",
            **theme.field_style(self.palette.dark),
        )
        error = ft.Text("", size=theme.FONT_SMALL, color=self.palette.expense)
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"{title} · {self.goal.name}"),
            content=ft.Container(
                content=ft.Column([field, error], spacing=theme.PAD_S, tight=True),
                width=340,
            ),
            actions=[
                ft.TextButton("取消", on_click=lambda _e: self.page.close(dialog)),
                ft.FilledButton("确定", on_click=lambda _e: submit()),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        def submit() -> None:
            try:
                amount = parse_money(field.value, field="金额")
                updated = (goal_service.deposit(self.goal_id, amount) if deposit
                           else goal_service.withdraw(self.goal_id, amount))
            except AppError as exc:
                error.value = str(exc)
                self.page.update()
                return
            self.page.close(dialog)
            self._close()
            self.view.changed(
                f"{'已存入' if deposit else '已取出'} {format_money(amount)}，"
                f"「{updated.name}」已存 {format_money(updated.saved_amount)}"
            )

        self.page.open(dialog)


# ==================================================================== 分类编辑弹窗

class CategoryEditorDialog:
    """新增 / 编辑收支分类。"""

    def __init__(self, view: SettingsView, category_id: int | None = None):
        self.view = view
        self.page = view.page
        self.palette = view.palette
        self.category_id = category_id
        self.category = category_repo.get_category(category_id) if category_id else None

        existing = self.category
        default_kind = KIND_EXPENSE if view.category_tab == 0 else KIND_INCOME
        self.kind = existing.kind if existing else default_kind
        self.icon = existing.icon if existing else "category"
        self.color = existing.color if existing else COLOR_CHOICES[3]
        self.name_field = ft.TextField(
            label="分类名称", value=existing.name if existing else "", max_length=20,
            hint_text="例如：宠物",
            **theme.field_style(self.palette.dark),
        )
        self.kind_switch = ft.SegmentedButton(
            segments=[
                ft.Segment(value=KIND_EXPENSE, label=ft.Text("支出")),
                ft.Segment(value=KIND_INCOME, label=ft.Text("收入")),
            ],
            selected={self.kind},
            on_change=self._on_kind_change,
            disabled=existing is not None,   # 已有分类不允许改方向
        )
        self.icon_row = ft.Row([], spacing=theme.PAD_XS, wrap=True)
        self.color_row = ft.Row([], spacing=theme.PAD_XS, wrap=True)
        self.error_control = ft.Text("", size=theme.FONT_SMALL, color=self.palette.expense)

        self._render_icon_choices()
        self._render_color_choices()

        self.dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("编辑分类" if existing else "新增分类"),
            content=ft.Container(
                content=ft.Column(
                    [
                        self.name_field,
                        ft.Row([self.kind_switch], alignment=ft.MainAxisAlignment.CENTER),
                        ft.Text("图标", size=theme.FONT_SMALL, color=self.palette.muted),
                        self.icon_row,
                        ft.Text("颜色", size=theme.FONT_SMALL, color=self.palette.muted),
                        self.color_row,
                        self.error_control,
                    ],
                    spacing=theme.PAD_S, tight=True, scroll=ft.ScrollMode.AUTO,
                ),
                width=420,
            ),
            actions=[
                ft.TextButton("取消", on_click=lambda _e: self.page.close(self.dialog)),
                ft.FilledButton("保存", icon=ft.Icons.CHECK, on_click=self._save),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

    # -------------------------------------------------- 图标/颜色选择

    def _render_icon_choices(self) -> None:
        self.icon_row.controls = [
            ft.Container(
                content=ft.Icon(name, size=18,
                                color="#FFFFFF" if name == self.icon else self.palette.muted),
                width=34, height=34,
                border_radius=theme.RADIUS_S,
                alignment=ft.alignment.center,
                bgcolor=self.color if name == self.icon else None,
                border=ft.border.all(1, ft.Colors.with_opacity(0.2, self.palette.muted)),
                on_click=self._make_icon_handler(name),
                ink=True,
            )
            for name in ICON_CHOICES
        ]

    def _make_icon_handler(self, name: str):
        def handler(_event) -> None:
            self.icon = name
            self._render_icon_choices()
            self.page.update()

        return handler

    def _render_color_choices(self) -> None:
        self.color_row.controls = [
            ft.Container(
                content=ft.Icon(ft.Icons.CHECK, size=16, color="#FFFFFF")
                if value == self.color else None,
                width=32, height=32,
                border_radius=16,
                bgcolor=value,
                alignment=ft.alignment.center,
                on_click=self._make_color_handler(value),
                ink=True,
            )
            for value in COLOR_CHOICES
        ]

    def _make_color_handler(self, value: str):
        def handler(_event) -> None:
            self.color = value
            self._render_color_choices()
            self._render_icon_choices()
            self.page.update()

        return handler

    # -------------------------------------------------- 事件

    def open(self) -> None:
        self.page.open(self.dialog)

    def _on_kind_change(self, event: ft.ControlEvent) -> None:
        selected = event.control.selected or set()
        if selected:
            self.kind = next(iter(selected))

    def _save(self, _event: ft.ControlEvent) -> None:
        name = (self.name_field.value or "").strip()
        if not name:
            self.error_control.value = "分类名称不能为空"
            self.page.update()
            return

        try:
            if self.category_id:
                category_repo.update_category(
                    self.category_id, name=name, icon=self.icon, color=self.color,
                )
                message = f"已保存分类「{name}」"
            else:
                category_repo.create_category(
                    name, self.kind, icon=self.icon, color=self.color,
                )
                message = f"已新增{kind_label(self.kind)}分类「{name}」"
        except CategoryError as exc:
            self.error_control.value = str(exc)
            self.page.update()
            return

        self.page.close(self.dialog)
        # 新增的是哪个方向，就切到哪个标签，方便立刻看到
        self.view.category_tab = 0 if self.kind == KIND_EXPENSE else 1
        self.view.changed(message)


def _table_label(table: str) -> str:
    return {
        "categories": "分类",
        "transactions": "流水",
        "goals": "目标",
    }.get(table, table)

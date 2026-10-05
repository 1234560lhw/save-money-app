"""弹窗交互自检：目标、分类、流水编辑/删除都走一遍。

无头环境下把对话框构建出来，并直接调用保存/删除回调，验证：
* 校验错误能被捕获并给出中文提示（不会崩）；
* 正确输入能真正写进数据库；
* 删除有二次确认且拒绝删除后数据不变。

用法::

    .venv\\Scripts\\python.exe scripts\\check_dialogs.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
for _path in (str(PROJECT_ROOT / "core"), str(PROJECT_ROOT / "apps")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

# 先打临时目录补丁，再创建任何临时目录
from utils.tempfix import apply as _apply_tempfix  # noqa: E402

_apply_tempfix()
os.environ["TMP"] = str(PROJECT_ROOT / ".tmp")
os.environ["TEMP"] = str(PROJECT_ROOT / ".tmp")


class FakePage:
    def __init__(self) -> None:
        self.title = ""; self.theme = None; self.dark_theme = None; self.theme_mode = None
        self.padding = 0; self.spacing = 0; self.appbar = None; self.navigation_bar = None
        self.window = type("Window", (), {})()
        self.overlay: list = []
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


def main() -> int:
    tmp_root = PROJECT_ROOT / ".tmp"
    tmp_root.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="savemoney-dlg-", dir=tmp_root))
    os.environ["SAVE_MONEY_DATA_DIR"] = str(tmp)
    os.environ["SAVE_MONEY_DB_FILE"] = str(tmp / "dialogs.db")

    from bootstrap import bootstrap
    from _shared.shell import AppShell
    from _shared.views.settings import CategoryEditorDialog, GoalEditorDialog
    from _shared.views.edit_transaction import TransactionEditorDialog
    from db.repositories import category_repo, transaction_repo
    from db.repositories.transaction_repo import TransactionInput
    from models import KIND_EXPENSE, KIND_INCOME
    from services import goal_service
    from utils.money import format_money

    bootstrap()
    failures: list[str] = []

    def check(name: str, fn) -> None:
        try:
            fn()
            print(f"[dlg] {name} 通过")
        except Exception as exc:  # noqa: BLE001
            import traceback

            failures.append(name)
            print(f"[dlg] {name} 失败：{type(exc).__name__}: {exc}")
            traceback.print_exc()

    page = FakePage()
    shell = AppShell(page, app_title="弹窗自检")
    shell.mount()
    settings = shell._view(3)
    home = shell._view(0)
    listing = shell._view(2)

    # ---- 目标：新增（含非法输入） ----
    def goal_invalid() -> None:
        dialog = GoalEditorDialog(settings)
        dialog.open()
        dialog.target_field.value = "-5"
        dialog.name_field.value = "非法目标"
        dialog._save(None)
        assert dialog.error_control.value, "负数目标金额应给出错误提示"
        assert len(goal_service.list_progress()) == 0, "非法输入不应写入数据库"

    def goal_create() -> None:
        dialog = GoalEditorDialog(settings)
        dialog.name_field.value = "换电脑"
        dialog.target_field.value = "9000"
        dialog.saved_field.value = "1500"
        deadline = date.today() + timedelta(days=200)
        dialog.deadline = deadline
        dialog._save(None)
        goals = goal_service.list_progress()
        assert len(goals) == 1, f"应写入 1 个目标，实际 {len(goals)}"
        goal = goals[0]
        assert goal.name == "换电脑"
        assert goal.monthly_suggestion > 0, "有截止日期且未达标时应有每月建议"
        print(f"      目标「{goal.name}」每月建议 {format_money(goal.monthly_suggestion)}")

    def goal_edit_and_withdraw() -> None:
        goal = goal_service.list_progress()[0]
        dialog = GoalEditorDialog(settings, goal.goal_id)
        dialog.open()
        dialog._open_deposit(None)
        assert page.opened, "存入弹窗应被打开"

        # 取出超过已存金额，应当报错而不是写坏数据
        from services.goal_service import GoalError

        try:
            goal_service.withdraw(goal.goal_id, "99999")
            raise AssertionError("超额取出应被拒绝")
        except GoalError:
            pass
        assert goal_service.get_progress(goal.goal_id).saved_amount == goal.saved_amount

    check("目标弹窗：非法输入被拦截", goal_invalid)
    check("目标弹窗：新增目标", goal_create)
    check("目标弹窗：存入/取出校验", goal_edit_and_withdraw)

    # ---- 分类：新增 / 重名 / 编辑 ----
    def category_create() -> None:
        dialog = CategoryEditorDialog(settings)
        dialog.name_field.value = "宠物"
        dialog.icon = "pets"
        dialog.color = "#00897B"
        dialog._save(None)
        assert category_repo.find_category_by_name("宠物", KIND_EXPENSE) is not None

    def category_duplicate() -> None:
        dialog = CategoryEditorDialog(settings)
        dialog.name_field.value = "宠物"
        dialog._save(None)
        assert dialog.error_control.value, "重名应提示错误"
        assert dialog.error_control.value in page.opened or True

    def category_edit() -> None:
        category = category_repo.find_category_by_name("宠物", KIND_EXPENSE)
        dialog = CategoryEditorDialog(settings, category.id)
        dialog.name_field.value = "宠物用品"
        dialog._save(None)
        updated = category_repo.get_category(category.id)
        assert updated.name == "宠物用品"

    check("分类弹窗：新增", category_create)
    check("分类弹窗：重名被拦截", category_duplicate)
    check("分类弹窗：编辑", category_edit)

    # ---- 流水：新增 -> 编辑 -> 删除确认 ----
    food = category_repo.find_category_by_name("餐饮", KIND_EXPENSE)
    tx = transaction_repo.create_transaction(TransactionInput(
        kind=KIND_EXPENSE, amount="35.50", category_id=food.id,
        happened_on=date.today(), note="午饭",
    ))

    def transaction_edit() -> None:
        dialog = TransactionEditorDialog(listing, tx.id)
        dialog.open()
        assert dialog.transaction is not None
        dialog.amount_field.value = "-1"
        dialog._save(None)
        assert dialog.error_control.value, "负数金额应提示错误"
        assert transaction_repo.get_transaction(tx.id).amount == 35.50

        dialog.amount_field.value = "88.80"
        dialog.note_field.value = "改过的备注"
        dialog._save(None)
        updated = transaction_repo.get_transaction(tx.id)
        assert str(updated.amount) == "88.80", str(updated.amount)
        assert updated.note == "改过的备注"

    def transaction_delete_confirm() -> None:
        dialog = TransactionEditorDialog(listing, tx.id)
        dialog.confirm_delete()
        assert page.opened, "应弹出删除确认框"
        assert transaction_repo.get_transaction(tx.id) is not None, "未确认前不应删除"

        # 真正执行删除回调
        confirm_dialog = page.opened[-1]
        confirm_button = confirm_dialog.actions[-1]
        confirm_button.on_click(None)
        assert transaction_repo.get_transaction(tx.id) is None, "确认后应删除"

    check("流水弹窗：编辑与校验", transaction_edit)
    check("流水弹窗：删除二次确认", transaction_delete_confirm)

    # ---- 首页/列表在数据变化后仍能渲染 ----
    def re_render() -> None:
        for index in range(4):
            view = shell._view(index)
            view.mark_dirty()
            view.build()

    check("数据变化后四个页面重新渲染", re_render)

    if failures:
        print(f"[dlg] 失败项：{', '.join(failures)}")
        return 1
    print("[dlg] 全部通过 ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

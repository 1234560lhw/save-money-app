"""第一步测试 3/3：存钱目标公式。

覆盖：
* 剩余月数 ``months_left`` 的边界（无期限 / 今天到期 / 过期 / 不足一月）；
* 每月建议存入 ``monthly_suggestion`` 的取整方向（向上取整到分）；
* 目标进度、差额、达标与逾期判定；
* 目标 CRUD 与存入/取出。
"""

from __future__ import annotations

import unittest
from datetime import date, timedelta
from decimal import Decimal

from conftest import DatabaseTestCase

from db.repositories import goal_repo
from services import goal_service
from services.goal_service import GoalInput


class TestMonthsLeft(unittest.TestCase):
    """纯公式测试，不碰数据库。"""

    TODAY = date(2025, 3, 10)

    def test_no_deadline(self):
        self.assertIsNone(goal_service.months_left(None, self.TODAY))

    def test_deadline_today(self):
        self.assertEqual(goal_service.months_left(self.TODAY, self.TODAY), 0)

    def test_deadline_passed(self):
        self.assertEqual(goal_service.months_left(date(2025, 1, 1), self.TODAY), 0)

    def test_deadline_this_month_later_day(self):
        """3/10 -> 3/20：不足一月，按 1 个月算，避免除零。"""
        self.assertEqual(goal_service.months_left(date(2025, 3, 20), self.TODAY), 1)

    def test_deadline_next_month_earlier_day(self):
        """3/10 -> 4/5：到 4 月不足整月，按 4 个月差 + 天数补偿 -> 1 个月。"""
        self.assertEqual(goal_service.months_left(date(2025, 4, 5), self.TODAY), 1)

    def test_deadline_next_month_later_day(self):
        """3/10 -> 4/20：约 1 个月零 10 天 -> 2 个月。"""
        self.assertEqual(goal_service.months_left(date(2025, 4, 20), self.TODAY), 2)

    def test_five_months(self):
        self.assertEqual(goal_service.months_left(date(2025, 8, 5), self.TODAY), 5)

    def test_cross_year(self):
        self.assertEqual(goal_service.months_left(date(2026, 3, 10), self.TODAY), 12)


class TestMonthlySuggestion(unittest.TestCase):

    def test_even_division(self):
        """12000 目标、已存 2000、5 个月 -> 2000/月。"""
        value = goal_service.monthly_suggestion(
            Decimal("12000"), Decimal("2000"), date(2025, 8, 5), today=date(2025, 3, 10),
        )
        self.assertEqual(value, Decimal("2000.00"))

    def test_rounds_up_to_cent(self):
        """10000 / 3 = 3333.333... -> 向上取整 3333.34，保证存够。"""
        value = goal_service.monthly_suggestion(
            Decimal("10000"), Decimal("0"), date(2025, 6, 10), today=date(2025, 3, 10),
        )
        self.assertEqual(value, Decimal("3333.34"))
        self.assertGreaterEqual(value * 3, Decimal("10000"))

    def test_no_deadline_returns_zero(self):
        value = goal_service.monthly_suggestion(
            Decimal("5000"), Decimal("1000"), None, today=date(2025, 3, 10),
        )
        self.assertEqual(value, Decimal("0"))

    def test_already_reached_returns_zero(self):
        value = goal_service.monthly_suggestion(
            Decimal("5000"), Decimal("5000"), date(2025, 8, 1), today=date(2025, 3, 10),
        )
        self.assertEqual(value, Decimal("0"))

    def test_over_reached_returns_zero(self):
        value = goal_service.monthly_suggestion(
            Decimal("5000"), Decimal("8000"), date(2025, 8, 1), today=date(2025, 3, 10),
        )
        self.assertEqual(value, Decimal("0"))

    def test_overdue_returns_full_remaining(self):
        """已过期：需要立刻补上全部差额。"""
        value = goal_service.monthly_suggestion(
            Decimal("5000"), Decimal("1000"), date(2025, 1, 1), today=date(2025, 3, 10),
        )
        self.assertEqual(value, Decimal("4000.00"))

    def test_single_month(self):
        value = goal_service.monthly_suggestion(
            Decimal("800"), Decimal("0"), date(2025, 3, 20), today=date(2025, 3, 10),
        )
        self.assertEqual(value, Decimal("800.00"))


class TestGoalCrud(DatabaseTestCase):

    def test_create_goal(self):
        goal = goal_service.create_goal(GoalInput(
            name="买电脑", target_amount="8000", saved_amount="1000",
            deadline=date(2030, 1, 1), note="攒钱换机",
        ))
        self.assertGreater(goal.goal_id, 0)
        self.assertEqual(goal.name, "买电脑")
        self.assertMoney(goal.target_amount, "8000.00")
        self.assertMoney(goal.saved_amount, "1000.00")
        self.assertMoney(goal.remaining, "7000.00")
        self.assertEqual(goal.deadline, date(2030, 1, 1))

    def test_default_saved_is_zero(self):
        goal = goal_service.create_goal(GoalInput(name="旅游", target_amount="3000"))
        self.assertMoney(goal.saved_amount, "0.00")
        self.assertIsNone(goal.deadline)
        self.assertMoney(goal.monthly_suggestion, "0.00")

    def test_goal_without_deadline_has_no_suggestion(self):
        goal = goal_service.create_goal(GoalInput(name="应急金", target_amount="20000"))
        self.assertIsNone(goal.months_left)
        self.assertMoney(goal.monthly_suggestion, "0.00")

    def test_reject_empty_name(self):
        with self.assertRaises(goal_repo.GoalError):
            goal_service.create_goal(GoalInput(name="  ", target_amount="100"))

    def test_reject_zero_or_negative_target(self):
        for bad in ("0", "-100"):
            with self.assertRaises(goal_repo.GoalError):
                goal_service.create_goal(GoalInput(name="测试", target_amount=bad))

    def test_reject_non_numeric_target(self):
        with self.assertRaises(goal_repo.GoalError):
            goal_service.create_goal(GoalInput(name="测试", target_amount="很多钱"))

    def test_reject_bad_deadline(self):
        with self.assertRaises(goal_repo.GoalError):
            goal_service.create_goal(GoalInput(
                name="测试", target_amount="100", deadline="2025-13-99",
            ))

    def test_update_goal(self):
        goal = goal_service.create_goal(GoalInput(name="买车", target_amount="100000"))
        updated = goal_service.update_goal(goal.goal_id, GoalInput(
            name="买车（二手）", target_amount="60000", saved_amount="5000",
        ))
        self.assertEqual(updated.name, "买车（二手）")
        self.assertMoney(updated.target_amount, "60000.00")
        self.assertMoney(updated.saved_amount, "5000.00")

    def test_update_missing_goal(self):
        with self.assertRaises(goal_repo.GoalError):
            goal_service.update_goal(9999, GoalInput(name="x", target_amount="1"))

    def test_delete_goal(self):
        goal = goal_service.create_goal(GoalInput(name="临时", target_amount="100"))
        self.assertTrue(goal_service.delete_goal(goal.goal_id))
        self.assertIsNone(goal_service.get_progress(goal.goal_id))
        self.assertFalse(goal_service.delete_goal(goal.goal_id))

    def test_list_order_active_first(self):
        goal_service.create_goal(GoalInput(
            name="有期限近", target_amount="1000", deadline=date(2030, 1, 1)))
        goal_service.create_goal(GoalInput(
            name="有期限远", target_amount="1000", deadline=date(2035, 1, 1)))
        goal_service.create_goal(GoalInput(name="无期限", target_amount="1000"))
        names = [g.name for g in goal_service.list_progress()]
        self.assertEqual(names[-1], "无期限")
        self.assertEqual(names[0], "有期限近")


class TestGoalProgress(DatabaseTestCase):

    def test_progress_ratio(self):
        goal = goal_service.create_goal(GoalInput(
            name="目标", target_amount="10000", saved_amount="2500"))
        self.assertEqual(goal.progress, Decimal("0.25"))
        self.assertEqual(goal.progress_percent, Decimal("25.00"))

    def test_progress_capped_at_one(self):
        goal = goal_service.create_goal(GoalInput(
            name="超额", target_amount="1000", saved_amount="1500"))
        self.assertEqual(goal.progress, Decimal("1"))
        self.assertMoney(goal.remaining, "0.00")
        self.assertTrue(goal.is_done)

    def test_deposit_and_withdraw(self):
        goal = goal_service.create_goal(GoalInput(name="目标", target_amount="1000"))
        after = goal_service.deposit(goal.goal_id, "300")
        self.assertMoney(after.saved_amount, "300.00")
        after = goal_service.deposit(goal.goal_id, "200.50")
        self.assertMoney(after.saved_amount, "500.50")
        after = goal_service.withdraw(goal.goal_id, "100.50")
        self.assertMoney(after.saved_amount, "400.00")

    def test_withdraw_more_than_saved_rejected(self):
        goal = goal_service.create_goal(GoalInput(
            name="目标", target_amount="1000", saved_amount="100"))
        with self.assertRaises(goal_repo.GoalError) as ctx:
            goal_service.withdraw(goal.goal_id, "500")
        self.assertIn("超过已存金额", str(ctx.exception))
        self.assertMoney(goal_service.get_progress(goal.goal_id).saved_amount, "100.00")

    def test_deposit_marks_done(self):
        goal = goal_service.create_goal(GoalInput(
            name="目标", target_amount="1000", saved_amount="900"))
        after = goal_service.deposit(goal.goal_id, "100")
        self.assertTrue(after.is_done)
        self.assertEqual(after.progress, Decimal("1"))

    def test_monthly_suggestion_in_progress(self):
        """今天起 6 个月后到期，目标 6000，已存 600 -> 每月 900。"""
        deadline = date.today() + timedelta(days=183)
        goal = goal_service.create_goal(GoalInput(
            name="半年计划", target_amount="6000", saved_amount="600", deadline=deadline))
        self.assertIsNotNone(goal.months_left)
        expected = (Decimal("5400") / goal.months_left).quantize(Decimal("0.01"),
                                                               rounding="ROUND_CEILING")
        self.assertEqual(goal.monthly_suggestion, expected)

    def test_overdue_flag(self):
        goal = goal_service.create_goal(GoalInput(
            name="过期目标", target_amount="1000",
            deadline=date.today() - timedelta(days=10)))
        self.assertTrue(goal.is_overdue)
        self.assertFalse(goal.is_done)

    def test_finished_goal_is_not_overdue(self):
        goal = goal_service.create_goal(GoalInput(
            name="已完成", target_amount="1000", saved_amount="1000",
            deadline=date.today() - timedelta(days=10)))
        self.assertTrue(goal.is_done)
        self.assertFalse(goal.is_overdue)

    def test_days_left(self):
        goal = goal_service.create_goal(GoalInput(
            name="目标", target_amount="1000",
            deadline=date.today() + timedelta(days=30)))
        self.assertEqual(goal.days_left, 30)

    def test_archived_hidden_by_default(self):
        goal = goal_service.create_goal(GoalInput(name="归档", target_amount="100"))
        goal_repo.set_status(goal.goal_id, "archived")
        self.assertEqual(len(goal_service.list_progress()), 0)
        self.assertEqual(len(goal_service.list_progress(include_archived=True)), 1)

    def test_totals(self):
        goal_service.create_goal(GoalInput(name="A", target_amount="1000", saved_amount="200"))
        goal_service.create_goal(GoalInput(name="B", target_amount="500", saved_amount="300"))
        self.assertMoney(goal_service.total_target(), "1500.00")
        self.assertMoney(goal_service.total_saved(), "500.00")


class TestBackupService(DatabaseTestCase):

    def test_export_and_import_roundtrip(self):
        from db.repositories import category_repo, transaction_repo
        from db.repositories.transaction_repo import TransactionInput
        from models import KIND_EXPENSE
        from services import backup_service

        food = category_repo.find_category_by_name("餐饮", KIND_EXPENSE)
        transaction_repo.create_transaction(TransactionInput(
            kind=KIND_EXPENSE, amount="66.60", category_id=food.id,
            happened_on="2025-05-01", note="备份前",
        ))
        goal_service.create_goal(GoalInput(name="备份目标", target_amount="2000",
                                           saved_amount="500", deadline="2030-01-01"))

        backup_file = backup_service.export_database(self.tmp / "backup.db")
        self.assertTrue(backup_file.is_file())

        # 再插一笔，然后导入备份，应当回到只有 1 笔的状态
        transaction_repo.create_transaction(TransactionInput(
            kind=KIND_EXPENSE, amount="1", category_id=food.id, happened_on="2025-05-02",
        ))
        self.assertEqual(transaction_repo.count_transactions(), 2)

        result = backup_service.import_database(backup_file)
        self.assertTrue(result.ok, result.message)
        self.assertEqual(transaction_repo.count_transactions(), 1)
        goal = goal_service.list_progress()[0]
        self.assertEqual(goal.name, "备份目标")
        self.assertMoney(goal.saved_amount, "500.00")

    def test_inspect_rejects_non_backup(self):
        from services import backup_service
        junk = self.tmp / "junk.db"
        with junk.open("wb") as fh:          # 显式关闭，避免 Windows 文件占用
            fh.write(b"this is not a database")
        check = backup_service.inspect_database(junk)
        self.assertFalse(check["ok"])
        self.assertTrue(check["message"])

    def test_inspect_missing_file(self):
        from services import backup_service
        self.assertFalse(backup_service.inspect_database(self.tmp / "nope.db")["ok"])

    def test_csv_export_has_bom_and_rows(self):
        from db.repositories import category_repo, transaction_repo
        from db.repositories.transaction_repo import TransactionInput
        from models import KIND_EXPENSE
        from services import backup_service

        food = category_repo.find_category_by_name("餐饮", KIND_EXPENSE)
        transaction_repo.create_transaction(TransactionInput(
            kind=KIND_EXPENSE, amount="12.34", category_id=food.id,
            happened_on="2025-06-01", note="CSV测试",
        ))
        csv_file = backup_service.export_transactions_csv()
        raw = csv_file.read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"), "CSV 需要 UTF-8 BOM 以便 Excel 打开")
        text = raw.decode("utf-8-sig")
        self.assertIn("日期,类型,金额,分类,备注,录入时间", text)
        self.assertIn("12.34", text)
        self.assertIn("CSV测试", text)


class TestSettingsService(DatabaseTestCase):

    def test_defaults_and_write(self):
        from services import settings_service

        # 默认深色：毛玻璃质感在深色下最明显（见 theme.Palette）
        self.assertEqual(settings_service.get_value(settings_service.KEY_THEME_MODE), "dark")
        settings_service.set_value(settings_service.KEY_THEME_MODE, "light")
        self.assertEqual(settings_service.get_value(settings_service.KEY_THEME_MODE), "light")
        settings_service.set_value(settings_service.KEY_THEME_MODE, "dark")
        self.assertEqual(settings_service.get_value(settings_service.KEY_THEME_MODE), "dark")

    def test_int_and_backup_time(self):
        from services import settings_service

        self.assertEqual(settings_service.get_int(settings_service.KEY_WEEK_START, 1), 1)
        self.assertIsNone(settings_service.last_backup_at())
        settings_service.touch_backup_time()
        self.assertIsNotNone(settings_service.last_backup_at())


if __name__ == "__main__":
    unittest.main(verbosity=2)

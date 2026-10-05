"""第一步测试 2/3：统计口径与储蓄率公式。

重点验证：
* 总存款 = 收入合计 − 支出合计；
* 本月结余 = 本月收入 − 本月支出；
* 储蓄率 = 结余 ÷ 收入，收入为 0 时返回 None（而不是 0）；
* 分类占比与月度趋势正确。
"""

from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal

from conftest import DatabaseTestCase

from db.repositories import category_repo, transaction_repo
from db.repositories.transaction_repo import TransactionInput
from models import KIND_EXPENSE, KIND_INCOME
from services import stats_service


class StatsBase(DatabaseTestCase):

    def setUp(self):
        super().setUp()
        self.salary = category_repo.find_category_by_name("工资", KIND_INCOME)
        self.food = category_repo.find_category_by_name("餐饮", KIND_EXPENSE)
        self.traffic = category_repo.find_category_by_name("交通", KIND_EXPENSE)

    def add(self, kind, amount, category_id, day, note=""):
        return transaction_repo.create_transaction(TransactionInput(
            kind=kind, amount=amount, category_id=category_id,
            happened_on=day, note=note,
        ))


class TestTotals(StatsBase):

    def test_empty_database(self):
        self.assertMoney(stats_service.total_balance(), "0.00")
        self.assertMoney(stats_service.total_income(), "0.00")
        self.assertMoney(stats_service.total_expense(), "0.00")
        self.assertEqual(stats_service.total_count(), 0)

    def test_total_balance_is_income_minus_expense(self):
        self.add(KIND_INCOME, "8000", self.salary.id, "2025-01-05")
        self.add(KIND_INCOME, "500", self.salary.id, "2025-02-05")
        self.add(KIND_EXPENSE, "1200.50", self.food.id, "2025-01-06")
        self.add(KIND_EXPENSE, "80", self.traffic.id, "2025-02-07")

        self.assertMoney(stats_service.total_income(), "8500.00")
        self.assertMoney(stats_service.total_expense(), "1280.50")
        self.assertMoney(stats_service.total_balance(), "7219.50")

    def test_total_balance_counts_all_months(self):
        """总存款是"所有收入减支出"，不限于本月。"""
        self.add(KIND_INCOME, "1000", self.salary.id, "2020-01-01")
        self.add(KIND_EXPENSE, "250", self.food.id, "2030-12-31")
        self.assertMoney(stats_service.total_balance(), "750.00")

    def test_decimal_precision_not_float(self):
        """0.1 + 0.2 类问题：25 笔 0.07 元必须精确等于 1.75。"""
        for _ in range(25):
            self.add(KIND_EXPENSE, "0.07", self.food.id, "2025-03-01")
        self.assertMoney(stats_service.total_expense(), "1.75")


class TestMonthlySummary(StatsBase):

    def setUp(self):
        super().setUp()
        self.add(KIND_INCOME, "10000", self.salary.id, "2025-03-05")
        self.add(KIND_EXPENSE, "2500", self.food.id, "2025-03-06")
        self.add(KIND_EXPENSE, "500", self.traffic.id, "2025-03-07")
        self.add(KIND_INCOME, "9000", self.salary.id, "2025-04-05")

    def test_month_income_expense_balance(self):
        summary = stats_service.monthly_summary(2025, 3)
        self.assertMoney(summary.income, "10000.00")
        self.assertMoney(summary.expense, "3000.00")
        self.assertMoney(summary.balance, "7000.00")

    def test_savings_rate_formula(self):
        """储蓄率 = 结余 / 收入 = 7000 / 10000 = 70%。"""
        summary = stats_service.monthly_summary(2025, 3)
        self.assertEqual(summary.savings_rate, Decimal("0.7"))
        self.assertEqual(stats_service.savings_rate(2025, 3), Decimal("0.7"))

    def test_negative_savings_rate_when_overspending(self):
        self.add(KIND_EXPENSE, "9000", self.food.id, "2025-05-01")
        summary = stats_service.monthly_summary(2025, 5)
        self.assertMoney(summary.balance, "-9000.00")
        self.assertIsNone(summary.savings_rate, "没有收入时储蓄率无法计算")

    def test_rate_none_when_no_income(self):
        summary = stats_service.monthly_summary(2025, 6)
        self.assertMoney(summary.income, "0.00")
        self.assertIsNone(summary.savings_rate)
        self.assertIsNone(summary.expense_ratio)

    def test_rate_is_negative_when_income_but_overspend(self):
        self.add(KIND_INCOME, "100", self.salary.id, "2025-07-01")
        self.add(KIND_EXPENSE, "300", self.food.id, "2025-07-02")
        summary = stats_service.monthly_summary(2025, 7)
        self.assertEqual(summary.savings_rate, Decimal("-2"))

    def test_month_label(self):
        self.assertEqual(stats_service.monthly_summary(2025, 3).label, "2025年3月")

    def test_other_month_unaffected(self):
        summary = stats_service.monthly_summary(2025, 4)
        self.assertMoney(summary.expense, "0.00")
        self.assertMoney(summary.income, "9000.00")


class TestCategoryBreakdown(StatsBase):

    def setUp(self):
        super().setUp()
        self.add(KIND_EXPENSE, "600", self.food.id, "2025-03-01")
        self.add(KIND_EXPENSE, "300", self.food.id, "2025-03-02")
        self.add(KIND_EXPENSE, "100", self.traffic.id, "2025-03-03")
        self.add(KIND_INCOME, "5000", self.salary.id, "2025-03-05")

    def test_grouped_and_sorted(self):
        stats = stats_service.category_breakdown(2025, 3, KIND_EXPENSE)
        self.assertEqual([s.name for s in stats], ["餐饮", "交通"])
        self.assertMoney(stats[0].amount, "900.00")
        self.assertMoney(stats[1].amount, "100.00")

    def test_share_ratio(self):
        stats = stats_service.category_breakdown(2025, 3, KIND_EXPENSE)
        self.assertEqual(stats[0].share, Decimal("0.9"))
        self.assertEqual(stats[1].share, Decimal("0.1"))

    def test_income_breakdown(self):
        stats = stats_service.category_breakdown(2025, 3, KIND_INCOME)
        self.assertEqual(len(stats), 1)
        self.assertEqual(stats[0].name, "工资")

    def test_limit(self):
        stats = stats_service.category_breakdown(2025, 3, KIND_EXPENSE, limit=1)
        self.assertEqual(len(stats), 1)
        self.assertEqual(stats[0].name, "餐饮")

    def test_bad_kind_rejected(self):
        with self.assertRaises(ValueError):
            stats_service.category_breakdown(2025, 3, "transfer")


class TestMonthHelpers(StatsBase):

    def test_shift_month_forward(self):
        self.assertEqual(stats_service.shift_month(2025, 12, 1), (2026, 1))

    def test_shift_month_backward(self):
        self.assertEqual(stats_service.shift_month(2025, 1, -1), (2024, 12))

    def test_shift_month_across_years(self):
        self.assertEqual(stats_service.shift_month(2025, 3, -15), (2023, 12))

    def test_month_range(self):
        self.assertEqual(
            stats_service.month_range(2025, 2),
            (date(2025, 2, 1), date(2025, 2, 28)),
        )
        self.assertEqual(
            stats_service.month_range(2024, 2),
            (date(2024, 2, 1), date(2024, 2, 29)),
        )

    def test_month_range_december(self):
        self.assertEqual(
            stats_service.month_range(2025, 12),
            (date(2025, 12, 1), date(2025, 12, 31)),
        )


class TestTrends(StatsBase):

    def setUp(self):
        super().setUp()
        self.add(KIND_INCOME, "1000", self.salary.id, "2025-01-10")
        self.add(KIND_EXPENSE, "400", self.food.id, "2025-01-11")
        self.add(KIND_INCOME, "1000", self.salary.id, "2025-02-10")
        self.add(KIND_EXPENSE, "600", self.food.id, "2025-02-11")
        self.add(KIND_INCOME, "1000", self.salary.id, "2025-03-10")

    def test_monthly_trend_length_and_order(self):
        points = stats_service.monthly_trend(3, end=(2025, 3))
        self.assertEqual([(p.year, p.month) for p in points],
                         [(2025, 1), (2025, 2), (2025, 3)])

    def test_monthly_trend_values(self):
        points = stats_service.monthly_trend(3, end=(2025, 3))
        self.assertMoney(points[0].balance, "600.00")
        self.assertMoney(points[1].balance, "400.00")
        self.assertMoney(points[2].balance, "1000.00")

    def test_trend_includes_empty_months(self):
        points = stats_service.monthly_trend(5, end=(2025, 5))
        self.assertEqual(len(points), 5)
        self.assertMoney(points[-1].income, "0.00")

    def test_cumulative_savings_trend(self):
        series = stats_service.cumulative_savings_trend(3, end=(2025, 3))
        values = [value for _, value in series]
        self.assertMoney(values[0], "600.00")
        self.assertMoney(values[1], "1000.00")
        self.assertMoney(values[2], "2000.00")

    def test_cumulative_includes_history_before_window(self):
        self.add(KIND_INCOME, "5000", self.salary.id, "2024-12-01")
        series = stats_service.cumulative_savings_trend(3, end=(2025, 3))
        self.assertMoney(series[0][1], "5600.00")

    def test_zero_months(self):
        self.assertEqual(stats_service.monthly_trend(0), [])


class TestDashboardSnapshot(StatsBase):

    def test_snapshot_keys(self):
        self.add(KIND_INCOME, "3000", self.salary.id, date.today().isoformat())
        snapshot = stats_service.dashboard_snapshot()
        for key in ("total_balance", "month", "savings_rate", "top_expense", "goals"):
            self.assertIn(key, snapshot)
        self.assertMoney(snapshot["total_balance"], "3000.00")
        self.assertEqual(snapshot["savings_rate"], Decimal("1"))


if __name__ == "__main__":
    unittest.main(verbosity=2)

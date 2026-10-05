"""初始财产 与 图表数据 的测试。

覆盖用户明确提出的三件事：

1. 第一次使用可以录入"初始财产"，并计入总存款；
2. 可以把初始财产归 0，也可以把全部数据清 0；
3. 流水页的两张图（曲线图看趋势、饼图看构成）所依赖的数据，
   必须**随着流水变化实时更新**——这里就把"变化后数据立刻不同"锁住。
"""

from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal

from conftest import DatabaseTestCase

import flet as ft

from db.repositories import category_repo, transaction_repo
from db.repositories.transaction_repo import TransactionInput
from models import KIND_EXPENSE, KIND_INCOME
from services import backup_service, settings_service, stats_service


class TestStartingBalance(DatabaseTestCase):
    """初始财产：默认 0、可读写、计入总存款。"""

    def test_default_is_zero(self):
        self.assertMoney(settings_service.get_starting_balance(), "0.00")
        self.assertIsNone(settings_service.starting_balance_set_at())

    def test_default_does_not_change_existing_behaviour(self):
        """没设置过初始财产时，总存款仍旧只是"收入 − 支出"。"""
        salary = category_repo.find_category_by_name("工资", KIND_INCOME)
        transaction_repo.create_transaction(TransactionInput(
            kind=KIND_INCOME, amount="3000", category_id=salary.id,
            happened_on="2025-05-01",
        ))
        self.assertMoney(stats_service.total_balance(), "3000.00")
        self.assertMoney(stats_service.transaction_net(), "3000.00")
        self.assertMoney(stats_service.starting_balance(), "0.00")

    def test_set_and_read(self):
        amount = settings_service.set_starting_balance("12000.5")
        self.assertMoney(amount, "12000.50")
        self.assertMoney(settings_service.get_starting_balance(), "12000.50")
        self.assertIsNotNone(settings_service.starting_balance_set_at())

    def test_counts_into_total_balance(self):
        salary = category_repo.find_category_by_name("工资", KIND_INCOME)
        food = category_repo.find_category_by_name("餐饮", KIND_EXPENSE)
        transaction_repo.create_transaction(TransactionInput(
            kind=KIND_INCOME, amount="5000", category_id=salary.id, happened_on="2025-05-10"))
        transaction_repo.create_transaction(TransactionInput(
            kind=KIND_EXPENSE, amount="1200", category_id=food.id, happened_on="2025-05-11"))

        settings_service.set_starting_balance("20000")
        # 20000（初始） + 5000 − 1200 = 23800
        self.assertMoney(stats_service.total_balance(), "23800.00")
        self.assertMoney(stats_service.starting_balance(), "20000.00")
        self.assertMoney(stats_service.transaction_net(), "3800.00")

    def test_allows_negative(self):
        """有欠款时初始财产可以是负数。"""
        settings_service.set_starting_balance("-3500.25")
        self.assertMoney(settings_service.get_starting_balance(), "-3500.25")
        self.assertMoney(stats_service.total_balance(), "-3500.25")

    def test_clear_to_zero(self):
        settings_service.set_starting_balance("8888")
        settings_service.clear_starting_balance()
        self.assertMoney(settings_service.get_starting_balance(), "0.00")
        self.assertMoney(stats_service.total_balance(), "0.00")

    def test_empty_string_means_zero(self):
        settings_service.set_starting_balance("500")
        amount = settings_service.set_starting_balance("")
        self.assertMoney(amount, "0.00")
        settings_service.set_starting_balance(None)   # 也不应报错
        self.assertMoney(settings_service.get_starting_balance(), "0.00")

    def test_rejects_garbage(self):
        with self.assertRaises(ValueError):
            settings_service.set_starting_balance("很多钱")

    def test_quantized_to_cents(self):
        settings_service.set_starting_balance("100.005")
        self.assertMoney(settings_service.get_starting_balance(), "100.01")

    def test_survives_amount_with_separators(self):
        settings_service.set_starting_balance("1,234.50")
        self.assertMoney(settings_service.get_starting_balance(), "1234.50")


class TestResetZeroesEverything(DatabaseTestCase):
    """「全部归 0」：清空数据后总存款必须是 0。"""

    def test_reset_clears_transactions_and_starting_balance(self):
        from services.goal_service import GoalInput
        from services import goal_service

        salary = category_repo.find_category_by_name("工资", KIND_INCOME)
        transaction_repo.create_transaction(TransactionInput(
            kind=KIND_INCOME, amount="9000", category_id=salary.id, happened_on="2025-06-01"))
        settings_service.set_starting_balance("5000")
        goal_service.create_goal(GoalInput(name="测试目标", target_amount="1000"))

        self.assertMoney(stats_service.total_balance(), "14000.00")

        result = backup_service.reset_all_data()

        self.assertMoney(stats_service.total_balance(), "0.00")
        self.assertMoney(settings_service.get_starting_balance(), "0.00")
        self.assertMoney(stats_service.transaction_net(), "0.00")
        self.assertEqual(transaction_repo.count_transactions(), 0)
        self.assertEqual(len(goal_service.list_progress()), 0)
        # 预置分类要保留，否则应用就没法用了
        self.assertGreaterEqual(result.get("categories_kept", 0), 10)

    def test_reset_keeps_app_usable(self):
        """清空后还能正常记一笔，总存款随之变化。"""
        backup_service.reset_all_data()
        salary = category_repo.find_category_by_name("工资", KIND_INCOME)
        transaction_repo.create_transaction(TransactionInput(
            kind=KIND_INCOME, amount="100", category_id=salary.id, happened_on=date.today()))
        self.assertMoney(stats_service.total_balance(), "100.00")


class TestChartData(DatabaseTestCase):
    """两张图依赖的数据：随流水实时变化。"""

    def setUp(self):
        super().setUp()
        self.salary = category_repo.find_category_by_name("工资", KIND_INCOME)
        self.food = category_repo.find_category_by_name("餐饮", KIND_EXPENSE)
        self.traffic = category_repo.find_category_by_name("交通", KIND_EXPENSE)

    def _add(self, kind, amount, category, day):
        return transaction_repo.create_transaction(TransactionInput(
            kind=kind, amount=amount, category_id=category.id,
            happened_on=date(2025, 7, day),
        ))

    # ---- 曲线图 ----

    def test_daily_series_covers_whole_month(self):
        series = stats_service.daily_balance_series(2025, 7)
        self.assertEqual(len(series), 31, "7 月应当有 31 个点")
        self.assertEqual(series[0][0], 1)
        self.assertEqual(series[-1][0], 31)

    def test_daily_series_starts_from_starting_balance(self):
        settings_service.set_starting_balance("10000")
        series = stats_service.daily_balance_series(2025, 7)
        self.assertMoney(series[0][1], "10000.00", "月初起点应当是初始财产")

    def test_daily_series_accumulates(self):
        settings_service.set_starting_balance("1000")
        self._add(KIND_INCOME, "500", self.salary, 5)
        self._add(KIND_EXPENSE, "200", self.food, 10)
        series = dict(stats_service.daily_balance_series(2025, 7))
        self.assertMoney(series[1], "1000.00", "还没有流水的日子与起点相同")
        self.assertMoney(series[5], "1500.00")
        self.assertMoney(series[9], "1500.00", "没有流水的日子沿用前一天")
        self.assertMoney(series[10], "1300.00")
        self.assertMoney(series[31], "1300.00")

    def test_daily_series_includes_history_before_this_month(self):
        self._add(KIND_INCOME, "5000", self.salary, 1)
        settings_service.set_starting_balance("0")
        # 看 8 月时，月初起点应当含 7 月的 5000
        series = stats_service.daily_balance_series(2025, 8)
        self.assertMoney(series[0][1], "5000.00")

    def test_daily_series_updates_after_new_transaction(self):
        """核心诉求：记一笔之后曲线数据必须立刻变。"""
        before = dict(stats_service.daily_balance_series(2025, 7))
        self._add(KIND_INCOME, "888", self.salary, 15)
        after = dict(stats_service.daily_balance_series(2025, 7))
        self.assertNotEqual(before[15], after[15])
        self.assertMoney(after[15] - before[15], "888.00")

    def test_daily_series_updates_after_delete(self):
        tx = self._add(KIND_INCOME, "300", self.salary, 20)
        self.assertMoney(dict(stats_service.daily_balance_series(2025, 7))[20], "300.00")
        transaction_repo.delete_transaction(tx.id)
        self.assertMoney(dict(stats_service.daily_balance_series(2025, 7))[20], "0.00")

    def test_daily_series_empty_month_is_flat(self):
        series = stats_service.daily_balance_series(2025, 9)
        self.assertEqual(len(series), 30)
        self.assertEqual(len({value for _, value in series}), 1, "没有流水时应当是一条平线")

    # ---- 饼图 ----

    def test_category_breakdown_expense(self):
        self._add(KIND_EXPENSE, "600", self.food, 3)
        self._add(KIND_EXPENSE, "200", self.food, 4)
        self._add(KIND_EXPENSE, "200", self.traffic, 5)
        stats = stats_service.category_breakdown(2025, 7, KIND_EXPENSE)
        self.assertEqual([s.name for s in stats], ["餐饮", "交通"])
        self.assertMoney(stats[0].amount, "800.00")
        self.assertEqual(stats[0].share, Decimal("0.8"))
        self.assertEqual(stats[1].share, Decimal("0.2"))

    def test_category_breakdown_income(self):
        self._add(KIND_INCOME, "9000", self.salary, 6)
        stats = stats_service.category_breakdown(2025, 7, KIND_INCOME)
        self.assertEqual(len(stats), 1)
        self.assertEqual(stats[0].name, "工资")

    def test_category_breakdown_updates_after_new_transaction(self):
        """核心诉求：记一笔之后饼图数据必须立刻变。"""
        self._add(KIND_EXPENSE, "100", self.food, 3)
        before = stats_service.category_breakdown(2025, 7, KIND_EXPENSE)
        self._add(KIND_EXPENSE, "300", self.traffic, 4)
        after = stats_service.category_breakdown(2025, 7, KIND_EXPENSE)
        self.assertEqual(len(before), 1)
        self.assertEqual(len(after), 2, "新增分类后饼图应当多一个扇区")
        shares = {s.name: s.share for s in after}
        self.assertEqual(shares["餐饮"], Decimal("0.25"))
        self.assertEqual(shares["交通"], Decimal("0.75"))

    def test_pie_shares_sum_to_one(self):
        self._add(KIND_EXPENSE, "333", self.food, 3)
        self._add(KIND_EXPENSE, "333", self.traffic, 4)
        stats = stats_service.category_breakdown(2025, 7, KIND_EXPENSE)
        total = sum((s.share or Decimal(0) for s in stats), Decimal(0))
        self.assertAlmostEqual(float(total), 1.0, places=6)

    def test_empty_month_returns_no_slices(self):
        self.assertEqual(stats_service.category_breakdown(2025, 12, KIND_EXPENSE), [])


class TestChartControls(DatabaseTestCase):
    """图表控件本身能构建（无头环境）。"""

    def test_line_chart_builds(self):
        from _shared import components as ui
        from _shared import theme

        series = [(day, Decimal(day * 10)) for day in range(1, 31)]
        chart = ui.line_chart(series, palette=theme.Palette(None))
        self.assertIsInstance(chart, ft.LineChart)
        self.assertEqual(len(chart.data_series[0].data_points), 30)

    def test_line_chart_empty_is_placeholder(self):
        from _shared import components as ui
        from _shared import theme

        placeholder = ui.line_chart([], palette=theme.Palette(None))
        self.assertNotIsInstance(placeholder, ft.LineChart)

    def test_flat_series_does_not_break_axis(self):
        """全平的数据（没有流水）不能让坐标轴上界等于下界。"""
        from _shared import components as ui
        from _shared import theme

        series = [(day, Decimal("0")) for day in range(1, 6)]
        chart = ui.line_chart(series, palette=theme.Palette(None))
        self.assertGreater(chart.max_y, chart.min_y)

    def test_pie_chart_builds(self):
        from _shared import components as ui
        from _shared import theme
        from models import CategoryStat

        stats = [
            CategoryStat(1, "餐饮", "#E53935", "restaurant", Decimal("80"), Decimal("0.8")),
            CategoryStat(2, "交通", "#FB8C00", "directions_bus", Decimal("20"), Decimal("0.2")),
        ]
        chart = ui.pie_chart(stats, palette=theme.Palette(None))
        self.assertIsInstance(chart, ft.PieChart)
        self.assertEqual(len(chart.sections), 2)

    def test_pie_chart_empty_is_placeholder(self):
        from _shared import components as ui
        from _shared import theme

        self.assertNotIsInstance(ui.pie_chart([], palette=theme.Palette(None)), ft.PieChart)

    def test_tiny_slice_has_no_title(self):
        """占比很小的扇区不写字，否则饼图上会糊成一团。"""
        from _shared import components as ui
        from _shared import theme
        from models import CategoryStat

        stats = [
            CategoryStat(1, "大头", "#E53935", "restaurant", Decimal("99"), Decimal("0.99")),
            CategoryStat(2, "小头", "#FB8C00", "directions_bus", Decimal("1"), Decimal("0.01")),
        ]
        chart = ui.pie_chart(stats, palette=theme.Palette(None))
        titles = [section.title for section in chart.sections]
        self.assertTrue(titles[0])
        self.assertEqual(titles[1], "")

    def test_legend_limits_rows(self):
        from _shared import components as ui
        from _shared import theme
        from models import CategoryStat

        stats = [
            CategoryStat(i, f"分类{i}", None, "category", Decimal(i), Decimal("0.1"))
            for i in range(1, 10)
        ]
        legend = ui.legend_row(stats, palette=theme.Palette(None), limit=6)
        # 6 行 + 1 行"其余略"
        self.assertEqual(len(legend.controls), 7)


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""第一步测试 1/3：数据库初始化与流水增删改查。

不涉及任何界面，只验证"数据存得住、取得出、改得对、删得掉"。
"""

from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal

from conftest import DatabaseTestCase

import db
from db.repositories import category_repo, transaction_repo
from db.repositories.transaction_repo import TransactionError, TransactionFilter, TransactionInput
from models import KIND_EXPENSE, KIND_INCOME


class TestSchemaInit(DatabaseTestCase):

    def test_tables_created(self):
        conn = db.get_connection()
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        tables = {row["name"] for row in rows}
        for expected in ("categories", "transactions", "goals", "accounts", "settings", "budgets"):
            self.assertIn(expected, tables)

    def test_schema_version_recorded(self):
        self.assertEqual(db.get_schema_version(db.get_connection()), db.SCHEMA_VERSION)

    def test_default_categories_seeded(self):
        incomes = category_repo.list_categories(KIND_INCOME)
        expenses = category_repo.list_categories(KIND_EXPENSE)
        self.assertGreaterEqual(len(incomes), 5)
        self.assertGreaterEqual(len(expenses), 10)
        names = {c.name for c in expenses}
        self.assertIn("餐饮", names)

    def test_init_is_idempotent(self):
        before = db.database_stats()["categories"]
        db.init_database(force=True)
        db.init_database(force=True)
        self.assertEqual(db.database_stats()["categories"], before)

    def test_foreign_keys_enabled(self):
        row = db.get_connection().execute("PRAGMA foreign_keys").fetchone()
        self.assertEqual(int(row[0]), 1)

    def test_amount_check_rejects_negative(self):
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            db.get_connection().execute(
                "INSERT INTO transactions (kind, amount, happened_on) VALUES ('expense', '-1', '2025-01-01')"
            )


class TestTransactionCrud(DatabaseTestCase):

    def setUp(self):
        super().setUp()
        self.food = category_repo.find_category_by_name("餐饮", KIND_EXPENSE)
        self.salary = category_repo.find_category_by_name("工资", KIND_INCOME)
        assert self.food and self.salary

    def test_create_expense(self):
        tx = transaction_repo.create_transaction(TransactionInput(
            kind=KIND_EXPENSE,
            amount="35.50",
            category_id=self.food.id,
            happened_on=date(2025, 3, 15),
            note="午饭",
        ))
        self.assertGreater(tx.id, 0)
        self.assertEqual(tx.kind, KIND_EXPENSE)
        self.assertMoney(tx.amount, "35.50")
        self.assertEqual(tx.category_name, "餐饮")
        self.assertEqual(tx.note, "午饭")
        self.assertEqual(tx.happened_on, date(2025, 3, 15))

    def test_create_income_and_signed_amount(self):
        tx = transaction_repo.create_transaction(TransactionInput(
            kind=KIND_INCOME, amount=8000, category_id=self.salary.id,
            happened_on="2025-03-01", note="三月工资",
        ))
        self.assertMoney(tx.amount, "8000.00")
        self.assertMoney(tx.signed_amount, "8000.00")
        self.assertTrue(tx.is_income)

    def test_expense_signed_amount_is_negative(self):
        tx = transaction_repo.create_transaction(TransactionInput(
            kind=KIND_EXPENSE, amount="12.30", category_id=self.food.id,
            happened_on="2025-03-02",
        ))
        self.assertMoney(tx.signed_amount, "-12.30")

    def test_amount_is_quantized_to_cents(self):
        tx = transaction_repo.create_transaction(TransactionInput(
            kind=KIND_EXPENSE, amount="10.005", category_id=self.food.id,
            happened_on="2025-03-02",
        ))
        # ROUND_HALF_UP -> 10.01
        self.assertMoney(tx.amount, "10.01")

    def test_get_transaction(self):
        tx = transaction_repo.create_transaction(TransactionInput(
            kind=KIND_EXPENSE, amount="5", category_id=self.food.id,
            happened_on="2025-03-03",
        ))
        fetched = transaction_repo.get_transaction(tx.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.id, tx.id)
        self.assertMoney(fetched.amount, "5.00")

    def test_list_is_desc_by_date(self):
        for day in (1, 20, 10):
            transaction_repo.create_transaction(TransactionInput(
                kind=KIND_EXPENSE, amount="1", category_id=self.food.id,
                happened_on=date(2025, 3, day),
            ))
        listed = transaction_repo.list_transactions()
        self.assertEqual([t.happened_on.day for t in listed], [20, 10, 1])

    def test_update_transaction(self):
        tx = transaction_repo.create_transaction(TransactionInput(
            kind=KIND_EXPENSE, amount="10", category_id=self.food.id,
            happened_on="2025-03-05", note="早饭",
        ))
        updated = transaction_repo.update_transaction(tx.id, TransactionInput(
            kind=KIND_EXPENSE, amount="18.80", category_id=self.food.id,
            happened_on="2025-03-06", note="早饭+咖啡",
        ))
        self.assertMoney(updated.amount, "18.80")
        self.assertEqual(updated.note, "早饭+咖啡")
        self.assertEqual(updated.happened_on, date(2025, 3, 6))
        self.assertEqual(transaction_repo.count_transactions(), 1)

    def test_delete_transaction(self):
        tx = transaction_repo.create_transaction(TransactionInput(
            kind=KIND_EXPENSE, amount="9", category_id=self.food.id,
            happened_on="2025-03-07",
        ))
        self.assertTrue(transaction_repo.delete_transaction(tx.id))
        self.assertIsNone(transaction_repo.get_transaction(tx.id))
        self.assertFalse(transaction_repo.delete_transaction(tx.id))


class TestTransactionValidation(DatabaseTestCase):

    def setUp(self):
        super().setUp()
        self.food = category_repo.find_category_by_name("餐饮", KIND_EXPENSE)

    def _make(self, amount, **kwargs):
        return transaction_repo.create_transaction(TransactionInput(
            kind=kwargs.pop("kind", KIND_EXPENSE),
            amount=amount,
            category_id=self.food.id,
            happened_on=kwargs.pop("happened_on", "2025-03-01"),
            **kwargs,
        ))

    def test_reject_negative(self):
        with self.assertRaises(TransactionError) as ctx:
            self._make("-5")
        self.assertIn("不能为负数", str(ctx.exception))

    def test_reject_non_numeric(self):
        for bad in ("abc", "12a", "一百", "--3", "3..5"):
            with self.assertRaises(TransactionError, msg=f"{bad} 应被拒绝"):
                self._make(bad)

    def test_reject_zero(self):
        with self.assertRaises(TransactionError):
            self._make("0")

    def test_reject_empty(self):
        with self.assertRaises(TransactionError):
            self._make("")

    def test_reject_over_limit(self):
        with self.assertRaises(TransactionError) as ctx:
            self._make("100000000")
        self.assertIn("上限", str(ctx.exception))

    def test_accept_full_width_and_separators(self):
        tx = self._make("１，２３４．５６")
        self.assertMoney(tx.amount, "1234.56")

    def test_accept_comma_separated(self):
        tx = self._make("1,234.56")
        self.assertMoney(tx.amount, "1234.56")

    def test_reject_bad_kind(self):
        with self.assertRaises(TransactionError):
            self._make("10", kind="transfer")

    def test_reject_bad_date(self):
        with self.assertRaises(TransactionError):
            self._make("10", happened_on="2025-13-40")

    def test_note_length_limited(self):
        with self.assertRaises(TransactionError):
            self._make("10", note="备" * 101)

    def test_default_date_is_today(self):
        tx = self._make("10", happened_on=None)
        self.assertEqual(tx.happened_on, date.today())


class TestTransactionFilter(DatabaseTestCase):

    def setUp(self):
        super().setUp()
        self.food = category_repo.find_category_by_name("餐饮", KIND_EXPENSE)
        self.salary = category_repo.find_category_by_name("工资", KIND_INCOME)
        self._seed()

    def _seed(self):
        data = [
            (KIND_INCOME, "8000", self.salary.id, "2025-01-05", "一月工资"),
            (KIND_EXPENSE, "300", self.food.id, "2025-01-06", "聚餐"),
            (KIND_INCOME, "8000", self.salary.id, "2025-02-05", "二月工资"),
            (KIND_EXPENSE, "500", self.food.id, "2025-02-08", "火锅"),
            (KIND_EXPENSE, "120", self.food.id, "2025-02-09", "外卖"),
        ]
        for kind, amount, cat, day, note in data:
            transaction_repo.create_transaction(TransactionInput(
                kind=kind, amount=amount, category_id=cat, happened_on=day, note=note,
            ))

    def test_filter_by_month(self):
        rows = transaction_repo.list_transactions(TransactionFilter(year=2025, month=2))
        self.assertEqual(len(rows), 3)
        self.assertEqual(transaction_repo.count_transactions(TransactionFilter(year=2025, month=1)), 2)

    def test_filter_by_kind(self):
        rows = transaction_repo.list_transactions(TransactionFilter(kind=KIND_EXPENSE))
        self.assertEqual(len(rows), 3)

    def test_filter_by_category(self):
        rows = transaction_repo.list_transactions(TransactionFilter(category_id=self.food.id))
        self.assertEqual(len(rows), 3)

    def test_filter_by_date_range(self):
        rows = transaction_repo.list_transactions(TransactionFilter(
            date_from=date(2025, 2, 1), date_to=date(2025, 2, 8),
        ))
        self.assertEqual(len(rows), 2)

    def test_filter_by_keyword(self):
        rows = transaction_repo.list_transactions(TransactionFilter(keyword="工资"))
        self.assertEqual(len(rows), 2)

    def test_pagination(self):
        for day in (10, 11, 12, 13, 14, 15):
            transaction_repo.create_transaction(TransactionInput(
                kind=KIND_EXPENSE, amount="1", category_id=self.food.id,
                happened_on=date(2025, 3, day), note=f"分页{day}",
            ))
        flt = TransactionFilter(year=2025, month=3)
        self.assertEqual(transaction_repo.count_transactions(flt), 6)

        page1 = transaction_repo.list_transactions(TransactionFilter(
            year=2025, month=3, limit=2, offset=0))
        page2 = transaction_repo.list_transactions(TransactionFilter(
            year=2025, month=3, limit=2, offset=2))
        page3 = transaction_repo.list_transactions(TransactionFilter(
            year=2025, month=3, limit=2, offset=4))
        self.assertEqual(len(page1), 2)
        self.assertEqual(len(page2), 2)
        self.assertEqual(len(page3), 2)
        ids = [t.id for t in (*page1, *page2, *page3)]
        self.assertEqual(len(set(ids)), 6, "分页结果不应重复")
        self.assertEqual([t.happened_on.day for t in page1], [15, 14])

    def test_available_months(self):
        self.assertEqual(transaction_repo.available_months(), [(2025, 2), (2025, 1)])

    def test_recent_transactions(self):
        rows = transaction_repo.recent_transactions(3)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0].happened_on, date(2025, 2, 9))


class TestCategoryCrud(DatabaseTestCase):

    def test_create_and_update(self):
        cat = category_repo.create_category("宠物", KIND_EXPENSE, icon="pets", color="#00BCD4")
        self.assertEqual(cat.name, "宠物")
        updated = category_repo.update_category(cat.id, name="宠物用品", color="#009688")
        self.assertEqual(updated.name, "宠物用品")
        self.assertEqual(updated.color, "#009688")

    def test_duplicate_rejected(self):
        category_repo.create_category("健身", KIND_EXPENSE)
        from db.repositories.category_repo import CategoryError
        with self.assertRaises(CategoryError):
            category_repo.create_category("健身", KIND_EXPENSE)

    def test_same_name_different_kind_allowed(self):
        a = category_repo.create_category("报销", KIND_EXPENSE)
        b = category_repo.create_category("报销", KIND_INCOME)
        self.assertNotEqual(a.id, b.id)

    def test_system_category_protected(self):
        from db.repositories.category_repo import CategoryError
        food = category_repo.find_category_by_name("餐饮", KIND_EXPENSE)
        self.assertTrue(food.is_system)
        with self.assertRaises(CategoryError):
            category_repo.delete_category(food.id)

    def test_delete_used_category_blocked_then_forced(self):
        from db.repositories.category_repo import CategoryError
        cat = category_repo.create_category("临时分类", KIND_EXPENSE)
        tx = transaction_repo.create_transaction(TransactionInput(
            kind=KIND_EXPENSE, amount="20", category_id=cat.id, happened_on="2025-04-01",
        ))
        with self.assertRaises(CategoryError):
            category_repo.delete_category(cat.id)

        self.assertTrue(category_repo.delete_category(cat.id, force=True))
        kept = transaction_repo.get_transaction(tx.id)
        self.assertIsNotNone(kept, "删除分类不应删掉历史流水")
        self.assertIsNone(kept.category_id)
        self.assertMoney(kept.amount, "20.00")

    def test_usage_counts(self):
        cat = category_repo.create_category("玩具", KIND_EXPENSE)
        for amount in ("10", "20"):
            transaction_repo.create_transaction(TransactionInput(
                kind=KIND_EXPENSE, amount=amount, category_id=cat.id, happened_on="2025-04-02",
            ))
        self.assertEqual(category_repo.category_usage().get(cat.id), 2)

    def test_category_error_on_empty_name(self):
        from db.repositories.category_repo import CategoryError
        with self.assertRaises(CategoryError):
            category_repo.create_category("   ", KIND_EXPENSE)


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""统计服务：总存款、月度收支、储蓄率、分类占比、月度趋势。

这里是"钱数怎么算"的唯一出处。UI 只负责把结果排版，绝不自己算钱。

口径说明
--------
* **总存款** = 所有收入合计 − 所有支出合计（含未来/补录的日期）；
* **本月结余** = 本月收入 − 本月支出；
* **储蓄率** = 本月结余 ÷ 本月收入；本月没有收入时返回 ``None``（无法计算），
  而不是 0%，避免"没工资那个月储蓄率 0%"这种误导。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable

from db.connection import get_connection
from models import CategoryStat, MonthlySummary, KIND_EXPENSE, KIND_INCOME
from utils.money import ZERO, money_from_db, safe_ratio


@dataclass(frozen=True)
class MonthlyPoint:
    """趋势图的一个点。"""

    year: int
    month: int
    income: Decimal
    expense: Decimal

    @property
    def balance(self) -> Decimal:
        return self.income - self.expense

    @property
    def label(self) -> str:
        return f"{self.month}月"


def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    """月份加减，跨年自动处理。``shift_month(2025, 1, -1) == (2024, 12)``。"""
    index = (year * 12 + (month - 1)) + delta
    return index // 12, index % 12 + 1


def current_month() -> tuple[int, int]:
    today = date.today()
    return today.year, today.month


def month_range(year: int, month: int) -> tuple[date, date]:
    """某月的起止日期（含首尾）。"""
    first = date(year, month, 1)
    next_year, next_month = shift_month(year, month, 1)
    return first, date(next_year, next_month, 1) - timedelta(days=1)


def starting_balance() -> Decimal:
    """初始财产：第一次使用应用时手里已有的钱（默认 0）。"""
    from services import settings_service

    return settings_service.get_starting_balance()


def transaction_net() -> Decimal:
    """所有流水的净额：收入合计 − 支出合计。"""
    row = get_connection().execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN kind = 'income'  THEN CAST(amount AS REAL) END), 0) AS income,
            COALESCE(SUM(CASE WHEN kind = 'expense' THEN CAST(amount AS REAL) END), 0) AS expense
          FROM transactions
        """
    ).fetchone()
    # 聚合在 SQL 里用 REAL 做中间量，最后回到 Decimal 两位小数即可
    return money_from_db(f"{row['income']:.2f}") - money_from_db(f"{row['expense']:.2f}")


def total_balance() -> Decimal:
    """总存款 = 初始财产 + 所有收入 − 所有支出。

    把初始财产算进来，是为了让"第一次使用"时的真实家底也对得上：
    否则刚装好应用总存款是 0，跟手里实际有多少钱不一致。
    初始财产默认为 0，所以没设置过的用户行为与以前完全一样。
    """
    return starting_balance() + transaction_net()


def total_income() -> Decimal:
    row = get_connection().execute(
        "SELECT COALESCE(SUM(CAST(amount AS REAL)), 0) AS v FROM transactions WHERE kind = 'income'"
    ).fetchone()
    return money_from_db(f"{row['v']:.2f}")


def total_expense() -> Decimal:
    row = get_connection().execute(
        "SELECT COALESCE(SUM(CAST(amount AS REAL)), 0) AS v FROM transactions WHERE kind = 'expense'"
    ).fetchone()
    return money_from_db(f"{row['v']:.2f}")


def daily_balance_series(year: int, month: int) -> list[tuple[int, Decimal]]:
    """某月"每天结束时的存款"序列，供流水页的曲线图使用。

    返回 ``[(日, 当日结束时的累计存款), ...]``，起点是**月初的存款**
    （= 初始财产 + 该月之前的流水净额），这样曲线从月初第一天的 0 号点开始，
    再逐日累加当天的收入减支出。

    没有流水的日子也会补点（金额与前一天相同），曲线才是连续的。
    """
    first_day, last_day = month_range(year, month)
    prefix = f"{year:04d}-{month:02d}"

    # 月初起点：初始财产 + 本月之前的全部流水
    row = get_connection().execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN kind = 'income'  THEN CAST(amount AS REAL) END), 0) AS income,
            COALESCE(SUM(CASE WHEN kind = 'expense' THEN CAST(amount AS REAL) END), 0) AS expense
          FROM transactions
         WHERE substr(happened_on, 1, 7) < ?
        """,
        (prefix,),
    ).fetchone()
    running = (starting_balance()
               + money_from_db(f"{row['income']:.2f}")
               - money_from_db(f"{row['expense']:.2f}"))

    # 当月每天的净额
    rows = get_connection().execute(
        """
        SELECT substr(happened_on, 9, 2) AS day,
               COALESCE(SUM(CASE WHEN kind = 'income'  THEN CAST(amount AS REAL) END), 0) AS income,
               COALESCE(SUM(CASE WHEN kind = 'expense' THEN CAST(amount AS REAL) END), 0) AS expense
          FROM transactions
         WHERE substr(happened_on, 1, 7) = ?
         GROUP BY day
         ORDER BY day
        """,
        (prefix,),
    ).fetchall()
    daily = {
        int(r["day"]): money_from_db(f"{r['income']:.2f}") - money_from_db(f"{r['expense']:.2f}")
        for r in rows
    }

    series: list[tuple[int, Decimal]] = []
    day = first_day
    while day <= last_day:
        running += daily.get(day.day, ZERO)
        series.append((day.day, running))
        day += timedelta(days=1)
    return series


def monthly_summary(year: int, month: int) -> MonthlySummary:
    """某月收入 / 支出 / 结余 / 储蓄率。"""
    prefix = f"{year:04d}-{month:02d}"
    row = get_connection().execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN kind = 'income'  THEN CAST(amount AS REAL) END), 0) AS income,
            COALESCE(SUM(CASE WHEN kind = 'expense' THEN CAST(amount AS REAL) END), 0) AS expense
          FROM transactions
         WHERE substr(happened_on, 1, 7) = ?
        """,
        (prefix,),
    ).fetchone()
    return MonthlySummary(
        year=year,
        month=month,
        income=money_from_db(f"{row['income']:.2f}"),
        expense=money_from_db(f"{row['expense']:.2f}"),
    )


def this_month_summary() -> MonthlySummary:
    year, month = current_month()
    return monthly_summary(year, month)


def category_breakdown(year: int, month: int, kind: str = KIND_EXPENSE,
                       limit: int | None = None) -> list[CategoryStat]:
    """某月按分类聚合；``share`` 为该分类占该方向总额的比例。"""
    if kind not in {KIND_INCOME, KIND_EXPENSE}:
        raise ValueError("kind 只能是 income 或 expense")
    prefix = f"{year:04d}-{month:02d}"
    sql = """
        SELECT t.category_id           AS category_id,
               COALESCE(c.name, '未分类') AS name,
               COALESCE(c.color, '#90A4AE') AS color,
               COALESCE(c.icon, 'category') AS icon,
               SUM(CAST(t.amount AS REAL)) AS amount
          FROM transactions t
          LEFT JOIN categories c ON c.id = t.category_id
         WHERE t.kind = ? AND substr(t.happened_on, 1, 7) = ?
         GROUP BY t.category_id
         ORDER BY amount DESC
    """
    params: list[object] = [kind, prefix]
    if limit is not None:
        sql += " LIMIT ?"
        params.append(int(limit))
    rows = get_connection().execute(sql, params).fetchall()
    stats = [CategoryStat.from_row(row) for row in rows]

    total = sum((item.amount for item in stats), ZERO)
    if total > 0:
        stats = [
            CategoryStat(
                category_id=item.category_id,
                name=item.name,
                color=item.color,
                icon=item.icon,
                amount=item.amount,
                share=(item.amount / total),
            )
            for item in stats
        ]
    return stats


def monthly_trend(months: int = 6, *, end: tuple[int, int] | None = None) -> list[MonthlyPoint]:
    """最近 ``months`` 个月（含当月）的收支，用于折线图。"""
    if months <= 0:
        return []
    end_year, end_month = end or current_month()
    points: list[MonthlyPoint] = []
    for offset in range(months - 1, -1, -1):
        year, month = shift_month(end_year, end_month, -offset)
        summary = monthly_summary(year, month)
        points.append(MonthlyPoint(year, month, summary.income, summary.expense))
    return points


def cumulative_savings_trend(months: int = 6, *,
                             end: tuple[int, int] | None = None) -> list[tuple[MonthlyPoint, Decimal]]:
    """存款增长折线：每个月末的累计存款额。

    起点 = 更早所有月份的结余合计，逐月累加。
    """
    points = monthly_trend(months, end=end)
    if not points:
        return []
    first_year, first_month = points[0].year, points[0].month
    row = get_connection().execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN kind = 'income'  THEN CAST(amount AS REAL) END), 0) AS income,
            COALESCE(SUM(CASE WHEN kind = 'expense' THEN CAST(amount AS REAL) END), 0) AS expense
          FROM transactions
         WHERE substr(happened_on, 1, 7) < ?
        """,
        (f"{first_year:04d}-{first_month:02d}",),
    ).fetchone()
    running = money_from_db(f"{row['income']:.2f}") - money_from_db(f"{row['expense']:.2f}")

    result: list[tuple[MonthlyPoint, Decimal]] = []
    for point in points:
        running += point.balance
        result.append((point, running))
    return result


def savings_rate(year: int | None = None, month: int | None = None) -> Decimal | None:
    """便捷函数：某月（默认本月）储蓄率。"""
    if year is None or month is None:
        summary = this_month_summary()
    else:
        summary = monthly_summary(year, month)
    return summary.savings_rate


def dashboard_snapshot() -> dict[str, object]:
    """首页一次取齐所需数据，避免页面里多次查询。"""
    from services.goal_service import list_progress  # 延迟导入，避免循环依赖

    summary = this_month_summary()
    prev_year, prev_month = shift_month(summary.year, summary.month, -1)
    previous = monthly_summary(prev_year, prev_month)
    return {
        "total_balance": total_balance(),
        "month": summary,
        "compare": previous,
        "month_balance_delta": summary.balance - previous.balance,
        "savings_rate": summary.savings_rate,
        "top_expense": category_breakdown(summary.year, summary.month, KIND_EXPENSE, limit=5),
        "goals": list_progress(),
    }


def total_count() -> int:
    row = get_connection().execute("SELECT COUNT(*) AS n FROM transactions").fetchone()
    return int(row["n"])

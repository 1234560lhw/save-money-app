"""流水仓储：增删改查 + 多维筛选。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from db.connection import get_connection, transaction
from errors import AppError, MoneyError
from models import Transaction, KIND_EXPENSE, KIND_INCOME
from utils.money import money_to_db, parse_money

_ALLOWED_KINDS = {KIND_INCOME, KIND_EXPENSE}
_MAX_NOTE = 100

_SELECT = """
SELECT t.*,
       c.name  AS category_name,
       c.icon  AS category_icon,
       c.color AS category_color,
       a.name  AS account_name
  FROM transactions t
  LEFT JOIN categories c ON c.id = t.category_id
  LEFT JOIN accounts   a ON a.id = t.account_id
"""


class TransactionError(MoneyError):
    """流水校验/操作失败，消息可直接展示给用户。

    继承 ``MoneyError``，因此金额格式错误也会被 ``except TransactionError``
    一并捕获。
    """


@dataclass(frozen=True)
class TransactionInput:
    """新流水或流水修改内容。"""

    kind: str
    amount: Decimal | int | str
    category_id: int | None = None
    happened_on: date | str | None = None
    note: str = ""
    account_id: int | None = None


@dataclass(frozen=True)
class TransactionFilter:
    """列表页筛选条件，全部可选。"""

    year: int | None = None
    month: int | None = None
    date_from: date | None = None
    date_to: date | None = None
    kind: str | None = None
    category_id: int | None = None
    keyword: str | None = None
    limit: int | None = None
    offset: int = 0


def _normalize_date(value: date | str | None) -> str:
    if value is None:
        return date.today().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError as exc:
        raise TransactionError("日期格式不正确") from exc


def _validate(data: TransactionInput) -> tuple[str, str, int | None, str, str, int | None]:
    if data.kind not in _ALLOWED_KINDS:
        raise TransactionError("类型只能是收入或支出")
    try:
        amount = parse_money(data.amount, field="金额")
    except MoneyError as exc:
        # 统一转成 TransactionError，调用方只需捕获一种异常
        raise TransactionError(str(exc)) from exc
    note = (data.note or "").strip()
    if len(note) > _MAX_NOTE:
        raise TransactionError(f"备注不能超过 {_MAX_NOTE} 个字")
    return (
        data.kind,
        money_to_db(amount),
        data.category_id,
        _normalize_date(data.happened_on),
        note,
        data.account_id,
    )


def create_transaction(data: TransactionInput) -> Transaction:
    """新增一笔流水。"""
    kind, amount, category_id, happened_on, note, account_id = _validate(data)
    try:
        with transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO transactions
                    (kind, amount, category_id, account_id, happened_on, note)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (kind, amount, category_id, account_id, happened_on, note),
            )
            new_id = int(cur.lastrowid)
    except Exception as exc:  # sqlite3.IntegrityError 等
        raise TransactionError(f"保存失败：{exc}") from exc

    created = get_transaction(new_id)
    assert created is not None
    return created


def update_transaction(transaction_id: int, data: TransactionInput) -> Transaction:
    """整体更新一笔流水。"""
    if get_transaction(transaction_id) is None:
        raise TransactionError("流水不存在")

    kind, amount, category_id, happened_on, note, account_id = _validate(data)
    with transaction() as conn:
        conn.execute(
            """
            UPDATE transactions
               SET kind = ?, amount = ?, category_id = ?, account_id = ?,
                   happened_on = ?, note = ?, updated_at = datetime('now', 'localtime')
             WHERE id = ?
            """,
            (kind, amount, category_id, account_id, happened_on, note, transaction_id),
        )

    updated = get_transaction(transaction_id)
    assert updated is not None
    return updated


def delete_transaction(transaction_id: int) -> bool:
    """删除一笔流水；返回是否真的删掉了。"""
    with transaction() as conn:
        cur = conn.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))
    return cur.rowcount > 0


def get_transaction(transaction_id: int) -> Transaction | None:
    row = get_connection().execute(_SELECT + " WHERE t.id = ?", (transaction_id,)).fetchone()
    return Transaction.from_row(row) if row else None


def _build_where(flt: TransactionFilter) -> tuple[str, list[object]]:
    clauses: list[str] = []
    params: list[object] = []

    if flt.year is not None and flt.month is not None:
        prefix = f"{int(flt.year):04d}-{int(flt.month):02d}"
        clauses.append("substr(t.happened_on, 1, 7) = ?")
        params.append(prefix)
    else:
        if flt.date_from is not None:
            clauses.append("t.happened_on >= ?")
            params.append(flt.date_from.isoformat())
        if flt.date_to is not None:
            clauses.append("t.happened_on <= ?")
            params.append(flt.date_to.isoformat())

    if flt.kind is not None:
        clauses.append("t.kind = ?")
        params.append(flt.kind)
    if flt.category_id is not None:
        clauses.append("t.category_id = ?")
        params.append(flt.category_id)
    if flt.keyword:
        clauses.append("t.note LIKE ?")
        params.append(f"%{flt.keyword.strip()}%")

    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


def list_transactions(flt: TransactionFilter | None = None) -> list[Transaction]:
    """按时间倒序列出流水（同一天按录入顺序倒序）。"""
    flt = flt or TransactionFilter()
    where, params = _build_where(flt)
    sql = _SELECT + where + " ORDER BY t.happened_on DESC, t.id DESC"
    if flt.limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params = [*params, int(flt.limit), int(flt.offset)]
    rows = get_connection().execute(sql, params).fetchall()
    return [Transaction.from_row(row) for row in rows]


def count_transactions(flt: TransactionFilter | None = None) -> int:
    """符合条件的流水条数（分页用）。"""
    flt = flt or TransactionFilter()
    where, params = _build_where(flt)
    row = get_connection().execute(
        "SELECT COUNT(*) AS n FROM transactions t" + where, params
    ).fetchone()
    return int(row["n"])


def available_months(limit: int = 24) -> list[tuple[int, int]]:
    """有流水的月份列表（新的在前），给"按月筛选"用。"""
    rows = get_connection().execute(
        """
        SELECT DISTINCT substr(happened_on, 1, 4) AS y, substr(happened_on, 6, 2) AS m
          FROM transactions
         ORDER BY y DESC, m DESC
         LIMIT ?
        """,
        (int(limit),),
    ).fetchall()
    return [(int(row["y"]), int(row["m"])) for row in rows]


def recent_transactions(limit: int = 5) -> list[Transaction]:
    """最近几笔流水，首页展示用。"""
    return list_transactions(TransactionFilter(limit=limit))

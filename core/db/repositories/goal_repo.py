"""存钱目标仓储：增删改查 + 存入/取出。

约定
----
``saved_amount`` 只记录这个目标已经攒下的钱，来源可以是：
* 用户手动"存入 / 取出"（``deposit`` / ``withdraw``）；
* 或在记一笔时直接勾选某个目标。
它独立于流水表，因此不影响"总存款"的统计口径。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from db.connection import get_connection, transaction
from errors import AppError, MoneyError
from models import GoalProgress
from utils.money import ZERO, money_from_db, money_to_db, parse_money

_MAX_NAME = 30
_MAX_NOTE = 100

_STATUS_ACTIVE = "active"
_STATUS_DONE = "done"
_STATUS_ARCHIVED = "archived"
_ALLOWED_STATUS = {_STATUS_ACTIVE, _STATUS_DONE, _STATUS_ARCHIVED}

_SELECT = "SELECT * FROM goals"


class GoalError(MoneyError):
    """目标校验/操作失败，消息可直接展示给用户。

    继承 ``MoneyError`` 是为了让金额解析失败（"必须是数字"等）也能被
    ``except GoalError`` 统一捕获，调用方不必区分异常来源。
    """


@dataclass(frozen=True)
class GoalInput:
    """新建或修改目标。``deadline`` 为空表示没有截止日期。"""

    name: str
    target_amount: Decimal | int | str
    saved_amount: Decimal | int | str = ZERO
    deadline: date | str | None = None
    note: str = ""


def _normalize_deadline(value: date | str | None) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError as exc:
        raise GoalError("截止日期格式不正确") from exc


def _parse_money(raw, *, field: str, allow_zero: bool = False) -> Decimal:
    """金额解析失败时统一转成 :class:`GoalError`。

    ``parse_money`` 抛的是基类 ``MoneyError``，若直接透传，调用方写
    ``except GoalError`` 会捕不到（基类实例不是子类实例）。这里统一转换，
    保证"目标相关的所有校验错误都能被 GoalError 捕获"。
    """
    try:
        return parse_money(raw, field=field, allow_zero=allow_zero)
    except MoneyError as exc:
        raise GoalError(str(exc)) from exc


def _validate(data: GoalInput) -> tuple[str, str, str, str | None, str]:
    name = (data.name or "").strip()
    if not name:
        raise GoalError("目标名称不能为空")
    if len(name) > _MAX_NAME:
        raise GoalError(f"目标名称不能超过 {_MAX_NAME} 个字")

    target = _parse_money(data.target_amount, field="目标金额")
    saved = _parse_money(data.saved_amount, field="已存金额", allow_zero=True)

    note = (data.note or "").strip()
    if len(note) > _MAX_NOTE:
        raise GoalError(f"备注不能超过 {_MAX_NOTE} 个字")

    return name, money_to_db(target), money_to_db(saved), _normalize_deadline(data.deadline), note


def _row_to_goal(row) -> GoalProgress:
    """原始行 -> 带基本字段的 GoalProgress（派生字段交给 goal_service 补全）。"""
    deadline = date.fromisoformat(row["deadline"]) if row["deadline"] else None
    return GoalProgress(
        goal_id=int(row["id"]),
        name=str(row["name"]),
        target_amount=money_from_db(row["target_amount"]),
        saved_amount=money_from_db(row["saved_amount"]),
        deadline=deadline,
        note=str(row["note"] or ""),
        created_at=row["created_at"],
    )


def create_goal(data: GoalInput) -> GoalProgress:
    """新建存钱目标。"""
    name, target, saved, deadline, note = _validate(data)
    with transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO goals (name, target_amount, saved_amount, deadline, note)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, target, saved, deadline, note),
        )
        new_id = int(cur.lastrowid)
    goal = get_goal(new_id)
    assert goal is not None
    return goal


def update_goal(goal_id: int, data: GoalInput) -> GoalProgress:
    """整体更新目标（含已存金额的手工修正）。"""
    if get_goal(goal_id) is None:
        raise GoalError("目标不存在")
    name, target, saved, deadline, note = _validate(data)
    with transaction() as conn:
        conn.execute(
            """
            UPDATE goals
               SET name = ?, target_amount = ?, saved_amount = ?, deadline = ?, note = ?,
                   updated_at = datetime('now', 'localtime')
             WHERE id = ?
            """,
            (name, target, saved, deadline, note, goal_id),
        )
    updated = get_goal(goal_id)
    assert updated is not None
    return updated


def delete_goal(goal_id: int) -> bool:
    with transaction() as conn:
        cur = conn.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
    return cur.rowcount > 0


def get_goal(goal_id: int) -> GoalProgress | None:
    row = get_connection().execute(_SELECT + " WHERE id = ?", (goal_id,)).fetchone()
    return _row_to_goal(row) if row else None


def list_goals(*, include_archived: bool = False) -> list[GoalProgress]:
    """列出目标：未完成的在前，其次按截止日期升序。"""
    sql = _SELECT
    params: list[object] = []
    if not include_archived:
        sql += " WHERE status != ?"
        params.append(_STATUS_ARCHIVED)
    sql += """
        ORDER BY CASE status WHEN 'active' THEN 0 WHEN 'done' THEN 1 ELSE 2 END,
                 CASE WHEN deadline IS NULL THEN 1 ELSE 0 END,
                 deadline,
                 id
    """
    rows = get_connection().execute(sql, params).fetchall()
    return [_row_to_goal(row) for row in rows]


def set_saved_amount(goal_id: int, amount: Decimal | int | str) -> GoalProgress:
    """直接设置已存金额（编辑目标时用）。"""
    value = _parse_money(amount, field="已存金额", allow_zero=True)
    if get_goal(goal_id) is None:
        raise GoalError("目标不存在")
    with transaction() as conn:
        conn.execute(
            "UPDATE goals SET saved_amount = ?, updated_at = datetime('now', 'localtime') "
            "WHERE id = ?",
            (money_to_db(value), goal_id),
        )
    updated = get_goal(goal_id)
    assert updated is not None
    return updated


def deposit(goal_id: int, amount: Decimal | int | str) -> GoalProgress:
    """往目标里存入一笔（累加）。"""
    return _adjust(goal_id, amount, field="存入金额", negative=False)


def withdraw(goal_id: int, amount: Decimal | int | str) -> GoalProgress:
    """从目标里取出一笔（累减，不允许取成负数）。"""
    return _adjust(goal_id, amount, field="取出金额", negative=True)


def _adjust(goal_id: int, amount: Decimal | int | str, *, field: str,
            negative: bool) -> GoalProgress:
    current = get_goal(goal_id)
    if current is None:
        raise GoalError("目标不存在")
    value = _parse_money(amount, field=field)
    delta = -value if negative else value
    new_saved = current.saved_amount + delta
    if new_saved < 0:
        raise GoalError(f"取出金额超过已存金额（当前已存 {current.saved_amount}）")

    with transaction() as conn:
        conn.execute(
            "UPDATE goals SET saved_amount = ?, updated_at = datetime('now', 'localtime') "
            "WHERE id = ?",
            (money_to_db(new_saved), goal_id),
        )
    updated = get_goal(goal_id)
    assert updated is not None
    return updated


def set_status(goal_id: int, status: str) -> GoalProgress:
    """active / done / archived。"""
    if status not in _ALLOWED_STATUS:
        raise GoalError("状态不合法")
    if get_goal(goal_id) is None:
        raise GoalError("目标不存在")
    with transaction() as conn:
        conn.execute(
            "UPDATE goals SET status = ?, updated_at = datetime('now', 'localtime') WHERE id = ?",
            (status, goal_id),
        )
    updated = get_goal(goal_id)
    assert updated is not None
    return updated


def total_target_amount() -> Decimal:
    total = ZERO
    for goal in list_goals():
        total += goal.target_amount
    return total

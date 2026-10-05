"""存钱目标业务逻辑：进度、剩余金额、每月建议存入、达标判定。

每月建议存入的公式
------------------
给定目标金额 ``target``、已存 ``saved``、截止日期 ``deadline``：

1. 剩余金额 ``remaining = max(target - saved, 0)``；
2. 剩余月数 ``months_left``：
   * 没有截止日期 -> ``None``（无法给出建议，界面显示"—"）；
   * 有截止日期 -> 从今天到截止日期还跨了几个月（今天算 0 个月，
     即"今天到期"时至少按 1 个月处理，避免除零）；
3. ``monthly_suggestion = ceil(remaining / months_left, 2)``，向上取整到分，
   保证按建议金额存下去一定能在截止日期前达标；
4. 已达标 -> 建议金额为 0。

举例：目标 12000 元、已存 2000 元、截止日期在 5 个月后 ->
剩余 10000，10000 / 5 = 2000.00 元/月。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_CEILING

from db.repositories import goal_repo
from db.repositories.goal_repo import GoalError, GoalInput
from models import GoalProgress
from utils.money import CENTS, ZERO, to_decimal

__all__ = [
    "GoalError",
    "GoalInput",
    "list_progress",
    "get_progress",
    "create_goal",
    "update_goal",
    "delete_goal",
    "deposit",
    "withdraw",
    "months_left",
    "monthly_suggestion",
    "summarize",
    "total_saved",
    "total_target",
]


# ---------------------------------------------------------------- 计算

def months_left(deadline: date | None, today: date | None = None) -> int | None:
    """距离截止日期还剩几个月（不足一个月按 1 个月算）。

    * ``deadline`` 为空 -> ``None``（没有期限）
    * 已经过期 -> ``0``
    """
    if deadline is None:
        return None
    today = today or date.today()
    if deadline <= today:
        return 0
    months = (deadline.year - today.year) * 12 + (deadline.month - today.month)
    if deadline.day > today.day:
        months += 1
    return max(months, 1)


def monthly_suggestion(target: Decimal, saved: Decimal,
                       deadline: date | None, today: date | None = None) -> Decimal:
    """每月建议存入金额（向上取整到分；无期限或已达标返回 0）。"""
    target = to_decimal(target)
    saved = to_decimal(saved)
    remaining = target - saved
    if remaining <= 0:
        return ZERO
    left = months_left(deadline, today)
    if left is None or left <= 0:
        # 没有期限：给不出建议；已过期：剩余金额就是需要立刻补上的数
        return ZERO if left is None else remaining.quantize(CENTS, rounding=ROUND_CEILING)

    raw = remaining / left
    return raw.quantize(CENTS, rounding=ROUND_CEILING)


def summarize(goal: GoalProgress, today: date | None = None) -> GoalProgress:
    """把仓储读出的基础字段补上派生字段，返回新的不可变对象。"""
    today = today or date.today()
    target = goal.target_amount
    saved = goal.saved_amount
    remaining = target - saved
    if remaining < 0:
        remaining = ZERO

    progress = (saved / target) if target > 0 else ZERO
    if progress > 1:
        progress = Decimal("1")

    left = months_left(goal.deadline, today)
    is_done = saved >= target
    is_overdue = bool(goal.deadline and not is_done and goal.deadline < today)

    return GoalProgress(
        goal_id=goal.goal_id,
        name=goal.name,
        target_amount=target,
        saved_amount=saved,
        deadline=goal.deadline,
        note=goal.note,
        created_at=goal.created_at,
        remaining=remaining,
        progress=progress,
        months_left=left,
        monthly_suggestion=monthly_suggestion(target, saved, goal.deadline, today=today),
        is_done=is_done,
        is_overdue=is_overdue,
    )


# ---------------------------------------------------------------- 查询

def list_progress(*, include_archived: bool = False,
                  today: date | None = None) -> list[GoalProgress]:
    """所有目标（含派生字段），首页卡片列表直接用。"""
    return [summarize(goal, today=today) for goal in goal_repo.list_goals(include_archived=include_archived)]


def get_progress(goal_id: int, today: date | None = None) -> GoalProgress | None:
    goal = goal_repo.get_goal(goal_id)
    return summarize(goal, today=today) if goal else None


def total_target(*, include_archived: bool = False) -> Decimal:
    return sum((g.target_amount for g in list_progress(include_archived=include_archived)), ZERO)


def total_saved(*, include_archived: bool = False) -> Decimal:
    return sum((g.saved_amount for g in list_progress(include_archived=include_archived)), ZERO)


# ---------------------------------------------------------------- 写操作（统一补派生字段）

def create_goal(data: GoalInput) -> GoalProgress:
    return summarize(goal_repo.create_goal(data))


def update_goal(goal_id: int, data: GoalInput) -> GoalProgress:
    return summarize(goal_repo.update_goal(goal_id, data))


def delete_goal(goal_id: int) -> bool:
    return goal_repo.delete_goal(goal_id)


def deposit(goal_id: int, amount: Decimal | int | str) -> GoalProgress:
    return summarize(goal_repo.deposit(goal_id, amount))


def withdraw(goal_id: int, amount: Decimal | int | str) -> GoalProgress:
    return summarize(goal_repo.withdraw(goal_id, amount))

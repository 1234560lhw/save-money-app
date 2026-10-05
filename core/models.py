"""领域模型：与数据库表一一对应的轻量 dataclass。

UI 层只依赖这里的对象，不直接接触 sqlite3.Row。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Mapping, Sequence

from utils.money import ZERO, money_from_db

# ---------------------------------------------------------------- 常量

KIND_INCOME = "income"
KIND_EXPENSE = "expense"
KINDS = (KIND_INCOME, KIND_EXPENSE)

KIND_LABELS = {KIND_INCOME: "收入", KIND_EXPENSE: "支出"}


def kind_label(kind: str) -> str:
    return KIND_LABELS.get(kind, kind)


# ---------------------------------------------------------------- 通用

def _as_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(str(value)[:10])


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    text = str(value).replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
    return datetime.fromisoformat(text)


def _as_decimal(value: Any) -> Decimal:
    return money_from_db(value)


# ---------------------------------------------------------------- 分类

@dataclass(frozen=True)
class Category:
    """收支分类。"""

    id: int
    name: str
    kind: str                      # income | expense
    icon: str = "category"
    color: str = "#607D8B"
    sort_order: int = 0
    is_system: bool = False        # 系统预置分类，默认不允许删除
    created_at: datetime | None = None

    @property
    def kind_label(self) -> str:
        return kind_label(self.kind)

    @property
    def is_income(self) -> bool:
        return self.kind == KIND_INCOME

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Category":
        return cls(
            id=int(row["id"]),
            name=str(row["name"]),
            kind=str(row["kind"]),
            icon=str(row["icon"] or "category"),
            color=str(row["color"] or "#607D8B"),
            sort_order=int(row["sort_order"] or 0),
            is_system=bool(row["is_system"]),
            created_at=_as_datetime(row["created_at"]) if row["created_at"] else None,
        )


# ---------------------------------------------------------------- 流水

@dataclass(frozen=True)
class Transaction:
    """一笔流水。``amount`` 恒为正数，方向由 ``kind`` 决定。"""

    id: int
    kind: str
    amount: Decimal
    category_id: int | None
    happened_on: date
    note: str = ""
    account_id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    # 读表带出来的冗余字段（方便列表直接展示）
    category_name: str | None = None
    category_icon: str | None = None
    category_color: str | None = None
    account_name: str | None = None

    @property
    def is_income(self) -> bool:
        return self.kind == KIND_INCOME

    @property
    def is_expense(self) -> bool:
        return self.kind == KIND_EXPENSE

    @property
    def signed_amount(self) -> Decimal:
        """收入为正、支出为负，可直接用于求总。"""
        return self.amount if self.is_income else -self.amount

    @property
    def category_label(self) -> str:
        return self.category_name or ("未分类" if not self.category_id else "已删除分类")

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Transaction":
        keys = row.keys() if hasattr(row, "keys") else ()
        return cls(
            id=int(row["id"]),
            kind=str(row["kind"]),
            amount=_as_decimal(row["amount"]),
            category_id=int(row["category_id"]) if row["category_id"] is not None else None,
            happened_on=_as_date(row["happened_on"]),
            note=str(row["note"] or ""),
            account_id=int(row["account_id"]) if row["account_id"] is not None else None,
            created_at=_as_datetime(row["created_at"]) if row["created_at"] else None,
            updated_at=_as_datetime(row["updated_at"]) if row["updated_at"] else None,
            category_name=row["category_name"] if "category_name" in keys else None,
            category_icon=row["category_icon"] if "category_icon" in keys else None,
            category_color=row["category_color"] if "category_color" in keys else None,
            account_name=row["account_name"] if "account_name" in keys else None,
        )


# ---------------------------------------------------------------- 账户

@dataclass(frozen=True)
class Account:
    """账户（银行卡 / 现金 / 支付宝…）。第三阶段做多账户统计时启用。"""

    id: int
    name: str
    kind: str = "cash"             # cash | bank | alipay | wechat | other
    initial_balance: Decimal = ZERO
    sort_order: int = 0
    is_archived: bool = False

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Account":
        return cls(
            id=int(row["id"]),
            name=str(row["name"]),
            kind=str(row["kind"] or "cash"),
            initial_balance=_as_decimal(row["initial_balance"]),
            sort_order=int(row["sort_order"] or 0),
            is_archived=bool(row["is_archived"]),
        )


# ---------------------------------------------------------------- 统计结果

@dataclass(frozen=True)
class MonthlySummary:
    """某个月的收支汇总。储蓄率 = 结余 / 收入。"""

    year: int
    month: int
    income: Decimal = ZERO
    expense: Decimal = ZERO

    @property
    def balance(self) -> Decimal:
        return self.income - self.expense

    @property
    def savings_rate(self) -> Decimal | None:
        """0.235 表示 23.5%；没有收入时返回 None（无法计算）。"""
        if self.income <= 0:
            return None
        return self.balance / self.income

    @property
    def expense_ratio(self) -> Decimal | None:
        if self.income <= 0:
            return None
        return self.expense / self.income

    @property
    def label(self) -> str:
        return f"{self.year}年{self.month}月"


@dataclass(frozen=True)
class CategoryStat:
    """按分类聚合的一行统计。"""

    category_id: int | None
    name: str
    color: str
    icon: str
    amount: Decimal
    share: Decimal | None = None   # 占该方向总额的比例

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "CategoryStat":
        return cls(
            category_id=int(row["category_id"]) if row["category_id"] is not None else None,
            name=str(row["name"] or "未分类"),
            color=str(row["color"] or "#90A4AE"),
            icon=str(row["icon"] or "category"),
            amount=_as_decimal(row["amount"]),
        )


@dataclass(frozen=True)
class GoalProgress:
    """存钱目标的实时进度（由 services.goal_service 计算）。"""

    goal_id: int
    name: str
    target_amount: Decimal
    saved_amount: Decimal
    deadline: date | None = None
    note: str = ""
    created_at: datetime | None = None

    # 派生结果
    remaining: Decimal = ZERO
    progress: Decimal = ZERO                    # 0 ~ 1
    months_left: int | None = None
    monthly_suggestion: Decimal = ZERO          # 每月建议存入
    is_done: bool = False
    is_overdue: bool = False

    @property
    def progress_percent(self) -> Decimal:
        return self.progress * 100

    @property
    def days_left(self) -> int | None:
        if self.deadline is None:
            return None
        return (self.deadline - date.today()).days


# ---------------------------------------------------------------- 其它

@dataclass(frozen=True)
class ImportResult:
    """导入/恢复结果，用于设置页反馈。"""

    ok: bool
    message: str
    counts: dict[str, int] = field(default_factory=dict)
    errors: Sequence[str] = ()

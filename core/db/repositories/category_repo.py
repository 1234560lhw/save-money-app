"""分类仓储：增删改查。"""

from __future__ import annotations

import sqlite3

from db.connection import get_connection, transaction
from errors import MoneyError
from models import Category, KIND_EXPENSE, KIND_INCOME

_ALLOWED_KINDS = {KIND_INCOME, KIND_EXPENSE}


class CategoryError(MoneyError):
    """分类操作失败（重名、被引用等），消息可直接展示给用户。"""


def list_categories(kind: str | None = None) -> list[Category]:
    """按方向列出分类；``kind=None`` 时返回全部。"""
    sql = "SELECT * FROM categories"
    params: list[object] = []
    if kind is not None:
        sql += " WHERE kind = ?"
        params.append(kind)
    sql += " ORDER BY kind, sort_order, id"
    rows = get_connection().execute(sql, params).fetchall()
    return [Category.from_row(row) for row in rows]


def get_category(category_id: int) -> Category | None:
    row = get_connection().execute(
        "SELECT * FROM categories WHERE id = ?", (category_id,)
    ).fetchone()
    return Category.from_row(row) if row else None


def find_category_by_name(name: str, kind: str) -> Category | None:
    row = get_connection().execute(
        "SELECT * FROM categories WHERE name = ? AND kind = ?", (name.strip(), kind)
    ).fetchone()
    return Category.from_row(row) if row else None


def create_category(name: str, kind: str, *, icon: str = "category",
                    color: str = "#607D8B", sort_order: int | None = None,
                    is_system: bool = False) -> Category:
    """新建分类；同名同方向会报错。"""
    clean = (name or "").strip()
    if not clean:
        raise CategoryError("分类名称不能为空")
    if len(clean) > 20:
        raise CategoryError("分类名称不能超过 20 个字")
    if kind not in _ALLOWED_KINDS:
        raise CategoryError("分类方向只能是收入或支出")

    if sort_order is None:
        row = get_connection().execute(
            "SELECT COALESCE(MAX(sort_order), 0) + 10 AS next FROM categories WHERE kind = ?",
            (kind,),
        ).fetchone()
        sort_order = int(row["next"])

    try:
        with transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO categories (name, kind, icon, color, sort_order, is_system)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (clean, kind, icon, color, int(sort_order), int(bool(is_system))),
            )
            new_id = int(cur.lastrowid)
    except sqlite3.IntegrityError as exc:
        raise CategoryError(f"「{clean}」已经存在") from exc

    created = get_category(new_id)
    assert created is not None
    return created


def update_category(category_id: int, *, name: str | None = None,
                    icon: str | None = None, color: str | None = None,
                    sort_order: int | None = None) -> Category:
    """修改分类；不允许改动方向（改了会让历史流水对不上）。"""
    current = get_category(category_id)
    if current is None:
        raise CategoryError("分类不存在")

    fields: dict[str, object] = {}
    if name is not None:
        clean = name.strip()
        if not clean:
            raise CategoryError("分类名称不能为空")
        if len(clean) > 20:
            raise CategoryError("分类名称不能超过 20 个字")
        fields["name"] = clean
    if icon is not None:
        fields["icon"] = icon
    if color is not None:
        fields["color"] = color
    if sort_order is not None:
        fields["sort_order"] = int(sort_order)

    if not fields:
        return current

    assignments = ", ".join(f"{key} = ?" for key in fields)
    try:
        with transaction() as conn:
            conn.execute(
                f"UPDATE categories SET {assignments} WHERE id = ?",
                (*fields.values(), category_id),
            )
    except sqlite3.IntegrityError as exc:
        raise CategoryError(f"「{fields.get('name', current.name)}」已经存在") from exc

    updated = get_category(category_id)
    assert updated is not None
    return updated


def count_transactions(category_id: int) -> int:
    """该分类下有多少条流水。"""
    row = get_connection().execute(
        "SELECT COUNT(*) AS n FROM transactions WHERE category_id = ?", (category_id,)
    ).fetchone()
    return int(row["n"])


def delete_category(category_id: int, *, force: bool = False) -> bool:
    """删除分类。

    默认拒绝删除系统预置分类；被流水引用时也拒绝，除非 ``force=True``
    （此时历史流水的分类会置空，金额统计不受影响）。
    """
    current = get_category(category_id)
    if current is None:
        return False
    if current.is_system and not force:
        raise CategoryError(f"「{current.name}」是预置分类，不能删除")

    used = count_transactions(category_id)
    if used and not force:
        raise CategoryError(f"「{current.name}」已被 {used} 条流水使用，不能删除")

    with transaction() as conn:
        if force:
            conn.execute("UPDATE transactions SET category_id = NULL WHERE category_id = ?",
                         (category_id,))
        conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))
    return True


def category_usage() -> dict[int, int]:
    """每个分类的流水条数，列表页展示用。"""
    rows = get_connection().execute(
        "SELECT category_id, COUNT(*) AS n FROM transactions "
        "WHERE category_id IS NOT NULL GROUP BY category_id"
    ).fetchall()
    return {int(row["category_id"]): int(row["n"]) for row in rows}

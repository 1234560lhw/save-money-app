"""数据库包：统一出口。

UI 层只需 ``from db import ...``，不必关心内部文件名。
"""

from __future__ import annotations

import sqlite3

from db.connection import (
    backup_to,
    close_connection,
    connect,
    current_database_path,
    get_connection,
    set_database_path,
    temp_connection,
    transaction,
)
from db.schema import (
    DEFAULT_ACCOUNTS,
    DEFAULT_CATEGORIES,
    SCHEMA_VERSION,
    create_schema,
    get_schema_version,
    initialize_database,
    migrate,
    seed_defaults,
)

_INITIALIZED = False


def init_database(*, force: bool = False, with_seed: bool = True) -> dict[str, object]:
    """初始化数据库（幂等）。应用启动时调用一次即可。"""
    global _INITIALIZED
    if _INITIALIZED and not force:
        return {"schema_version": get_schema_version(get_connection()), "already": True}
    info = initialize_database(get_connection(), with_seed=with_seed)
    _INITIALIZED = True
    return info


def reset_runtime_state() -> None:
    """切换数据库（测试/导入后）时清理进程内状态。"""
    global _INITIALIZED
    _INITIALIZED = False
    close_connection()


def database_stats() -> dict[str, int]:
    """各表条数，设置页展示。"""
    conn = get_connection()
    result: dict[str, int] = {}
    for table in ("categories", "transactions", "goals", "accounts", "budgets", "templates"):
        try:
            row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
            result[table] = int(row["n"])
        except sqlite3.Error:
            result[table] = -1
    return result


__all__ = [
    "init_database",
    "reset_runtime_state",
    "database_stats",
    "get_connection",
    "connect",
    "temp_connection",
    "transaction",
    "close_connection",
    "set_database_path",
    "current_database_path",
    "backup_to",
    "create_schema",
    "migrate",
    "seed_defaults",
    "get_schema_version",
    "SCHEMA_VERSION",
    "DEFAULT_CATEGORIES",
    "DEFAULT_ACCOUNTS",
]

"""数据库表结构、迁移与预置数据。

版本管理
--------
``SCHEMA_VERSION`` 记录结构版本，每次结构变更都要：
1. 提高版本号；
2. 在 ``MIGRATIONS`` 里补一条升级步骤；
3. 同步更新 ``SCHEMA_SQL``，保证全新安装直接得到最新结构。

这样老用户的数据库（第一阶段建的）升级到第二阶段时不会丢数据。
"""

from __future__ import annotations

import sqlite3
from datetime import date

SCHEMA_VERSION = 1

# ---------------------------------------------------------------- 结构定义

SCHEMA_SQL = """
-- 收支分类 ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS categories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    kind        TEXT    NOT NULL CHECK (kind IN ('income', 'expense')),
    icon        TEXT    NOT NULL DEFAULT 'category',
    color       TEXT    NOT NULL DEFAULT '#607D8B',
    sort_order  INTEGER NOT NULL DEFAULT 0,
    is_system   INTEGER NOT NULL DEFAULT 0,     -- 1 = 预置分类，不可删除
    created_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    UNIQUE (name, kind)
);
CREATE INDEX IF NOT EXISTS idx_categories_kind ON categories (kind, sort_order);

-- 账户（第三阶段多账户统计用，MVP 先留结构）-----------------------------
CREATE TABLE IF NOT EXISTS accounts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL UNIQUE,
    kind            TEXT    NOT NULL DEFAULT 'cash',
    initial_balance TEXT    NOT NULL DEFAULT '0.00',
    sort_order      INTEGER NOT NULL DEFAULT 0,
    is_archived     INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- 流水 ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS transactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT    NOT NULL CHECK (kind IN ('income', 'expense')),
    amount      TEXT    NOT NULL CHECK (CAST(amount AS REAL) >= 0),
    category_id INTEGER REFERENCES categories (id) ON DELETE SET NULL,
    account_id  INTEGER REFERENCES accounts (id) ON DELETE SET NULL,
    happened_on TEXT    NOT NULL,                -- YYYY-MM-DD
    note        TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_tx_date  ON transactions (happened_on DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_tx_kind  ON transactions (kind, happened_on);
CREATE INDEX IF NOT EXISTS idx_tx_cat   ON transactions (category_id);

-- 存钱目标 ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS goals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL,
    target_amount   TEXT    NOT NULL CHECK (CAST(target_amount AS REAL) > 0),
    saved_amount    TEXT    NOT NULL DEFAULT '0.00',
    deadline        TEXT,                        -- YYYY-MM-DD，可为空
    note            TEXT    NOT NULL DEFAULT '',
    status          TEXT    NOT NULL DEFAULT 'active'
                            CHECK (status IN ('active', 'done', 'archived')),
    created_at      TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_goals_status ON goals (status);

-- 应用配置（键值对：备份目录、密码哈希、主题等）------------------------
CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL DEFAULT '',
    updated_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- 预算（第二阶段）----------------------------------------------------
CREATE TABLE IF NOT EXISTS budgets (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id  INTEGER NOT NULL REFERENCES categories (id) ON DELETE CASCADE,
    year_month   TEXT    NOT NULL,               -- YYYY-MM
    amount       TEXT    NOT NULL CHECK (CAST(amount AS REAL) >= 0),
    created_at   TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    UNIQUE (category_id, year_month)
);

-- 记账模板（第二阶段：工资一键录入）-----------------------------------
CREATE TABLE IF NOT EXISTS templates (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL,
    kind         TEXT    NOT NULL CHECK (kind IN ('income', 'expense')),
    amount       TEXT    NOT NULL,
    category_id  INTEGER REFERENCES categories (id) ON DELETE SET NULL,
    note         TEXT    NOT NULL DEFAULT '',
    day_of_month INTEGER,
    sort_order   INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);
"""

#: 版本 -> 升级语句列表。第一版就是全新建表，后续版本在此追加。
MIGRATIONS: dict[int, list[str]] = {
    1: [],  # 由 SCHEMA_SQL 建立
}

# ---------------------------------------------------------------- 预置分类

DEFAULT_CATEGORIES: list[tuple[str, str, str, str, int]] = [
    # (name, kind, icon, color, sort_order)
    ("工资", "income", "payments", "#2E7D32", 10),
    ("奖金", "income", "emoji_events", "#43A047", 20),
    ("兼职", "income", "work_outline", "#66BB6A", 30),
    ("理财收益", "income", "trending_up", "#81C784", 40),
    ("红包", "income", "redeem", "#A5D6A7", 50),
    ("其他收入", "income", "more_horiz", "#C8E6C9", 90),

    ("餐饮", "expense", "restaurant", "#E53935", 10),
    ("交通", "expense", "directions_bus", "#FB8C00", 20),
    ("购物", "expense", "shopping_bag", "#8E24AA", 30),
    ("居住", "expense", "home", "#3949AB", 40),
    ("水电燃气", "expense", "bolt", "#1E88E5", 50),
    ("通讯", "expense", "smartphone", "#00ACC1", 60),
    ("医疗", "expense", "local_hospital", "#00897B", 70),
    ("教育", "expense", "school", "#5E35B1", 80),
    ("娱乐", "expense", "sports_esports", "#D81B60", 90),
    ("人情往来", "expense", "card_giftcard", "#F4511E", 100),
    ("其他支出", "expense", "more_horiz", "#757575", 110),
]

DEFAULT_ACCOUNTS: list[tuple[str, str, int]] = [
    ("现金", "cash", 10),
    ("银行卡", "bank", 20),
]


# ---------------------------------------------------------------- 操作

def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row["name"] for row in rows}


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> bool:
    """轻量迁移助手：缺列就补，已存在则跳过。"""
    if column in _table_columns(conn, table):
        return False
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
    return True


def get_schema_version(conn: sqlite3.Connection) -> int:
    try:
        row = conn.execute("PRAGMA user_version").fetchone()
    except sqlite3.Error:
        return 0
    return int(row[0]) if row else 0


def set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(f"PRAGMA user_version = {int(version)}")


def create_schema(conn: sqlite3.Connection) -> None:
    """建表（幂等）。"""
    conn.executescript(SCHEMA_SQL)


def migrate(conn: sqlite3.Connection) -> int:
    """把数据库升到 ``SCHEMA_VERSION``，返回起始版本。"""
    start = get_schema_version(conn)
    if start >= SCHEMA_VERSION:
        return start
    for version in range(start + 1, SCHEMA_VERSION + 1):
        for statement in MIGRATIONS.get(version, []):
            conn.execute(statement)
    set_schema_version(conn, SCHEMA_VERSION)
    return start


def seed_defaults(conn: sqlite3.Connection) -> None:
    """写入预置分类与账户（已存在则不动，用户改过名字也不会被覆盖）。"""
    conn.executemany(
        """
        INSERT INTO categories (name, kind, icon, color, sort_order, is_system)
        VALUES (?, ?, ?, ?, ?, 1)
        ON CONFLICT (name, kind) DO NOTHING
        """,
        DEFAULT_CATEGORIES,
    )
    conn.executemany(
        """
        INSERT INTO accounts (name, kind, sort_order)
        VALUES (?, ?, ?)
        ON CONFLICT (name) DO NOTHING
        """,
        DEFAULT_ACCOUNTS,
    )
    conn.execute(
        """
        INSERT INTO settings (key, value) VALUES ('installed_on', ?)
        ON CONFLICT (key) DO NOTHING
        """,
        (date.today().isoformat(),),
    )


def initialize_database(conn: sqlite3.Connection, *, with_seed: bool = True) -> dict[str, object]:
    """初始化数据库：建表 -> 迁移 -> 预置数据。可重复调用。"""
    before = get_schema_version(conn)
    create_schema(conn)
    migrate(conn)
    if with_seed:
        seed_defaults(conn)
    return {
        "schema_version": SCHEMA_VERSION,
        "previous_version": before,
        "migrated": before != SCHEMA_VERSION,
        "seeded": with_seed,
    }

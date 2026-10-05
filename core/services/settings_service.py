"""应用配置读写（键值对表 settings）。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation

from db.connection import get_connection, transaction
from utils.money import CENTS, ROUND_HALF_UP, ZERO

# 常用键名集中定义，避免各处写字符串写错
KEY_THEME_MODE = "theme_mode"            # light | dark | system
KEY_CURRENCY_SYMBOL = "currency_symbol"  # 默认 ¥
KEY_PASSWORD_HASH = "password_hash"      # 第二阶段：密码锁
KEY_PASSWORD_SALT = "password_salt"
KEY_LAST_BACKUP_AT = "last_backup_at"
KEY_WEEK_START = "week_start"            # 1=周一
KEY_DEFAULT_ACCOUNT = "default_account_id"
#: 初始财产：第一次使用时手里已有的钱，计入总存款
KEY_STARTING_BALANCE = "starting_balance"
KEY_STARTING_BALANCE_SET_AT = "starting_balance_set_at"

DEFAULTS: dict[str, str] = {
    KEY_THEME_MODE: "dark",
    KEY_CURRENCY_SYMBOL: "¥",
    KEY_WEEK_START: "1",
    KEY_LAST_BACKUP_AT: "",
    KEY_STARTING_BALANCE: "0.00",
}


def get_value(key: str, default: str | None = None) -> str | None:
    row = get_connection().execute(
        "SELECT value FROM settings WHERE key = ?", (key,)
    ).fetchone()
    if row is not None:
        return str(row["value"])
    if default is not None:
        return default
    return DEFAULTS.get(key)


def set_value(key: str, value: str) -> None:
    with transaction() as conn:
        conn.execute(
            """
            INSERT INTO settings (key, value, updated_at)
            VALUES (?, ?, datetime('now', 'localtime'))
            ON CONFLICT (key) DO UPDATE
               SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (key, str(value)),
        )


def get_int(key: str, default: int = 0) -> int:
    raw = get_value(key)
    try:
        return int(raw) if raw not in (None, "") else default
    except (TypeError, ValueError):
        return default


def all_settings() -> dict[str, str]:
    rows = get_connection().execute("SELECT key, value FROM settings").fetchall()
    return {str(row["key"]): str(row["value"]) for row in rows}


def touch_backup_time() -> None:
    set_value(KEY_LAST_BACKUP_AT, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


def last_backup_at() -> str | None:
    value = get_value(KEY_LAST_BACKUP_AT)
    return value or None


# ================================================================ 初始财产

def get_starting_balance() -> Decimal:
    """第一次使用前手里已有的钱（默认 0）。

    值存在 settings 键值表里，不需要给数据库加字段，
    因此老用户的数据库直接就能用，不用做结构迁移。
    """
    raw = get_value(KEY_STARTING_BALANCE) or "0"
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return ZERO
    if value.is_nan() or value.is_infinite():
        return ZERO
    # 初始财产允许为负（例如信用卡欠款），但不接受离谱的精度
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


def set_starting_balance(value: Decimal | int | str | None) -> Decimal:
    """写入初始财产。传 None 或空字符串视为清 0。

    校验交给调用方用 ``parse_money`` 做（那里有统一的中文提示），
    这里只保证写进去的一定是合法十进制字符串。
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        amount = ZERO
    else:
        try:
            if isinstance(value, Decimal):
                amount = value
            else:
                amount = Decimal(str(value).strip().replace(",", "").replace("，", ""))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("初始财产必须是数字") from exc
        if amount.is_nan() or amount.is_infinite():
            raise ValueError("初始财产必须是有效数字")
        amount = amount.quantize(CENTS, rounding=ROUND_HALF_UP)

    set_value(KEY_STARTING_BALANCE, str(amount))
    set_value(KEY_STARTING_BALANCE_SET_AT, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    return amount


def clear_starting_balance() -> Decimal:
    """把初始财产归 0。"""
    return set_starting_balance(None)


def starting_balance_set_at() -> str | None:
    """初始财产的设置时间（没设过返回 None）。"""
    value = get_value(KEY_STARTING_BALANCE_SET_AT)
    return value or None

"""金额与比率工具。

所有金额统一使用 ``decimal.Decimal`` 表示，数据库以 TEXT 存储十进制字符串
（例如 ``"1234.56"``），彻底避免 float 的二进制误差在记账软件里累加出错。
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext

from errors import MoneyError

#: 金额精度：分
CENTS = Decimal("0.01")
#: 金额量化规则
ROUNDING = ROUND_HALF_UP

ZERO = Decimal("0.00")

__all__ = [
    "MoneyError",
    "CENTS",
    "ROUNDING",
    "ZERO",
    "quantize_money",
    "to_decimal",
    "parse_money",
    "money_to_db",
    "money_from_db",
    "format_money",
    "format_percent",
    "safe_ratio",
    "split_amount",
]


def quantize_money(value: Decimal | int | str) -> Decimal:
    """把数值统一到两位小数。"""
    if not isinstance(value, Decimal):
        value = to_decimal(value)
    return value.quantize(CENTS, rounding=ROUNDING)


def to_decimal(value: Decimal | int | float | str) -> Decimal:
    """尽量把任意输入转成 Decimal；float 先转成字符串再转，避免精度污染。"""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise MoneyError("布尔值不能作为金额")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(repr(value))
    if isinstance(value, str):
        return Decimal(value.strip())
    raise MoneyError(f"不支持的金额类型: {type(value).__name__}")


def parse_money(raw: str | int | float | Decimal | None, *,
                field: str = "金额",
                allow_zero: bool = False,
                allow_negative: bool = False,
                max_value: Decimal | None = Decimal("99999999.99")) -> Decimal:
    """把用户输入解析成合法金额，非法输入一律抛出 :class:`MoneyError`。

    这是表单校验的唯一入口，UI 层只负责把提示语展示出来。
    """
    if raw is None:
        raise MoneyError(f"{field}不能为空")

    # 统一成字符串再校验，这样 int / Decimal / float 输入与文本框输入
    # 走完全相同的规则（负数、非数字都在这里被挡下）。
    text = str(raw).strip()
    if not text:
        raise MoneyError(f"{field}不能为空")
    # 容忍常见的全角/千分位/货币符号输入
    text = (text.replace(",", "").replace("，", "").replace(" ", "")
                .replace("￥", "").replace("¥", "").replace("$", ""))
    text = text.replace("。", ".").replace("．", ".")
    if text in {"", "-", "+", "."}:
        raise MoneyError(f"{field}必须是数字")
    if text.startswith("-"):
        if not allow_negative:
            raise MoneyError(f"{field}不能为负数")

    try:
        value = to_decimal(text)
    except (InvalidOperation, ArithmeticError, MoneyError) as exc:
        raise MoneyError(f"{field}必须是数字") from exc

    if value.is_nan() or value.is_infinite():
        raise MoneyError(f"{field}必须是有效数字")
    if value < 0 and not allow_negative:
        raise MoneyError(f"{field}不能为负数")
    if value == 0 and not allow_zero:
        raise MoneyError(f"{field}必须大于 0")

    value = quantize_money(value)
    if max_value is not None and abs(value) > max_value:
        raise MoneyError(f"{field}超出上限（最大 {max_value}）")
    return value


def money_to_db(value: Decimal | int | str) -> str:
    """转成数据库存储用的十进制字符串。"""
    return str(quantize_money(to_decimal(value)))


def money_from_db(value: str | int | float | Decimal | None) -> Decimal:
    """从数据库读回金额；NULL 视为 0。"""
    if value is None or value == "":
        return ZERO
    return quantize_money(to_decimal(value))


def format_money(value: Decimal | int | str | None, *,
                 symbol: str = "¥",
                 thousands: bool = True,
                 signed: bool = False) -> str:
    """格式化成给人看的金额字符串，例如 ``¥1,234.56``。"""
    amount = money_from_db(value)
    body = f"{abs(amount):,.2f}" if thousands else f"{abs(amount):.2f}"
    sign = ""
    if amount < 0:
        sign = "-"
    elif signed and amount > 0:
        sign = "+"
    return f"{sign}{symbol}{body}"


def format_percent(ratio: Decimal | None, *, digits: int = 1) -> str:
    """把比率（0.235）格式化成百分比字符串（``23.5%``）。"""
    if ratio is None:
        return "—"
    quant = Decimal(1).scaleb(-digits)
    pct = (to_decimal(ratio) * 100).quantize(quant, rounding=ROUNDING)
    return f"{pct}%"


def safe_ratio(numerator: Decimal | int | str,
               denominator: Decimal | int | str) -> Decimal | None:
    """安全除法：分母为 0 时返回 ``None``（表示"无法计算"），而不是抛异常。"""
    num = to_decimal(numerator)
    den = to_decimal(denominator)
    if den == 0:
        return None
    with localcontext() as ctx:
        ctx.prec = 28
        return num / den


def split_amount(total: Decimal | int | str, parts: int) -> list[Decimal]:
    """把金额均分成 ``parts`` 份，余数补到最后一份，保证合计不变。"""
    if parts <= 0:
        raise MoneyError("份数必须大于 0")
    total = quantize_money(to_decimal(total))
    base = quantize_money(total / parts)
    result = [base] * (parts - 1)
    result.append(quantize_money(total - base * (parts - 1)))
    return result

"""统一业务异常。

为什么要单独放一个模块
----------------------
金额解析在 ``utils.money``，仓储校验在 ``db.repositories``，业务规则在
``services``。三者互相引用会成环，所以把异常基类抽到这里。

所有"提示给用户看"的错误都继承 :class:`AppError`，UI 层只需::

    try:
        ...
    except AppError as exc:
        show_message(str(exc))

就能拿到一句中文说明，不用分别处理一堆异常类型。
"""

from __future__ import annotations


class AppError(ValueError):
    """应用内所有可预期错误的基类。

    继承 ``ValueError`` 是为了让"没特意捕获"的调用处也能被当作参数错误处理。
    """


class MoneyError(AppError):
    """金额 / 比率解析失败。"""


class ValidationError(AppError):
    """通用输入校验失败。"""


__all__ = ["AppError", "MoneyError", "ValidationError"]

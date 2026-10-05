"""存钱罐应用 · 共享核心层。

只放与界面无关的代码：数据模型、SQLite 数据层、业务服务、通用工具。
桌面端（apps/desktop）和手机端（apps/mobile）都引用本层，
因此两端的数据口径与计算结果永远一致。

导入约定
--------
启动入口会把本目录（``core/``）加入 ``sys.path``，
所以内部一律用「顶层包名」导入，例如::

    from db.connection import get_connection
    from services.stats_service import total_balance
    from utils.money import format_money

详见 docs/目录结构.md。
"""

from __future__ import annotations

__version__ = "0.1.0"
__all__ = ["__version__"]

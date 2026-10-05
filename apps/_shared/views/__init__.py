"""页面集合。

* :class:`HomeView`              首页仪表盘
* :class:`AddTransactionView`     记一笔
* :class:`TransactionListView`    流水列表
* :class:`SettingsView`           设置
"""

from _shared.views.add_transaction import AddTransactionView
from _shared.views.base import BaseView
from _shared.views.home import HomeView
from _shared.views.settings import SettingsView
from _shared.views.transactions import TransactionListView

__all__ = [
    "BaseView",
    "HomeView",
    "AddTransactionView",
    "TransactionListView",
    "SettingsView",
]

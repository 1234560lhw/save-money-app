"""业务服务层：所有"钱怎么算"的逻辑都在这里。

UI 层不允许自己写金额公式，只能调用本层函数，保证桌面端与手机端
计算结果完全一致。
"""

from services import backup_service, goal_service, settings_service, stats_service

__all__ = ["backup_service", "goal_service", "settings_service", "stats_service"]

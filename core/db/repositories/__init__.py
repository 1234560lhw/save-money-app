"""数据仓储层。

每个仓储只管一张表的增删改查与校验，不做跨表业务计算
（跨表计算放在 ``services`` 里）。
"""

from db.repositories import category_repo, goal_repo, transaction_repo

__all__ = ["category_repo", "goal_repo", "transaction_repo"]

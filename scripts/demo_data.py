"""演示数据：开发期一键造一批流水与目标，方便看界面效果。

只在 ``--demo`` / ``seed_demo=True`` 时调用，普通使用不会写入任何假数据。

    .venv\\Scripts\\python.exe scripts\\demo_data.py          # 直接给默认库写入
    .venv\\Scripts\\python.exe scripts\\demo_data.py --reset  # 先清空再写入

调用方式（供 bootstrap 使用）::

    from scripts.demo_data import seed_demo_data
    seed_demo_data()
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
for _path in (str(PROJECT_ROOT / "core"), str(PROJECT_ROOT / "apps")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from db.connection import get_connection, transaction  # noqa: E402
from db.repositories import category_repo, transaction_repo  # noqa: E402
from db.repositories.transaction_repo import TransactionInput  # noqa: E402
from models import KIND_EXPENSE, KIND_INCOME  # noqa: E402
from services.goal_service import GoalInput  # noqa: E402
from services import goal_service  # noqa: E402

#: (分类名, 金额区间, 备注候选)
EXPENSE_PLAN = [
    ("餐饮", (15, 120), ["早饭", "午饭", "晚饭", "外卖", "和同事聚餐"]),
    ("交通", (4, 60), ["地铁", "公交", "打车", "加油"]),
    ("购物", (30, 600), ["日用品", "衣服", "数码配件"]),
    ("水电燃气", (50, 300), ["电费", "水费", "燃气费"]),
    ("通讯", (30, 130), ["话费", "宽带"]),
    ("娱乐", (20, 300), ["电影", "游戏", "周末出游"]),
    ("医疗", (30, 500), ["感冒药", "看牙"]),
    ("人情往来", (50, 800), ["随礼", "送礼"]),
]

GOALS = [
    ("旅行基金", "12000", "3500", "旅行"),
    ("换电脑", "9000", "1200", "数码"),
    ("应急储备金", "30000", "18000", "安全垫"),
]


def seed_demo_data(*, months: int = 3, reset: bool = False) -> dict[str, int]:
    """写入演示数据，返回写入条数。"""
    if reset:
        with transaction() as conn:
            conn.execute("DELETE FROM transactions")
            conn.execute("DELETE FROM goals")

    rng = random.Random(20250801)   # 固定种子，多次运行结果一致
    today = date.today()
    salary = category_repo.find_category_by_name("工资", KIND_INCOME)
    bonus = category_repo.find_category_by_name("奖金", KIND_INCOME)
    inserted = 0

    for offset in range(months - 1, -1, -1):
        year = today.year
        month = today.month - offset
        while month <= 0:
            month += 12
            year -= 1

        # 每月工资
        if salary:
            day = min(10, 28)
            transaction_repo.create_transaction(TransactionInput(
                kind=KIND_INCOME, amount="12000",
                category_id=salary.id, happened_on=date(year, month, day),
                note=f"{month}月工资",
            ))
            inserted += 1

        # 偶尔发奖金
        if bonus and rng.random() < 0.5:
            transaction_repo.create_transaction(TransactionInput(
                kind=KIND_INCOME, amount=str(rng.choice([500, 1000, 2000])),
                category_id=bonus.id, happened_on=date(year, month, 15),
                note="项目奖金",
            ))
            inserted += 1

        # 当月日常支出
        for name, (low, high), notes in EXPENSE_PLAN:
            category = category_repo.find_category_by_name(name, KIND_EXPENSE)
            if category is None:
                continue
            for _ in range(rng.randint(1, 3)):
                amount = rng.randint(low, high)
                day = rng.randint(1, 28)
                transaction_repo.create_transaction(TransactionInput(
                    kind=KIND_EXPENSE, amount=str(amount),
                    category_id=category.id, happened_on=date(year, month, day),
                    note=rng.choice(notes),
                ))
                inserted += 1

    existing = {goal.name for goal in goal_service.list_progress(include_archived=True)}
    for name, target, saved, note in GOALS:
        if name in existing:
            continue
        goal_service.create_goal(GoalInput(
            name=name, target_amount=target, saved_amount=saved,
            deadline=today + timedelta(days=180), note=note,
        ))

    return {"transactions": inserted, "goals": len(GOALS)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="写入演示数据")
    parser.add_argument("--reset", action="store_true", help="先清空流水与目标")
    parser.add_argument("--months", type=int, default=3, help="生成最近几个月的数据")
    args = parser.parse_args(argv)

    from bootstrap import bootstrap

    info = bootstrap()
    result = seed_demo_data(months=args.months, reset=args.reset)
    print(f"[demo] 数据库：{info['paths']['db_path']}")
    print(f"[demo] 已写入 {result['transactions']} 笔流水、{result['goals']} 个目标")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

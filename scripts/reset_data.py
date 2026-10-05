"""账本数据管理：清空 / 造演示数据。

用法::

    # 看看当前有多少数据（不清）
    .venv\\Scripts\\python.exe scripts\\reset_data.py --status

    # 清空正式数据（数据目录 %APPDATA%\\SaveMoneyApp）
    .venv\\Scripts\\python.exe scripts\\reset_data.py --clear

    # 清空开发数据（.devdata）
    .venv\\Scripts\\python.exe scripts\\reset_data.py --clear --dev

    # 两个都清（正式 + 开发）
    .venv\\Scripts\\python.exe scripts\\reset_data.py --clear --all

    # 清空并顺便造一批演示数据（只是想看效果时用）
    .venv\\Scripts\\python.exe scripts\\reset_data.py --clear --all --demo

清空前会自动导出一份快照到备份目录，清错了可以在「设置 - 导入备份」里恢复。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
for _path in (str(PROJECT_ROOT / "core"), str(PROJECT_ROOT / "apps")):
    if _path not in sys.path:
        sys.path.insert(0, _path)


def _describe(counts: dict[str, int], db_file: str) -> str:
    return (f"数据库：{db_file}\n"
            f"    流水 {counts.get('transactions', 0)} 笔 ｜ "
            f"存钱目标 {counts.get('goals', 0)} 个 ｜ "
            f"分类 {counts.get('categories', 0)} 个（其中自定义 "
            f"{max(counts.get('categories', 0) - counts.get('categories_kept', 0), 0)} 个）")


def handle(target: str, *, clear: bool, demo: bool, keep_backups: bool) -> int:
    """对某个数据目录执行「查看 / 清空 / 造数据」。"""
    import os

    from bootstrap import bootstrap
    from db import database_stats
    from utils import paths

    label = {"app": "正式数据", "dev": "开发数据(.devdata)", "mobile": "开发数据(.devdata/mobile)"}[target]

    if target == "app":
        os.environ.pop("SAVE_MONEY_DATA_DIR", None)
        os.environ.pop("SAVE_MONEY_DB_FILE", None)
    elif target == "dev":
        os.environ["SAVE_MONEY_DATA_DIR"] = str(PROJECT_ROOT / ".devdata")
        os.environ.pop("SAVE_MONEY_DB_FILE", None)
    else:
        os.environ["SAVE_MONEY_DATA_DIR"] = str(PROJECT_ROOT / ".devdata" / "mobile")
        os.environ.pop("SAVE_MONEY_DB_FILE", None)

    info = bootstrap()
    db_file = info["paths"]["db_path"]
    print(f"\n=== {label} ===")
    print(f"  目录：{info['paths']['data_dir']}")
    print(f"  库文件：{db_file}")

    stats = database_stats()
    from services import goal_service

    print(f"  现状：流水 {stats.get('transactions', 0)} 笔 ｜ "
          f"目标 {stats.get('goals', 0)} 个 ｜ 分类 {stats.get('categories', 0)} 个")

    if not clear:
        return 0

    from services import backup_service

    counts = backup_service.reset_all_data(keep_backups=keep_backups)
    print(f"  已清空：流水 {counts.get('transactions', 0)} 笔、"
          f"目标 {counts.get('goals', 0)} 个、"
          f"自定义分类 {max(counts.get('categories', 0) - counts.get('categories_kept', 0), 0)} 个")
    print(f"  保留预置分类 {counts.get('categories_kept', 0)} 个")
    print(f"  清空后：流水 {database_stats().get('transactions', 0)} 笔 ｜ "
          f"目标 {len(goal_service.list_progress(include_archived=True))} 个")

    if demo:
        from scripts.demo_data import seed_demo_data

        result = seed_demo_data(reset=False)
        print(f"  已写入演示数据：流水 {result['transactions']} 笔、目标 {result['goals']} 个")

    print(f"  备份目录：{paths.backup_dir()}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="账本数据清空 / 造演示数据")
    parser.add_argument("--clear", action="store_true", help="执行清空（不加此参数只查看现状）")
    parser.add_argument("--status", action="store_true", help="只查看现状")
    parser.add_argument("--dev", action="store_true", help="只处理开发数据 .devdata")
    parser.add_argument("--mobile", action="store_true", help="只处理 .devdata/mobile")
    parser.add_argument("--all", action="store_true", help="正式数据 + 开发数据 全部处理")
    parser.add_argument("--demo", action="store_true", help="清空后写入演示数据")
    parser.add_argument("--keep-backups", action="store_true", help="保留历史备份文件")
    args = parser.parse_args(argv)

    if args.all:
        targets = ["app", "dev", "mobile"]
    elif args.dev:
        targets = ["dev"]
    elif args.mobile:
        targets = ["mobile"]
    else:
        targets = ["app"]

    print("=" * 64)
    print("存钱罐 · 数据管理" + ("（清空模式）" if args.clear else "（只查看，未改动）"))
    print("=" * 64)

    rc = 0
    for target in targets:
        try:
            rc |= handle(target, clear=args.clear, demo=args.demo,
                         keep_backups=args.keep_backups)
        except Exception as exc:  # noqa: BLE001
            import traceback

            print(f"\n!!! 处理 {target} 失败：{type(exc).__name__}: {exc}")
            traceback.print_exc()
            rc = 1
    print()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())

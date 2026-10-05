"""备份 / 迁移服务：导出数据库、导出 CSV、导入恢复。

跨设备迁移的推荐做法
--------------------
1. 旧设备「设置 - 数据备份 - 导出数据库」，得到一个 ``.db`` 文件；
2. 把文件传到新设备（微信/网盘/U 盘都行）；
3. 新设备「设置 - 数据备份 - 导入备份」选中该文件。

导入时会先把当前数据自动存一份"导入前快照"，选错了也能退回去。
"""

from __future__ import annotations

import csv
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable

from db import reset_runtime_state
from db.connection import (
    backup_to,
    close_connection,
    current_database_path,
    get_connection,
    temp_connection,
    transaction,
)
from db.repositories import transaction_repo
from db.schema import seed_defaults
from models import ImportResult
from utils.paths import backup_dir
from utils.money import money_from_db


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


# ---------------------------------------------------------------- 导出

def export_database(target: str | Path | None = None) -> Path:
    """导出完整数据库（热备份，使用中也能导出）。"""
    if target is None:
        target = backup_dir() / f"pocket_money_{timestamp()}.db"
    return backup_to(target)


def export_transactions_csv(target: str | Path | None = None,
                            *, year: int | None = None,
                            month: int | None = None) -> Path:
    """导出流水为 CSV。

    用 ``utf-8-sig`` 编码，Excel 双击打开不乱码。
    """
    if target is None:
        suffix = f"_{year:04d}{month:02d}" if year and month else ""
        target = backup_dir() / f"transactions{suffix}_{timestamp()}.csv"
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)

    flt = transaction_repo.TransactionFilter(year=year, month=month)
    rows = transaction_repo.list_transactions(flt)

    with target.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(["日期", "类型", "金额", "分类", "备注", "录入时间"])
        for tx in rows:
            writer.writerow([
                tx.happened_on.isoformat(),
                "收入" if tx.is_income else "支出",
                f"{tx.amount:.2f}",
                tx.category_label,
                tx.note,
                tx.created_at.strftime("%Y-%m-%d %H:%M:%S") if tx.created_at else "",
            ])
    return target


def export_goals_csv(target: str | Path | None = None) -> Path:
    """导出存钱目标为 CSV。"""
    from services.goal_service import list_progress

    if target is None:
        target = backup_dir() / f"goals_{timestamp()}.csv"
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)

    with target.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(["目标名称", "目标金额", "已存金额", "进度", "差额",
                         "截止日期", "每月建议", "状态"])
        for goal in list_progress(include_archived=True):
            status = "已达标" if goal.is_done else ("已逾期" if goal.is_overdue else "进行中")
            writer.writerow([
                goal.name,
                f"{goal.target_amount:.2f}",
                f"{goal.saved_amount:.2f}",
                f"{goal.progress_percent:.1f}%",
                f"{goal.remaining:.2f}",
                goal.deadline.isoformat() if goal.deadline else "",
                f"{goal.monthly_suggestion:.2f}",
                status,
            ])
    return target


# ---------------------------------------------------------------- 校验与导入

REQUIRED_TABLES = {"categories", "transactions", "goals"}


def inspect_database(path: str | Path) -> dict[str, object]:
    """检查一个 .db 文件是不是本应用的备份。"""
    path = Path(path)
    if not path.is_file():
        return {"ok": False, "message": "文件不存在"}

    try:
        with temp_connection(path) as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
            tables = {row["name"] for row in rows}
            missing = REQUIRED_TABLES - tables
            if missing:
                return {
                    "ok": False,
                    "message": f"不是本应用的备份文件（缺少数据表：{'、'.join(sorted(missing))}）",
                }
            counts = {
                table: int(conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"])
                for table in sorted(REQUIRED_TABLES)
            }
            version_row = conn.execute("PRAGMA user_version").fetchone()
    except sqlite3.Error as exc:
        return {"ok": False, "message": f"文件无法读取：{exc}"}

    return {
        "ok": True,
        "message": "备份文件校验通过",
        "counts": counts,
        "schema_version": int(version_row[0]) if version_row else 0,
        "path": str(path),
    }


def import_database(source: str | Path, *, keep_snapshot: bool = True) -> ImportResult:
    """用备份文件覆盖当前数据库。

    步骤：校验 -> 给当前数据存快照 -> 关闭连接 -> 覆盖文件 -> 重新初始化。
    """
    source = Path(source)
    check = inspect_database(source)
    if not check.get("ok"):
        return ImportResult(ok=False, message=str(check.get("message", "备份文件无效")))

    target = Path(current_database_path())
    snapshot: Path | None = None
    if keep_snapshot and target.exists():
        snapshot = backup_dir() / f"before_import_{timestamp()}.db"
        backup_to(snapshot)

    close_connection()
    reset_runtime_state()
    try:
        # WAL 模式下 -wal/-shm 残留会让旧数据混进来，一起清掉
        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(target) + suffix)
            if sidecar.exists():
                sidecar.unlink()
        shutil.copy2(source, target)
    except OSError as exc:
        return ImportResult(ok=False, message=f"写入失败：{exc}")

    from db import init_database  # 延迟导入，避免循环

    info = init_database(force=True)

    counts = {str(k): int(v) for k, v in dict(check.get("counts", {})).items()}
    message = "导入成功"
    if snapshot:
        message += f"；导入前数据已存快照：{snapshot.name}"
    if info.get("migrated"):
        message += "（已完成数据结构升级）"
    return ImportResult(ok=True, message=message, counts=counts)


def delete_all_transactions() -> int:
    """清空流水（危险操作，界面二次确认后调用）。"""
    conn = get_connection()
    with conn:
        cur = conn.execute("DELETE FROM transactions")
    return int(cur.rowcount)


def reset_all_data(*, keep_backups: bool = True, snapshot: bool = True) -> dict[str, int]:
    """把账本恢复成"刚装上"的样子，用于正式使用前清掉演示/测试数据。

    会清空：流水、存钱目标、自定义分类、预算、记账模板、账户。
    会保留：预置分类（餐饮/交通/工资…）、应用设置。

    ``snapshot=True`` 时会先把当前数据导出一份到备份目录，
    万一清错了还能在「设置 - 导入备份」里恢复。返回被清空的条数。
    """
    conn = get_connection()
    counts: dict[str, int] = {}
    # 统计清空前的条数，方便界面反馈
    for table in ("transactions", "goals", "budgets", "templates", "accounts", "categories"):
        try:
            row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
            counts[table] = int(row["n"])
        except sqlite3.Error:
            counts[table] = 0

    if snapshot:
        try:
            export_database(backup_dir() / f"before_reset_{timestamp()}.db")
        except (OSError, sqlite3.Error):
            # 快照失败不应阻断清空（可能是首次使用、还没有数据）
            pass

    # 顺序很重要：先删引用方，再删被引用方，避免外键约束报错
    with transaction() as tx:
        tx.execute("DELETE FROM transactions")
        tx.execute("DELETE FROM budgets")
        tx.execute("DELETE FROM templates")
        tx.execute("DELETE FROM goals")
        tx.execute("DELETE FROM accounts")
        tx.execute("DELETE FROM categories WHERE is_system = 0")

    # 清空后补回预置账户（用户可能把默认账户删掉了）
    seed_defaults(conn)

    if not keep_backups:
        for path in backup_dir().glob("*"):
            try:
                path.unlink()
            except OSError:
                pass

    counts["categories_kept"] = int(
        conn.execute("SELECT COUNT(*) AS n FROM categories").fetchone()["n"]
    )

    # 初始财产也一起归 0，这样"清空所有数据"之后总存款真的是 0
    from services import settings_service

    settings_service.clear_starting_balance()
    return counts


def prune_backups(keep: int = 10) -> int:
    """只保留最近 ``keep`` 个备份，返回删除数量。"""
    files: Iterable[Path] = sorted(
        (p for p in backup_dir().glob("*") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    removed = 0
    for index, path in enumerate(files):
        if index >= keep:
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
    return removed

"""SQLite 连接管理。

设计要点
--------
* 桌面端与手机端共用同一套数据层，只是数据库路径不同（见 utils/paths.py）；
* 打开连接即设置 ``foreign_keys``、``journal_mode=WAL``、``busy_timeout``，
  避免并发读写时的 "database is locked"；
* 每线程一个连接（sqlite3 连接对象不跨线程共享），由 ``threading.local`` 管理；
* 支持 ``:memory:`` 与临时文件，方便测试。
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from utils.paths import db_path

_local = threading.local()
_override_path: str | None = None
_lock = threading.RLock()


def set_database_path(path: str | Path | None) -> None:
    """覆盖数据库位置（测试或多账户场景使用），并关闭已有连接。"""
    global _override_path
    close_connection()
    _override_path = None if path is None else str(path)


def current_database_path() -> str:
    """当前生效的数据库文件路径。"""
    if _override_path is not None:
        return _override_path
    return str(db_path())


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    """新建（或复用）一个已配置好的连接。"""
    target = str(path) if path is not None else current_database_path()
    if target != ":memory:":
        Path(target).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(target, timeout=15.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 15000")
    if target != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def get_connection() -> sqlite3.Connection:
    """取得当前线程的连接（惰性建立）。"""
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = connect()
        _local.conn = conn
    return conn


def close_connection() -> None:
    """关闭当前线程的连接。"""
    conn = getattr(_local, "conn", None)
    if conn is not None:
        try:
            conn.close()
        finally:
            _local.conn = None


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    """显式事务；异常时回滚，正常时提交。"""
    conn = get_connection()
    with _lock:
        conn.execute("BEGIN")
        try:
            yield conn
        except Exception:
            conn.execute("ROLLBACK")
            raise
        else:
            conn.execute("COMMIT")


@contextmanager
def temp_connection(path: str | Path) -> Iterator[sqlite3.Connection]:
    """打开一个独立的临时连接（备份、导入导出、测试用）。

    ``connect()`` 本身就可能抛错（例如文件不是数据库），因此必须在
    try 之外先建立连接、进入 try 之后再关闭，避免连接泄漏导致
    Windows 上文件被占用无法删除。
    """
    conn = connect(path)
    try:
        yield conn
    finally:
        conn.close()


def backup_to(target: str | Path) -> Path:
    """用 SQLite 官方 backup API 做热备份，生成一个完整可用的 .db 文件。"""
    target_path = Path(target)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    source = get_connection()
    dest = sqlite3.connect(str(target_path))
    try:
        with dest:
            source.backup(dest)
    finally:
        dest.close()
    return target_path

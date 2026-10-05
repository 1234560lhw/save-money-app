"""运行期路径解析：一处决定数据放哪里。

目录策略
--------
* 桌面端：Windows ``%APPDATA%\\SaveMoneyApp``、macOS ``~/Library/Application Support/SaveMoneyApp``、
  Linux ``~/.local/share/SaveMoneyApp``；
* 手机端（Flet 打包成 APK 后）：使用应用私有目录 ``FLET_APP_STORAGE_DATA``；
* 两者都可用环境变量覆盖，测试用 ``SAVE_MONEY_DATA_DIR`` 指到临时目录。

桌面与手机各自保存自己的数据库文件，跨设备靠"导出备份 / 导入备份"迁移
（见 services/backup_service.py）。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "SaveMoneyApp"
DB_FILENAME = "pocket_money.db"
#: 应用显示名（窗口标题、关于页等）
APP_TITLE = "Flipped的存钱罐"

_ENV_DATA_DIR = "SAVE_MONEY_DATA_DIR"
_ENV_DB_FILE = "SAVE_MONEY_DB_FILE"


class DataDirError(RuntimeError):
    """所有候选数据目录都不可写（权限、组策略、安全软件拦截等）。"""

    def __init__(self, message: str, *, tried: list[str] | None = None):
        super().__init__(message)
        self.tried = tried or []


def asset_path(*parts: str) -> Path:
    """定位静态资源（图标等），源码运行与打包后都能用。

    打包成 exe 之后，``__file__`` 的层级关系会变，PyInstaller 会把数据
    解到 ``sys._MEIPASS``；Flet 打包（flet build）则把 assets 放在
    可执行文件旁边。这里把三种情况都覆盖掉，调用方不用关心。
    """
    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "assets")
    if is_frozen():
        candidates.append(Path(sys.executable).parent / "assets")
    candidates.append(project_root() / "assets")

    for base in candidates:
        candidate = base.joinpath(*parts)
        if candidate.exists():
            return candidate
    # 都不存在时返回源码目录下的路径，让报错信息更直观
    return project_root() / "assets" / Path(*parts)


def is_mobile() -> bool:
    """是否运行在手机端（Android / iOS）。"""
    return bool(os.environ.get("FLET_APP_STORAGE_DATA")) or sys.platform in {"android", "ios"}


def is_frozen() -> bool:
    """是否运行在打包后的可执行文件里。"""
    return bool(getattr(sys, "frozen", False))


def project_root() -> Path:
    """源码根目录（仅开发期使用）。"""
    return Path(__file__).resolve().parents[2]


def _is_writable(directory: Path) -> bool:
    """真正**写一个文件**来判断目录可不可写。

    不用 ``os.access``：Windows 上它只看只读属性，不看 ACL，
    结果会说"可写"然后真正写入时抛 PermissionError（踩过这个坑）。
    """
    probe = directory / ".write_test"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def _data_dir_candidates() -> list[tuple[str, Path]]:
    """按优先级列出数据目录候选：``(说明, 路径)``。"""
    if is_mobile():
        mobile_root = os.environ.get("FLET_APP_STORAGE_DATA")
        return [("应用私有目录", Path(mobile_root) if mobile_root else Path.cwd())]

    override = os.environ.get(_ENV_DATA_DIR)
    if override:
        return [("环境变量指定", Path(override).expanduser())]

    home = Path.home()
    if sys.platform.startswith("win"):
        roaming = os.environ.get("APPDATA") or str(home / "AppData" / "Roaming")
        local = os.environ.get("LOCALAPPDATA") or str(home / "AppData" / "Local")
        candidates = [
            ("用户数据目录(Roaming)", Path(roaming) / APP_NAME),
            ("本地数据目录(Local)", Path(local) / APP_NAME),
        ]
    elif sys.platform == "darwin":
        candidates = [("用户数据目录", home / "Library" / "Application Support" / APP_NAME)]
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(home / ".local" / "share")
        candidates = [("用户数据目录", Path(base) / APP_NAME)]

    candidates.append(("用户主目录", home / f".{APP_NAME}"))
    import tempfile

    candidates.append(("系统临时目录",
                       Path(tempfile.gettempdir()) / APP_NAME))
    return candidates


#: 已经选定的数据目录（进程内缓存，避免每次都被反复探测）
_resolved_data_dir: Path | None = None
#: 探测过程记录，出问题时可以展示给用户
_probe_log: list[str] = []


def probe_log() -> list[str]:
    """返回数据目录的探测记录（哪些可用、哪些不可用）。"""
    return list(_probe_log)


def app_data_dir() -> Path:
    """应用数据目录（数据库、备份都放这里）。

    会**逐个候选目录尝试真正写入**，第一个可写的就用它。这样即使用户的
    ``%APPDATA%`` 因为权限/组策略/安全软件不可写，应用也能正常启动，
    而不是弹一个 "unable to open database file" 然后打不开。
    """
    global _resolved_data_dir
    if _resolved_data_dir is not None:
        return _resolved_data_dir

    _probe_log.clear()
    for label, candidate in _data_dir_candidates():
        try:
            candidate.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            _probe_log.append(f"{label} {candidate} 无法创建（{exc.strerror or exc}）")
            continue
        if _is_writable(candidate):
            _probe_log.append(f"{label} {candidate} 可用")
            _resolved_data_dir = candidate
            return candidate
        _probe_log.append(f"{label} {candidate} 不可写")

    raise DataDirError(
        "找不到可写的数据目录，应用无法保存账本。\n"
        + "\n".join(f"  · {line}" for line in _probe_log)
    )


def db_path() -> Path:
    """数据库文件路径。"""
    override = os.environ.get(_ENV_DB_FILE)
    if override:
        path = Path(override).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    return app_data_dir() / DB_FILENAME


def backup_dir() -> Path:
    """默认备份目录。"""
    path = app_data_dir() / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def export_dir() -> Path:
    """默认导出目录（CSV 等）。"""
    path = app_data_dir() / "exports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def describe() -> dict[str, str]:
    """返回当前路径配置，便于"设置 - 关于"展示与排错。"""
    return {
        "platform": sys.platform,
        "mobile": str(is_mobile()),
        "data_dir": str(app_data_dir()),
        "db_path": str(db_path()),
        "backup_dir": str(backup_dir()),
        "probe": " | ".join(probe_log()),
    }

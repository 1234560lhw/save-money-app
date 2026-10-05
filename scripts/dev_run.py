"""开发期热重载启动器（实时预览 UI）。

为什么要自己写
--------------
Flet 的打包版没有内置 CLI 热重载；网上常见的 ``flet run --reload`` 需要额外装
``flet-cli``。这里用标准库实现一个轻量看门狗：监视源码改动 -> 重启应用进程。
重启后界面立刻是新代码，数据在 SQLite 里，不会丢。

用法（在项目根目录）::

    # 桌面端窗口 + 热重载（默认）
    .venv\\Scripts\\python.exe scripts\\dev_run.py

    # 浏览器预览（手机端布局，改完刷新即可）
    .venv\\Scripts\\python.exe scripts\\dev_run.py --target mobile --web

    # 只运行一次，不监视改动
    .venv\\Scripts\\python.exe scripts\\dev_run.py --no-reload

实现细节
--------
子进程用 ``os.spawnv`` + ``stdio 继承`` 启动，不经过管道。原因：受限沙箱下
父进程用管道捕获子进程输出会被拒绝，继承标准流没有这个问题。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGETS = {
    "desktop": PROJECT_ROOT / "apps" / "desktop" / "app_entry.py",
    "mobile": PROJECT_ROOT / "apps" / "mobile" / "app_entry.py",
}
#: 监视这些目录里的 .py 改动
WATCH_DIRS = [PROJECT_ROOT / "core", PROJECT_ROOT / "apps"]
IGNORE_PARTS = {"__pycache__", ".venv", ".devdata", ".tmp", ".git", "build", "dist"}
POLL_INTERVAL = 0.7


def log(text: str) -> None:
    """实时打印（立即刷新），否则日志会被缓冲，看不到重启提示。"""
    print(text, flush=True)


def snapshot() -> dict[str, float]:
    """收集所有 .py 文件的修改时间。"""
    result: dict[str, float] = {}
    for base in WATCH_DIRS:
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            if any(part in IGNORE_PARTS for part in path.parts):
                continue
            try:
                result[str(path)] = path.stat().st_mtime
            except OSError:
                continue
    return result


def changed_files(old: dict[str, float], new: dict[str, float]) -> list[str]:
    """比较两次快照，返回有变化的文件（新增/修改/删除）。"""
    diff = [path for path, mtime in new.items() if old.get(path) != mtime]
    diff += [path for path in old if path not in new]
    return sorted(diff)


def spawn(entry: Path, extra: list[str]):
    """启动应用子进程。

    标准输出/错误直接继承当前终端（不建管道）：受限沙箱下父进程用管道捕获
    子进程输出会被拒绝，继承标准流没有这个问题，而且日志能实时看到。
    """
    python = sys.executable
    argv = [python, str(entry), *extra]
    log(f"[dev] 启动：{' '.join(argv)}")
    return subprocess.Popen(argv, cwd=str(PROJECT_ROOT), stdout=None, stderr=None)


def stop(process: subprocess.Popen) -> None:
    """结束子进程并等它真正退出。"""
    if process.poll() is not None:
        return
    try:
        process.terminate()
        process.wait(timeout=6)
    except (subprocess.TimeoutExpired, OSError):
        try:
            process.kill()
            process.wait(timeout=3)
        except (subprocess.TimeoutExpired, OSError):
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="存钱罐 · 开发期热重载启动器")
    parser.add_argument("--target", choices=sorted(TARGETS), default="desktop",
                        help="desktop=桌面端窗口（默认），mobile=手机端布局")
    parser.add_argument("--web", action="store_true",
                        help="在浏览器里预览（桌面端同样支持）")
    parser.add_argument("--port", type=int, default=None, help="--web 模式的端口")
    parser.add_argument("--demo", action="store_true", help="写入演示数据")
    parser.add_argument("--no-reload", action="store_true", help="不监视文件改动")
    args = parser.parse_args(argv)

    entry = TARGETS[args.target]
    if not entry.is_file():
        log(f"[dev] 找不到入口文件：{entry}")
        return 1

    extra: list[str] = ["--dev"]
    if args.demo:
        extra.append("--demo")
    if args.web:
        extra.append("--web")
    if args.port is not None:
        extra += ["--port", str(args.port)]

    log(f"[dev] 项目根目录：{PROJECT_ROOT}")
    log(f"[dev] 目标：{args.target} | 参数：{' '.join(extra) or '(无)'}")
    if not args.no_reload:
        log(f"[dev] 热重载：开启（监视 core/ 与 apps/ 下的 .py，间隔 {POLL_INTERVAL}s）")
        log("[dev] 改完代码保存，应用会自动重启。按 Ctrl+C 退出。")

    before = snapshot()
    process = spawn(entry, extra)

    if args.no_reload:
        return process.wait()

    try:
        while True:
            time.sleep(POLL_INTERVAL)
            after = snapshot()
            diff = changed_files(before, after)
            if diff:
                before = after
                shown = ", ".join(Path(p).name for p in diff[:4])
                more = f" 等 {len(diff)} 个文件" if len(diff) > 4 else ""
                log(f"\n[dev] 检测到改动：{shown}{more} -> 重启应用")
                stop(process)
                process = spawn(entry, extra)
                before = snapshot()
            # 应用自己退出了（比如关掉窗口）：看门狗跟着结束
            if process.poll() is not None and not diff:
                log(f"\n[dev] 应用已退出（退出码 {process.returncode}）")
                return int(process.returncode or 0)
    finally:
        stop(process)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        log("\n[dev] 已退出")
        raise SystemExit(0)

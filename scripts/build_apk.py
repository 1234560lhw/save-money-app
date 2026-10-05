"""打包 Android APK（Flet 移动端）。

这台机器的特殊限制（脚本已全部绕开）
------------------------------------
* ``%APPDATA%`` / ``%LOCALAPPDATA%`` **不可写**，而 Flutter / Gradle / Pub
  默认都往那里写缓存 —— 所以所有缓存目录都重定向到项目内的 ``.toolchain``；
* ``services.gradle.org`` 访问超时 —— Gradle 发行包改用腾讯云镜像
  （通过修改 Flutter 工具里的下载地址实现，见 :func:`patch_flutter_gradle_url`）；
* ``%USERPROFILE%\\.android`` 不可写 —— 调试签名目录用 ``ANDROID_USER_HOME``
  重定向。

用法::

    .venv\\Scripts\\python.exe scripts\\build_apk.py            # 完整流程
    .venv\\Scripts\\python.exe scripts\\build_apk.py --check    # 只检查工具链
    .venv\\Scripts\\python.exe scripts\\build_apk.py --no-patch # 不改 Flutter 的 Gradle 地址

产出：``build\\apk\\app-release.apk``
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOOLCHAIN = PROJECT_ROOT / ".toolchain"
FLUTTER_DIR = TOOLCHAIN / "flutter"
JDK_DIR = TOOLCHAIN / "jdk17"
ANDROID_SDK = TOOLCHAIN / "android-sdk"
GRADLE_HOME = TOOLCHAIN / "gradle-home"
PUB_CACHE = TOOLCHAIN / "pub-cache"
ANDROID_USER_HOME = TOOLCHAIN / "android-home"
#: Flutter 在 Windows 上把工具状态写到 %APPDATA%\.flutter_tool_state
#: （源码硬编码读 APPDATA，没有环境变量能覆盖），而本机 %APPDATA% 不可写。
#: 因此给子进程重定义这些目录到工作区内，并准备一个可写的"假用户目录"
#: （USERPROFILE 必须真实存在，否则 git 读不到 .gitconfig 会失败）。
USERPROFILE_OVERRIDE = TOOLCHAIN / "userprofile"
APPDATA_OVERRIDE = USERPROFILE_OVERRIDE / "AppData" / "Roaming"
LOCALAPPDATA_OVERRIDE = USERPROFILE_OVERRIDE / "AppData" / "Local"
#: 设环境变量 SAVE_MONEY_FORCE_PROFILE_OVERRIDE=1 可强制启用重定向
_FORCE_OVERRIDE = os.environ.get("SAVE_MONEY_FORCE_PROFILE_OVERRIDE") == "1"
MOBILE_APP = PROJECT_ROOT / "apps" / "mobile"

#: Gradle 发行包镜像（官方源在本机超时）
GRADLE_MIRROR = "https://mirrors.cloud.tencent.com/gradle"

APP_NAME = "Flipped的存钱罐"
PROJECT_NAME = "flipped_piggy"
ORG = "com.flipped"


def find_jdk() -> Path | None:
    """定位 JDK：优先项目内自带的，其次 JAVA_HOME。"""
    if JDK_DIR.is_dir():
        for candidate in JDK_DIR.iterdir():
            if (candidate / "bin" / "java.exe").is_file():
                return candidate
        if (JDK_DIR / "bin" / "java.exe").is_file():
            return JDK_DIR
    java_home = os.environ.get("JAVA_HOME")
    if java_home and (Path(java_home) / "bin" / "java.exe").is_file():
        return Path(java_home)
    return None


def find_flutter() -> Path | None:
    """定位 Flutter：``.toolchain/flutter/bin/flutter.bat``。"""
    for candidate in (FLUTTER_DIR / "bin" / "flutter.bat",
                      FLUTTER_DIR / "flutter" / "bin" / "flutter.bat"):
        if candidate.is_file():
            return candidate
    return None


def _needs_profile_override() -> bool:
    """系统用户目录是否不可写（不可写才需要把缓存重定向到项目内）。"""
    if _FORCE_OVERRIDE:
        return True
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return False
    probe = Path(appdata) / ".save_money_write_test"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return False          # 正常可写，按标准方式构建
    except OSError:
        print("[apk] 检测到 %APPDATA% 不可写，将把工具缓存重定向到项目内")
        return True


def prepare_user_profile() -> Path | None:
    """准备可写的"假用户目录"并写好最小 git 配置（仅在不必要时返回 None）。

    Flutter 用 git 取 SDK 版本号，git 启动要读 ``$USERPROFILE\\.gitconfig``；
    USERPROFILE 指向不存在的目录时 git 会直接失败（CreateFile failed 5）。
    """
    if not _needs_profile_override():
        return None

    USERPROFILE_OVERRIDE.mkdir(parents=True, exist_ok=True)
    for sub in (APPDATA_OVERRIDE, LOCALAPPDATA_OVERRIDE):
        sub.mkdir(parents=True, exist_ok=True)

    gitconfig = USERPROFILE_OVERRIDE / ".gitconfig"
    if not gitconfig.exists():
        workspace = str(PROJECT_ROOT).replace("\\", "/")
        flutter = str(FLUTTER_DIR).replace("\\", "/")
        gitconfig.write_text(
            "[user]\n\tname = SaveMoneyApp Build\n\temail = build@localhost\n"
            "[safe]\n"
            f"\tdirectory = {workspace}\n\tdirectory = {workspace}/*\n"
            f"\tdirectory = {flutter}\n\tdirectory = {flutter}/*\n"
            "[core]\n\tautocrlf = false\n",
            encoding="utf-8",
        )
    return USERPROFILE_OVERRIDE


def build_env() -> dict[str, str]:
    """构造打包用的环境变量。

    用户目录可写时保持原样；不可写时把 Flutter / Gradle / Pub / 签名缓存
    全部重定向到 ``.toolchain`` 内。
    """
    env = dict(os.environ)
    prepare_user_profile()
    for path in (GRADLE_HOME, PUB_CACHE, ANDROID_USER_HOME):
        path.mkdir(parents=True, exist_ok=True)

    jdk = find_jdk()
    if jdk:
        env["JAVA_HOME"] = str(jdk)
        env["PATH"] = f"{jdk / 'bin'}{os.pathsep}" + env.get("PATH", "")

    if _needs_profile_override():
        # Flutter 读 %APPDATA%\.flutter_tool_state，
        # 否则工具快照永远建不出来（会陷入无限重建）
        env["USERPROFILE"] = str(USERPROFILE_OVERRIDE)
        env["APPDATA"] = str(APPDATA_OVERRIDE)
        env["LOCALAPPDATA"] = str(LOCALAPPDATA_OVERRIDE)
        env["HOME"] = str(USERPROFILE_OVERRIDE)

    env["ANDROID_HOME"] = str(ANDROID_SDK)
    env["ANDROID_SDK_ROOT"] = str(ANDROID_SDK)
    env["ANDROID_USER_HOME"] = str(ANDROID_USER_HOME)
    env["GRADLE_USER_HOME"] = str(GRADLE_HOME)
    env["PUB_CACHE"] = str(PUB_CACHE)

    flutter = find_flutter()
    if flutter:
        env["PATH"] = f"{flutter.parent}{os.pathsep}" + env.get("PATH", "")
        env["FLUTTER_ROOT"] = str(flutter.parent.parent)

    # Flutter 会把分析报告、遥测写进用户目录，这里关掉以免报权限错
    env["FLUTTER_SUPPRESS_ANALYTICS"] = "true"
    env["CI"] = "true"
    return env


def patch_flutter_gradle_url() -> bool:
    """把 Flutter 工具里的 Gradle 下载地址换成本机可达的镜像。

    Flutter 的 ``gradle_utils.dart`` 里硬编码了
    ``https://services.gradle.org/distributions``，而这个域名在本机超时。
    这里就地改成腾讯云镜像（只改本地 SDK，不影响 Flutter 安装包的完整性
    校验——因为改的是 Dart 源码，Flutter 会重新编译工具快照）。
    """
    candidates = list(FLUTTER_DIR.rglob("gradle_utils.dart"))
    if not candidates:
        print("[apk] 没找到 gradle_utils.dart，跳过 Gradle 地址替换")
        return False

    changed = False
    for path in candidates:
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "services.gradle.org/distributions" not in text:
            continue
        backup = path.with_suffix(".dart.bak")
        if not backup.exists():
            backup.write_text(text, encoding="utf-8")
        patched = text.replace("https://services.gradle.org/distributions", GRADLE_MIRROR)
        path.write_text(patched, encoding="utf-8")
        print(f"[apk] 已替换 Gradle 下载源：{path.relative_to(FLUTTER_DIR)}")
        changed = True

    if changed:
        # 工具快照需要重建，删掉旧的让它重新编译
        stamp = FLUTTER_DIR / "bin" / "cache" / "flutter_tools.stamp"
        if stamp.exists():
            stamp.unlink()
            print("[apk] 已清理 flutter_tools 快照，下次运行会重新编译")
    return changed


def check_toolchain() -> tuple[bool, list[str]]:
    """检查工具链是否齐备，返回 (是否齐备, 问题列表)。"""
    problems: list[str] = []

    jdk = find_jdk()
    if not jdk:
        problems.append(f"缺少 JDK：期望 {JDK_DIR} 或设置 JAVA_HOME")
    else:
        try:
            out = subprocess.run([str(jdk / "bin" / "java.exe"), "-version"],
                                 capture_output=True, text=True, timeout=30)
            version = (out.stderr or out.stdout).splitlines()[0] if (out.stderr or out.stdout) else "?"
            print(f"[apk] JDK      {jdk}")
            print(f"[apk]          {version.strip()}")
        except Exception as exc:  # noqa: BLE001
            problems.append(f"JDK 无法运行：{exc}")

    flutter = find_flutter()
    if not flutter:
        problems.append(f"缺少 Flutter SDK：期望 {FLUTTER_DIR}")
    else:
        print(f"[apk] Flutter  {flutter}")

    if not (ANDROID_SDK / "cmdline-tools" / "latest" / "bin").is_dir():
        problems.append(f"缺少 Android 命令行工具：期望 {ANDROID_SDK / 'cmdline-tools' / 'latest'}")
    else:
        print(f"[apk] Android  {ANDROID_SDK}")

    return (not problems), problems


def flet_cli_command(*args: str) -> list[str]:
    """构造调用 flet CLI 的命令。

    **重要**：flet 0.28.3 **没有** ``flet/__main__.py``，所以
    ``python -m flet build ...`` 会直接报 ``No module named flet.__main__``。
    早期版本这里就是这么写的，导致打包命令根本没跑起来
    （如果你看到的是"没反应"，很可能就是这个原因）。

    正确做法是调用分发入口 ``flet.cli:main``。
    另外 ``install_deps.py`` 用 pip ``--target`` 装包，不会生成
    ``Scripts\\flet.exe``，所以也不能靠命令行脚本名调用。
    """
    invoke = (
        "import sys;"
        "from flet.cli import main;"
        f"sys.argv = ['flet', {', '.join(repr(a) for a in args)}];"
        "main()"
    )
    return [sys.executable, "-c", invoke]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="打包 Android APK")
    parser.add_argument("--check", action="store_true", help="只检查工具链")
    parser.add_argument("--no-patch", action="store_true",
                        help="不修改 Flutter 的 Gradle 下载地址")
    parser.add_argument("--clean", action="store_true", help="构建前清理 build 目录")
    parser.add_argument("--timeout", type=int, default=3600,
                        help="整体超时秒数（默认 3600）；超时会打印最后的输出便于排查")
    args = parser.parse_args(argv)

    print("=" * 66)
    print(f"{APP_NAME} · Android APK 打包")
    print("=" * 66)

    ok, problems = check_toolchain()
    if not ok:
        print()
        for line in problems:
            print(f"[apk] ✗ {line}")
        print()
        print("[apk] 工具链不完整，先补齐再打包")
        return 1
    if args.check:
        print()
        print("[apk] 工具链齐备 ✅")
        return 0

    if not args.no_patch:
        patch_flutter_gradle_url()

    env = build_env()
    if args.clean:
        import shutil

        shutil.rmtree(PROJECT_ROOT / "build" / "apk", ignore_errors=True)

    # --no-rich-output：关掉富文本进度动画。否则日志会被 spinner 刷屏
    # （之前就是一屏的 "Initializing apk build..."），看不到真实报错。
    flet_args = [
        "build", "apk", str(MOBILE_APP),
        "--project", PROJECT_NAME,
        "--org", ORG,
        "--product", APP_NAME,
        "--build-version", "1.0.0",
        "--skip-flutter-doctor",
        "--no-rich-output",
    ]
    cmd = flet_cli_command(*flet_args)

    log_path = PROJECT_ROOT / ".tmp" / "apk_build.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"[apk] 开始构建：flet build apk {MOBILE_APP.name} --product {APP_NAME}")
    print(f"[apk] 完整输出同时写入：{log_path.relative_to(PROJECT_ROOT)}")
    print("[apk] 首次构建要下载 Android 平台包与 Gradle 依赖，可能较久。")
    print(f"[apk] 超过 {args.timeout} 秒会自动中止并打印最后的输出。")

    started = time.time()
    with open(log_path, "w", encoding="utf-8", buffering=1) as log_file:
        proc = subprocess.Popen(cmd, cwd=str(PROJECT_ROOT), env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, bufsize=1)
        timed_out = False
        try:
            for line in proc.stdout:  # type: ignore[union-attr]
                log_file.write(line)
                stripped = line.rstrip()
                if stripped:
                    print(f"[flet] {stripped}")
                if time.time() - started > args.timeout:
                    timed_out = True
                    proc.kill()
                    break
            if not timed_out:
                proc.wait()
        except KeyboardInterrupt:
            proc.kill()
            print("[apk] 已手动中断")
            return 130

    if timed_out:
        print(f"[apk] ✗ 超过 {args.timeout} 秒仍未完成，已中止")
        _print_tail(log_path, 20)
        return 124

    if proc.returncode != 0:
        print(f"[apk] 构建失败（退出码 {proc.returncode}）")
        _print_tail(log_path, 20)
        return proc.returncode

    apk = PROJECT_ROOT / "build" / "apk" / "app-release.apk"
    if apk.is_file():
        print(f"\n[apk] ✅ 打包完成：{apk}")
        print(f"[apk]    体积 {apk.stat().st_size / 1024 / 1024:.1f} MB")
        print("[apk]    传到手机安装即可（需允许安装未知来源应用）")
    else:
        print(f"[apk] 构建结束但没找到 apk，检查 {PROJECT_ROOT / 'build' / 'apk'}")
    return 0


def _print_tail(log_path: Path, lines: int) -> None:
    """打印日志末尾，方便定位失败原因。"""
    try:
        content = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return
    print(f"[apk] 最后 {lines} 行输出：")
    for item in content[-lines:]:
        print(f"        {item}")


if __name__ == "__main__":
    raise SystemExit(main())

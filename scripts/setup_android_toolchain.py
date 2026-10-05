"""装配 Android 工具链到项目内（一次性）。

这台机器的限制
--------------
* ``%APPDATA%`` / ``%LOCALAPPDATA%`` / ``%USERPROFILE%\\.android`` **都不可写**，
  而 Flutter、Gradle、Pub、Android 签名默认全往那里写 —— 所以所有缓存与
  配置目录都由本脚本重定向到 ``.toolchain`` 内；
* ``services.gradle.org`` 超时 —— Gradle 发行包走腾讯云镜像；
* JDK 官方源会跳转 GitHub 导致超时 —— 改用华为云镜像。

做四件事：
1. 解压 Flutter SDK（若还没解压）；
2. 用 Flutter 自带的 Dart 初始化一次（会下载 Dart SDK 到 SDK 目录内）；
3. 用 sdkmanager 安装 Android 平台包、构建工具、平台工具；
4. 接受 Android 许可协议。

用法::

    .venv\\Scripts\\python.exe scripts\\setup_android_toolchain.py
    .venv\\Scripts\\python.exe scripts\\setup_android_toolchain.py --check
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOOLCHAIN = PROJECT_ROOT / ".toolchain"
DOWNLOADS = TOOLCHAIN / "downloads"
FLUTTER_DIR = TOOLCHAIN / "flutter"
JDK_DIR = TOOLCHAIN / "jdk17"
ANDROID_SDK = TOOLCHAIN / "android-sdk"
GRADLE_HOME = TOOLCHAIN / "gradle-home"
PUB_CACHE = TOOLCHAIN / "pub-cache"
ANDROID_USER_HOME = TOOLCHAIN / "android-home"
#: 关键：Flutter 在 Windows 上把工具状态写到 %APPDATA%\.flutter_tool_state
#: （源码里硬编码读 APPDATA，没有对应的环境变量可以覆盖），而这台机器的
#: %APPDATA% 不可写 —— 于是它永远建不出工具快照，无限重试。
#: 所以给子进程重定义 APPDATA / LOCALAPPDATA / USERPROFILE 到工作区内。
#:
#: 注意 USERPROFILE 必须是一个**真实存在**的目录，并且里面有 .gitconfig：
#: Flutter 会用 git 取版本号，git 启动时要读 $USERPROFILE\.gitconfig，
#: 目录不存在就会报 "CreateFile failed 5"（踩过这个坑）。
USERPROFILE_OVERRIDE = TOOLCHAIN / "userprofile"
APPDATA_OVERRIDE = USERPROFILE_OVERRIDE / "AppData" / "Roaming"
LOCALAPPDATA_OVERRIDE = USERPROFILE_OVERRIDE / "AppData" / "Local"
#: 设环境变量 SAVE_MONEY_FORCE_PROFILE_OVERRIDE=1 可强制启用重定向
_FORCE_OVERRIDE = os.environ.get("SAVE_MONEY_FORCE_PROFILE_OVERRIDE") == "1"

#: 需要安装的 Android 包（Flutter 默认 target 34 左右，多装几个版本更稳）
ANDROID_PACKAGES = [
    "platform-tools",
    "platforms;android-34",
    "platforms;android-35",
    "build-tools;34.0.0",
    "build-tools;35.0.0",
    "cmdline-tools;latest",
]


def log(message: str) -> None:
    print(message, flush=True)


def find_java() -> Path | None:
    """找到 JDK 的 java.exe。"""
    if JDK_DIR.is_dir():
        for candidate in JDK_DIR.rglob("bin/java.exe"):
            return candidate
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        candidate = Path(java_home) / "bin" / "java.exe"
        if candidate.is_file():
            return candidate
    return None


def find_flutter_bat() -> Path | None:
    for candidate in (FLUTTER_DIR / "bin" / "flutter.bat",
                      FLUTTER_DIR / "flutter" / "bin" / "flutter.bat"):
        if candidate.is_file():
            return candidate
    return None


def prepare_user_profile() -> Path | None:
    """准备一个可写的"假用户目录"，并把 git 配置好。

    **只在系统用户目录不可写时才需要**（例如受限沙箱环境）。判断方式是
    真的往 ``%APPDATA%`` 写一个文件试试。

    Flutter 会用 git 取 SDK 版本号；git 启动时要读 ``$USERPROFILE\\.gitconfig``。
    如果 USERPROFILE 指向不存在的目录，git 会直接失败（CreateFile failed 5），
    表现为 Flutter 报"cannot access the file or directory"。所以这里把目录
    建好、写一个最小 .gitconfig，并把工作区标记为 safe.directory。
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
            "[user]\n"
            "\tname = SaveMoneyApp Build\n"
            "\temail = build@localhost\n"
            "[safe]\n"
            f"\tdirectory = {workspace}\n"
            f"\tdirectory = {workspace}/*\n"
            f"\tdirectory = {flutter}\n"
            f"\tdirectory = {flutter}/*\n"
            "[core]\n"
            "\tautocrlf = false\n",
            encoding="utf-8",
        )
        log(f"[setup] 已准备 git 配置：{gitconfig}")
    return USERPROFILE_OVERRIDE


def _needs_profile_override() -> bool:
    """系统用户目录是否不可写（需要把工具缓存重定向到项目内）。"""
    if _FORCE_OVERRIDE:
        return True
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return False
    probe = Path(appdata) / ".save_money_write_test"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return False          # 正常可写，不需要重定向
    except OSError:
        log("[setup] 检测到 %APPDATA% 不可写，将把工具缓存重定向到项目内")
        return True


def env_for_tools() -> dict[str, str]:
    """构造所有工具都需要的环境变量。

    用户目录可写时保持原样；不可写时（受限沙箱）把 Flutter / Gradle / Pub /
    Android 签名的缓存目录全部重定向到 ``.toolchain`` 内。
    """
    env = dict(os.environ)
    prepare_user_profile()
    for path in (GRADLE_HOME, PUB_CACHE, ANDROID_USER_HOME):
        path.mkdir(parents=True, exist_ok=True)

    java = find_java()
    if java:
        env["JAVA_HOME"] = str(java.parent.parent)
        env["PATH"] = f"{java.parent}{os.pathsep}" + env.get("PATH", "")

    if _needs_profile_override():
        # Flutter 读 %APPDATA%\.flutter_tool_state；git 读 $USERPROFILE\.gitconfig
        env["USERPROFILE"] = str(USERPROFILE_OVERRIDE)
        env["APPDATA"] = str(APPDATA_OVERRIDE)
        env["LOCALAPPDATA"] = str(LOCALAPPDATA_OVERRIDE)
        env["HOME"] = str(USERPROFILE_OVERRIDE)

    env["ANDROID_HOME"] = str(ANDROID_SDK)
    env["ANDROID_SDK_ROOT"] = str(ANDROID_SDK)
    env["ANDROID_USER_HOME"] = str(ANDROID_USER_HOME)
    env["GRADLE_USER_HOME"] = str(GRADLE_HOME)
    env["PUB_CACHE"] = str(PUB_CACHE)
    env["FLUTTER_SUPPRESS_ANALYTICS"] = "true"
    env["CI"] = "true"
    return env


def step_extract_flutter() -> bool:
    """解压 Flutter SDK。"""
    if find_flutter_bat():
        log("[setup] Flutter 已解压，跳过")
        return True
    archive = DOWNLOADS / "flutter_sdk.zip"
    if not archive.is_file() or archive.stat().st_size < 100 * 1024 * 1024:
        log(f"[setup] ✗ Flutter 压缩包不完整：{archive}")
        return False

    log(f"[setup] 解压 Flutter（{archive.stat().st_size / 1024 ** 2:.0f} MB），需要一两分钟…")
    FLUTTER_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        # 包内顶层是 flutter/，解到 .toolchain 下正好得到 .toolchain/flutter
        zf.extractall(TOOLCHAIN)
    log("[setup] Flutter 解压完成")
    return find_flutter_bat() is not None


def step_init_flutter() -> bool:
    """跑一次 flutter --version，让它把 Dart SDK 等下载到 SDK 目录内。"""
    flutter = find_flutter_bat()
    if not flutter:
        log("[setup] ✗ 找不到 flutter.bat")
        return False

    log("[setup] 初始化 Flutter（首次会下载 Dart SDK，约 200MB，请稍候）…")
    result = subprocess.run([str(flutter), "--version"], env=env_for_tools(),
                            capture_output=True, text=True, timeout=1800)
    output = (result.stdout or "") + (result.stderr or "")
    log("        " + output.strip().splitlines()[0] if output.strip() else "        （无输出）")
    if result.returncode != 0:
        log(f"[setup] ✗ flutter --version 失败（退出码 {result.returncode}）")
        for line in output.strip().splitlines()[-12:]:
            log(f"        {line}")
        return False
    return True


def step_install_android_packages() -> bool:
    """用 sdkmanager 安装 Android 平台包并接受许可。"""
    sdkmanager = ANDROID_SDK / "cmdline-tools" / "latest" / "bin" / "sdkmanager.bat"
    if not sdkmanager.is_file():
        log(f"[setup] ✗ 找不到 sdkmanager：{sdkmanager}")
        return False

    env = env_for_tools()
    log("[setup] 接受 Android 许可协议…")
    yes = subprocess.run(f'echo y| "{sdkmanager}" --licenses', shell=True, env=env,
                         capture_output=True, text=True, timeout=600)
    tail = (yes.stdout or "")[-300:]
    log("        " + ("许可已处理" if "accept" in tail.lower() or yes.returncode == 0
                      else f"（退出码 {yes.returncode}）"))

    log(f"[setup] 安装 Android 包：{len(ANDROID_PACKAGES)} 个（含平台与构建工具，约 300MB）…")
    cmd = [str(sdkmanager), "--sdk_root", str(ANDROID_SDK)] + ANDROID_PACKAGES
    result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=3600)
    if result.returncode != 0:
        log(f"[setup] ✗ sdkmanager 失败（退出码 {result.returncode}）")
        for line in ((result.stdout or "") + (result.stderr or "")).strip().splitlines()[-15:]:
            log(f"        {line}")
        return False
    log("[setup] Android 包安装完成")
    return True


def step_check() -> int:
    """检查工具链是否齐备。"""
    log("=== 工具链检查 ===")
    problems: list[str] = []

    java = find_java()
    if java:
        out = subprocess.run([str(java), "-version"], capture_output=True, text=True)
        log(f"  JDK      {java}")
        log(f"           {(out.stderr or out.stdout).splitlines()[0].strip()}")
    else:
        problems.append(f"缺少 JDK（期望 {JDK_DIR}）")

    flutter = find_flutter_bat()
    if flutter:
        log(f"  Flutter  {flutter}")
    else:
        problems.append(f"缺少 Flutter（期望 {FLUTTER_DIR}）")

    sdkmanager = ANDROID_SDK / "cmdline-tools" / "latest" / "bin" / "sdkmanager.bat"
    if sdkmanager.is_file():
        log(f"  Android  {ANDROID_SDK}")
        platforms = sorted(p.name for p in (ANDROID_SDK / "platforms").glob("*")) \
            if (ANDROID_SDK / "platforms").is_dir() else []
        build_tools = sorted(p.name for p in (ANDROID_SDK / "build-tools").glob("*")) \
            if (ANDROID_SDK / "build-tools").is_dir() else []
        log(f"           平台: {platforms or '（未安装）'}")
        log(f"           构建工具: {build_tools or '（未安装）'}")
        if not platforms:
            problems.append("Android 平台包未安装")
    else:
        problems.append(f"缺少 Android 命令行工具（期望 {sdkmanager}）")

    log("")
    if problems:
        for line in problems:
            log(f"  ✗ {line}")
        return 1
    log("  全部齐备 ✅")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="装配 Android 工具链")
    parser.add_argument("--check", action="store_true", help="只检查，不安装")
    parser.add_argument("--skip-flutter-init", action="store_true",
                        help="跳过 Flutter 初始化")
    parser.add_argument("--skip-android", action="store_true",
                        help="跳过 Android 包安装")
    args = parser.parse_args(argv)

    if args.check:
        return step_check()

    if not step_extract_flutter():
        return 1
    if not args.skip_flutter_init and not step_init_flutter():
        return 1
    if not args.skip_android and not step_install_android_packages():
        return 1
    return step_check()


if __name__ == "__main__":
    raise SystemExit(main())

@echo off
REM ===================================================================
REM  存钱罐 · 一键启动（开发期）
REM
REM  双击本文件即可：
REM    1) 检查虚拟环境是否存在，不存在就自动创建
REM    2) 检查依赖是否装好
REM    3) 带热重载启动界面
REM
REM  想启动手机端布局：  start.bat mobile
REM  想用浏览器预览：    start.bat desktop web
REM  只想跑一次不热重载：start.bat desktop noreload
REM ===================================================================
setlocal
cd /d "%~dp0"

set TARGET=%1
if "%TARGET%"=="" set TARGET=desktop
set MODE=%2

set PY=.venv\Scripts\python.exe

if not exist "%PY%" (
  echo [start] 未找到虚拟环境，正在创建 .venv ...
  python -m venv .venv
  if errorlevel 1 (
    echo [start] 创建虚拟环境失败，请确认已安装 Python 3.10+ 并加入 PATH。
    pause
    exit /b 1
  )
)

"%PY%" -c "import flet" 2>nul
if errorlevel 1 (
  echo [start] 未安装依赖，正在安装（使用清华镜像）...
  "%PY%" scripts\install_deps.py -r requirements-desktop.txt
  if errorlevel 1 (
    echo [start] 依赖安装失败，详见上面的错误信息。
    pause
    exit /b 1
  )
)

set ARGS=--target %TARGET%
if /i "%MODE%"=="web" set ARGS=%ARGS% --web
if /i "%MODE%"=="noreload" set ARGS=%ARGS% --no-reload

echo [start] 启动：%ARGS%
"%PY%" scripts\dev_run.py %ARGS%

pause

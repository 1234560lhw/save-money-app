<#
.SYNOPSIS
    打开一个已经激活项目虚拟环境的 PowerShell 窗口。

.DESCRIPTION
    双击运行本脚本（右键"使用 PowerShell 运行"）会打开一个新的
    PowerShell 窗口并自动激活 .venv，省去每次手输激活命令和
    放宽执行策略的麻烦。

    想在当前窗口里激活，请直接用：
        .\.venv\Scripts\Activate.ps1

.EXAMPLE
    .\shell.ps1
#>

$root = $PSScriptRoot
$activate = Join-Path $root ".venv\Scripts\Activate.ps1"

if (-not (Test-Path $activate)) {
    Write-Host "找不到虚拟环境：$activate" -ForegroundColor Red
    Write-Host "请先创建：python -m venv .venv" -ForegroundColor Yellow
    exit 1
}

Write-Host "正在打开已激活虚拟环境的 PowerShell 窗口..." -ForegroundColor Green
Start-Process -FilePath "powershell.exe" `
    -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", "& '$activate'"

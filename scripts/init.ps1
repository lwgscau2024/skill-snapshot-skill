# ============================================================
# init.ps1 - Skill Snapshot 初始化脚本 (Windows 11 Optimized)
# ============================================================

#Requires -Version 5.1
$ErrorActionPreference = "Stop"
# 解决 Windows 终端中文乱码问题
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"

# 获取脚本所在目录的绝对路径
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$PythonScript = Join-Path $ScriptDir "snapshot_manager.py"

# 检查 Python 环境
if (-not (Get-Command "python" -ErrorAction SilentlyContinue)) {
    Write-Host "错误: 未找到 Python。请安装 Python 3.7+ 并添加到 PATH。" -ForegroundColor Red
    exit 1
}

# 调用 Python 脚本
python "$PythonScript" init
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

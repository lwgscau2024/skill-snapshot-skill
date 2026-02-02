# ============================================================
# save.ps1 - Skill Snapshot 保存脚本 (Windows 11 Optimized)
# ============================================================

#Requires -Version 5.1
param(
    [Parameter(Position = 0, Mandatory = $true)]
    [string]$SkillName,
    
    [Parameter(Position = 1)]
    [string]$Message
)

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

# 构建参数列表
$ArgsList = @("save", $SkillName)
if (-not [string]::IsNullOrEmpty($Message)) {
    $ArgsList += $Message
}

# 调用 Python 脚本
# 注意：PowerShell 传递带空格参数给 Python 有时需要特别注意引号，但在 Start-Process 或直接调用时通常由 PS 处理
# 直接调用 python "$Script" arg1 arg2
python "$PythonScript" @ArgsList

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

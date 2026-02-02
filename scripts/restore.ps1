# ============================================================
# restore.ps1 - Skill Snapshot 恢复脚本 (Windows 11 Optimized)
# ============================================================

#Requires -Version 5.1
param(
    [Parameter(Position = 0, Mandatory = $true)]
    [string]$SkillName,
    
    [Parameter(Position = 1)]
    [string]$Version
)

$ErrorActionPreference = "Stop"
# 解决 Windows 终端中文乱码问题
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$PythonScript = Join-Path $ScriptDir "snapshot_manager.py"

if (-not (Get-Command "python" -ErrorAction SilentlyContinue)) {
    Write-Host "错误: 未找到 Python。" -ForegroundColor Red
    exit 1
}

$ArgsList = @("restore", $SkillName)
if (-not [string]::IsNullOrEmpty($Version)) {
    $ArgsList += $Version
}

python "$PythonScript" @ArgsList

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

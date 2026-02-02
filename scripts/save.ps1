# ============================================================
# save.ps1 - Skill Snapshot 保存脚本 (Windows PowerShell 版本)
# 功能：将指定技能保存为版本快照
# 用法：.\save.ps1 <skill-name> [message]
# ============================================================

#Requires -Version 5.1
param(
    [Parameter(Position = 0)]
    [string]$SkillName,
    
    [Parameter(Position = 1)]
    [string]$Message
)

$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# 配置
$SkillsDir = Join-Path $env:USERPROFILE ".claude\skills"
$LocalRepo = Join-Path $env:USERPROFILE ".claude\skill-snapshots"

# 参数检查
if ([string]::IsNullOrEmpty($SkillName)) {
    Write-Host "错误: 请指定技能名称" -ForegroundColor Red
    Write-Host "用法: .\save.ps1 <skill-name> [message]" -ForegroundColor Yellow
    exit 1
}

$SkillPath = Join-Path $SkillsDir $SkillName

# 检查技能是否存在
if (-not (Test-Path $SkillPath)) {
    Write-Host "错误: 技能不存在: $SkillPath" -ForegroundColor Red
    exit 1
}

# 检查是否为符号链接
$Item = Get-Item $SkillPath -Force
if ($Item.LinkType -eq 'SymbolicLink' -or $Item.LinkType -eq 'Junction') {
    Write-Host "错误: $SkillName 是符号链接（外部安装），不支持快照" -ForegroundColor Red
    exit 1
}

# 检查仓库是否初始化
if (-not (Test-Path (Join-Path $LocalRepo ".git"))) {
    Write-Host "错误: 仓库未初始化，请先执行 init" -ForegroundColor Red
    exit 1
}

# 进入仓库目录
Push-Location $LocalRepo

try {
    # 同步远程
    git pull --quiet origin main 2>$null
    git fetch --tags --quiet 2>$null

    # 获取现有版本号
    $ExistingTags = git tag -l "$SkillName/v*" 2>$null | Sort-Object { [int]($_ -replace ".*v", "") } | Select-Object -Last 1
    
    if ([string]::IsNullOrEmpty($ExistingTags)) {
        $NextVersion = "v1"
    }
    else {
        $LastNum = [int]($ExistingTags -replace ".*v", "")
        $NextVersion = "v$($LastNum + 1)"
    }

    $TagName = "$SkillName/$NextVersion"

    # 默认提交说明
    if ([string]::IsNullOrEmpty($Message)) {
        $Message = "Snapshot at $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
    }

    Write-Host "=== 保存快照 ===" -ForegroundColor Cyan
    Write-Host "技能: $SkillName" -ForegroundColor White
    Write-Host "版本: $NextVersion" -ForegroundColor White
    Write-Host "说明: $Message" -ForegroundColor White
    Write-Host ""

    # 准备目标目录
    $TargetDir = Join-Path $LocalRepo $SkillName
    if (Test-Path $TargetDir) {
        Remove-Item $TargetDir -Recurse -Force
    }
    New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null

    # 复制文件
    Copy-Item -Path "$SkillPath\*" -Destination $TargetDir -Recurse -Force

    # 清理不需要的文件和目录
    $CleanupPaths = @(
        (Join-Path $TargetDir ".git"),
        (Join-Path $TargetDir "__pycache__"),
        (Join-Path $TargetDir ".DS_Store"),
        (Join-Path $TargetDir "node_modules"),
        (Join-Path $TargetDir ".venv")
    )
    
    foreach ($CleanPath in $CleanupPaths) {
        if (Test-Path $CleanPath) {
            Remove-Item $CleanPath -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    # 递归清理 __pycache__ 目录
    Get-ChildItem -Path $TargetDir -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue | 
    ForEach-Object { Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }

    # 递归清理 .DS_Store 文件
    Get-ChildItem -Path $TargetDir -Recurse -File -Filter ".DS_Store" -ErrorAction SilentlyContinue | 
    ForEach-Object { Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue }

    # 添加到 Git
    git add "$SkillName/"

    # 检查是否有变化
    $HasChanges = git diff --cached --quiet 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ 无变化 - 内容与最新快照相同，无需保存" -ForegroundColor Green
        $LatestTag = git tag -l "$SkillName/v*" 2>$null | Sort-Object { [int]($_ -replace ".*v", "") } | Select-Object -Last 1
        if (-not [string]::IsNullOrEmpty($LatestTag)) {
            Write-Host "→ 最新快照: $LatestTag" -ForegroundColor Yellow
        }
        exit 0
    }

    # 提交并推送
    git commit --quiet -m "[$SkillName] $NextVersion`: $Message"
    git tag -a $TagName -m $Message
    git push --quiet origin main
    git push --quiet origin $TagName

    Write-Host "✓ 快照已保存: $TagName" -ForegroundColor Green
    Write-Host "→ 可用 'restore $SkillName $NextVersion' 恢复" -ForegroundColor Yellow

}
finally {
    Pop-Location
}

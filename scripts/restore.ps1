# ============================================================
# restore.ps1 - Skill Snapshot 恢复脚本 (Windows PowerShell 版本)
# 功能：将技能恢复到指定历史版本
# 用法：.\restore.ps1 <skill-name> [version]
# ============================================================

#Requires -Version 5.1
param(
    [Parameter(Position = 0)]
    [string]$SkillName,
    
    [Parameter(Position = 1)]
    [string]$Version
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
    Write-Host "用法: .\restore.ps1 <skill-name> [version]" -ForegroundColor Yellow
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

    # 获取可用版本
    $AvailableTags = git tag -l "$SkillName/v*" 2>$null | Sort-Object { [int]($_ -replace ".*v", "") }
    
    if ($null -eq $AvailableTags -or $AvailableTags.Count -eq 0) {
        Write-Host "错误: 没有找到 $SkillName 的快照" -ForegroundColor Red
        exit 1
    }

    # 如果没有指定版本，显示可用版本列表
    if ([string]::IsNullOrEmpty($Version)) {
        Write-Host "=== $SkillName 可用版本 ===" -ForegroundColor Cyan
        Write-Host ""
        
        foreach ($Tag in $AvailableTags) {
            $Ver = $Tag -replace ".*/"
            $TagMsg = git tag -l $Tag -n1 2>$null
            $TagMsg = $TagMsg -replace "^$Tag\s*", ""
            $TagDate = git log -1 --format="%ci" $Tag 2>$null
            if ($TagDate) {
                $TagDate = $TagDate.Substring(0, 10)
            }
            Write-Host "  $Ver - $TagDate - $TagMsg" -ForegroundColor White
        }
        
        Write-Host ""
        Write-Host "请指定要恢复的版本，如: restore $SkillName v2" -ForegroundColor Yellow
        exit 0
    }

    # 检查版本是否存在
    $TagName = "$SkillName/$Version"
    if ($AvailableTags -notcontains $TagName) {
        Write-Host "错误: 版本不存在: $TagName" -ForegroundColor Red
        Write-Host "可用版本:" -ForegroundColor Yellow
        foreach ($Tag in $AvailableTags) {
            $Ver = $Tag -replace ".*/"
            Write-Host "  $Ver" -ForegroundColor White
        }
        exit 1
    }

    $SkillPath = Join-Path $SkillsDir $SkillName

    # 检查是否为符号链接
    if (Test-Path $SkillPath) {
        $Item = Get-Item $SkillPath -Force
        if ($Item.LinkType -eq 'SymbolicLink' -or $Item.LinkType -eq 'Junction') {
            Write-Host "错误: $SkillName 是符号链接（外部安装），不支持恢复" -ForegroundColor Red
            exit 1
        }
    }

    Write-Host "=== 恢复快照 ===" -ForegroundColor Cyan
    Write-Host "技能: $SkillName" -ForegroundColor White
    Write-Host "版本: $Version" -ForegroundColor White
    Write-Host ""

    # 备份当前版本
    if (Test-Path $SkillPath) {
        $BackupDir = Join-Path $SkillsDir ".snapshot-backup"
        New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
        $BackupName = "$SkillName-$(Get-Date -Format 'yyyyMMddHHmmss')"
        $BackupPath = Join-Path $BackupDir $BackupName
        Copy-Item -Path $SkillPath -Destination $BackupPath -Recurse -Force
        Write-Host "→ 当前版本已备份到: .snapshot-backup\$BackupName" -ForegroundColor Yellow
    }

    # 切换到指定版本
    git checkout --quiet $TagName

    # 删除现有技能目录
    if (Test-Path $SkillPath) {
        Remove-Item $SkillPath -Recurse -Force
    }
    New-Item -ItemType Directory -Path $SkillPath -Force | Out-Null

    # 复制文件（排除 .git 等目录）
    $SourceDir = Join-Path $LocalRepo $SkillName
    $ExcludeItems = @('.git', '__pycache__', '.DS_Store')
    
    Get-ChildItem -Path $SourceDir -Force | Where-Object { 
        $ExcludeItems -notcontains $_.Name 
    } | ForEach-Object {
        Copy-Item -Path $_.FullName -Destination $SkillPath -Recurse -Force
    }

    # 切回 main 分支
    git checkout --quiet main

    Write-Host "✓ 已恢复到 $TagName" -ForegroundColor Green
    Write-Host "→ 技能位置: $SkillPath" -ForegroundColor Yellow

}
finally {
    Pop-Location
}

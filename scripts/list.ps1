# ============================================================
# list.ps1 - Skill Snapshot 列表脚本 (Windows PowerShell 版本)
# 功能：查看技能的版本历史
# 用法：.\list.ps1 [skill-name]
# ============================================================

#Requires -Version 5.1
param(
    [Parameter(Position = 0)]
    [string]$SkillName
)

$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# 配置
$LocalRepo = Join-Path $env:USERPROFILE ".claude\skill-snapshots"

# 检查仓库是否初始化
if (-not (Test-Path (Join-Path $LocalRepo ".git"))) {
    Write-Host "错误: 仓库未初始化，请先执行 init" -ForegroundColor Red
    exit 1
}

# 进入仓库目录
Push-Location $LocalRepo

try {
    # 同步远程标签
    git fetch --tags --quiet 2>$null

    if ([string]::IsNullOrEmpty($SkillName)) {
        # 列出所有技能的快照
        Write-Host "=== 所有技能快照 ===" -ForegroundColor Cyan
        Write-Host ""

        $AllTags = git tag -l "*/v*" 2>$null | Sort-Object
        
        if ($null -eq $AllTags -or $AllTags.Count -eq 0) {
            Write-Host "暂无快照" -ForegroundColor Yellow
            exit 0
        }

        # 按技能分组
        $Skills = $AllTags | ForEach-Object { ($_ -split "/")[0] } | Sort-Object -Unique

        foreach ($Skill in $Skills) {
            $SkillTags = git tag -l "$Skill/v*" 2>$null | Sort-Object { [int]($_ -replace ".*v", "") }
            $Count = @($SkillTags).Count
            $Latest = @($SkillTags)[-1] -replace ".*/"
            Write-Host "  $Skill ($Count 个版本, 最新: $Latest)" -ForegroundColor White
        }

        Write-Host ""
        Write-Host "查看特定技能: list <skill-name>" -ForegroundColor Yellow
    }
    else {
        # 列出指定技能的快照
        $AvailableTags = git tag -l "$SkillName/v*" 2>$null | Sort-Object { [int]($_ -replace ".*v", "") }

        if ($null -eq $AvailableTags -or $AvailableTags.Count -eq 0) {
            Write-Host "没有找到 $SkillName 的快照" -ForegroundColor Yellow
            exit 0
        }

        Write-Host "=== $SkillName 快照历史 ===" -ForegroundColor Cyan
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
        $Latest = @($AvailableTags)[-1] -replace ".*/"
        Write-Host "最新版本: $Latest" -ForegroundColor Green
    }

}
finally {
    Pop-Location
}

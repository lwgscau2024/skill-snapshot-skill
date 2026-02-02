# ============================================================
# scan.ps1 - Skill Snapshot 扫描脚本 (Windows PowerShell 版本)
# 功能：智能扫描识别哪些技能需要备份
# 用法：.\scan.ps1
# ============================================================

#Requires -Version 5.1
$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# 配置
$SkillsDir = Join-Path $env:USERPROFILE ".claude\skills"
$LocalRepo = Join-Path $env:USERPROFILE ".claude\skill-snapshots"

# 检查技能函数
function Test-Skill {
    param([string]$SkillPath)
    
    $SkillName = Split-Path $SkillPath -Leaf
    
    # 规则 1: archive 目录
    if ($SkillName -eq "archive") {
        return @{ Type = "SKIP"; Name = $SkillName; Reason = "归档目录" }
    }
    
    # 规则 2: 符号链接（外部安装）
    $Item = Get-Item $SkillPath -Force
    if ($Item.LinkType -eq 'SymbolicLink' -or $Item.LinkType -eq 'Junction') {
        return @{ Type = "SKIP"; Name = $SkillName; Reason = "符号链接（外部安装）" }
    }
    
    # 规则 3: 快照工具本身
    if ($SkillName -eq "skill-snapshot") {
        return @{ Type = "SKIP"; Name = $SkillName; Reason = "快照工具本身" }
    }
    
    # 规则 4: 自带 Git 版本控制
    if (Test-Path (Join-Path $SkillPath ".git")) {
        return @{ Type = "SKIP"; Name = $SkillName; Reason = "自带 Git 版本控制" }
    }
    
    # 规则 5: 包含依赖目录
    if ((Test-Path (Join-Path $SkillPath ".venv")) -or (Test-Path (Join-Path $SkillPath "node_modules"))) {
        return @{ Type = "SKIP"; Name = $SkillName; Reason = "包含依赖目录 (.venv/node_modules)" }
    }
    
    # 规则 6: 体积过大 (> 10MB)
    $SizeKB = [math]::Round((Get-ChildItem $SkillPath -Recurse -File -ErrorAction SilentlyContinue | 
            Measure-Object -Property Length -Sum).Sum / 1KB, 0)
    if ($SizeKB -gt 10240) {
        $SizeMB = [math]::Round($SizeKB / 1024, 1)
        return @{ Type = "SKIP"; Name = $SkillName; Reason = "体积过大 (${SizeMB}MB > 10MB)" }
    }
    
    # 规则 7: 缺少 SKILL.md
    if (-not (Test-Path (Join-Path $SkillPath "SKILL.md"))) {
        return @{ Type = "SKIP"; Name = $SkillName; Reason = "缺少 SKILL.md" }
    }
    
    # 通过所有检查，需要备份
    $FileCount = (Get-ChildItem $SkillPath -Recurse -File -ErrorAction SilentlyContinue | 
        Where-Object { $_.Name -ne ".DS_Store" }).Count
    
    if ($SizeKB -ge 1024) {
        $SizeStr = "$([math]::Round($SizeKB / 1024, 1))MB"
    }
    else {
        $SizeStr = "${SizeKB}KB"
    }
    
    # 检查是否已有快照
    $HasSnapshot = ""
    if (Test-Path (Join-Path $LocalRepo ".git")) {
        Push-Location $LocalRepo
        $LatestTag = git tag -l "$SkillName/v*" 2>$null | 
        Sort-Object { [int]($_ -replace ".*v", "") } | 
        Select-Object -Last 1
        Pop-Location
        if ($LatestTag) {
            $HasSnapshot = $LatestTag
        }
    }
    
    return @{ 
        Type     = "BACKUP"
        Name     = $SkillName
        Info     = "$FileCount files, $SizeStr"
        Snapshot = $HasSnapshot
    }
}

# 主逻辑
Write-Host "=== 技能快照扫描 ===" -ForegroundColor Cyan
Write-Host ""

# 收集结果
$BackupList = @()
$SkipList = @()

# 检查技能目录是否存在
if (-not (Test-Path $SkillsDir)) {
    Write-Host "技能目录不存在: $SkillsDir" -ForegroundColor Red
    exit 1
}

# 扫描所有技能目录
Get-ChildItem -Path $SkillsDir -Directory | ForEach-Object {
    $Result = Test-Skill -SkillPath $_.FullName
    if ($Result.Type -eq "BACKUP") {
        $BackupList += $Result
    }
    else {
        $SkipList += $Result
    }
}

# 输出需要备份的
Write-Host "【需要备份】" -ForegroundColor Green
if ($BackupList.Count -eq 0) {
    Write-Host "  (无)" -ForegroundColor DarkGray
}
else {
    foreach ($Item in $BackupList) {
        if ($Item.Snapshot) {
            Write-Host "  ✓ $($Item.Name) ($($Item.Info)) [已有: $($Item.Snapshot)]" -ForegroundColor White
        }
        else {
            Write-Host "  ● $($Item.Name) ($($Item.Info)) [未备份]" -ForegroundColor Yellow
        }
    }
}

Write-Host ""
Write-Host "【跳过】" -ForegroundColor DarkGray
if ($SkipList.Count -eq 0) {
    Write-Host "  (无)" -ForegroundColor DarkGray
}
else {
    foreach ($Item in $SkipList) {
        Write-Host "  ✗ $($Item.Name) - $($Item.Reason)" -ForegroundColor DarkGray
    }
}

# 统计
Write-Host ""
Write-Host "----------------------------------------" -ForegroundColor DarkGray
Write-Host "需要备份: $($BackupList.Count) 个" -ForegroundColor White
Write-Host "跳过: $($SkipList.Count) 个" -ForegroundColor White

# 检查未备份的
$NeedBackup = $BackupList | Where-Object { -not $_.Snapshot }
if ($NeedBackup.Count -gt 0) {
    Write-Host ""
    Write-Host "【待备份】$($NeedBackup.Count) 个技能尚未创建快照:" -ForegroundColor Yellow
    foreach ($Item in $NeedBackup) {
        Write-Host "  - $($Item.Name)" -ForegroundColor Yellow
    }
}

# ============================================================
# diff.ps1 - Skill Snapshot 对比脚本 (Windows PowerShell 版本)
# 功能：对比当前版本与某个历史快照的差异
# 用法：.\diff.ps1 <skill-name> [version]
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
    Write-Host "用法: .\diff.ps1 <skill-name> [version]" -ForegroundColor Yellow
    exit 1
}

$SkillPath = Join-Path $SkillsDir $SkillName

# 检查技能是否存在
if (-not (Test-Path $SkillPath)) {
    Write-Host "错误: 技能不存在: $SkillPath" -ForegroundColor Red
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
    git fetch --tags --quiet 2>$null

    # 获取可用版本
    $AvailableTags = git tag -l "$SkillName/v*" 2>$null | Sort-Object { [int]($_ -replace ".*v", "") }
    
    if ($null -eq $AvailableTags -or $AvailableTags.Count -eq 0) {
        Write-Host "错误: 没有找到 $SkillName 的快照" -ForegroundColor Red
        exit 1
    }

    # 如果没有指定版本，使用最新版本
    if ([string]::IsNullOrEmpty($Version)) {
        $Version = @($AvailableTags)[-1] -replace ".*/"
        Write-Host "使用最新版本: $Version" -ForegroundColor Yellow
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

    Write-Host "=== 对比差异 ===" -ForegroundColor Cyan
    Write-Host "技能: $SkillName" -ForegroundColor White
    Write-Host "快照版本: $Version" -ForegroundColor White
    Write-Host "当前版本: 本地" -ForegroundColor White
    Write-Host ""

    # 创建临时目录
    $TempDir = Join-Path $env:TEMP "skill-snapshot-diff-$(Get-Random)"
    New-Item -ItemType Directory -Path $TempDir -Force | Out-Null

    try {
        # 导出快照版本到临时目录
        git archive $TagName | tar -xf - -C $TempDir 2>$null
        
        $SnapshotPath = Join-Path $TempDir $SkillName

        # 获取所有文件
        $SnapshotFiles = @{}
        $CurrentFiles = @{}
        
        $ExcludePatterns = @('.DS_Store', '__pycache__', '.git', 'node_modules', '.venv')
        
        if (Test-Path $SnapshotPath) {
            Get-ChildItem -Path $SnapshotPath -Recurse -File | Where-Object {
                $Include = $true
                foreach ($Pattern in $ExcludePatterns) {
                    if ($_.FullName -like "*$Pattern*") { $Include = $false; break }
                }
                $Include
            } | ForEach-Object {
                $RelPath = $_.FullName.Substring($SnapshotPath.Length + 1)
                $SnapshotFiles[$RelPath] = $_.FullName
            }
        }

        Get-ChildItem -Path $SkillPath -Recurse -File | Where-Object {
            $Include = $true
            foreach ($Pattern in $ExcludePatterns) {
                if ($_.FullName -like "*$Pattern*") { $Include = $false; break }
            }
            $Include
        } | ForEach-Object {
            $RelPath = $_.FullName.Substring($SkillPath.Length + 1)
            $CurrentFiles[$RelPath] = $_.FullName
        }

        # 比较文件
        $AllFiles = @($SnapshotFiles.Keys) + @($CurrentFiles.Keys) | Sort-Object -Unique
        $HasDiff = $false

        foreach ($File in $AllFiles) {
            $InSnapshot = $SnapshotFiles.ContainsKey($File)
            $InCurrent = $CurrentFiles.ContainsKey($File)

            if ($InSnapshot -and -not $InCurrent) {
                Write-Host "[-] 已删除: $File" -ForegroundColor Red
                $HasDiff = $true
            }
            elseif (-not $InSnapshot -and $InCurrent) {
                Write-Host "[+] 新增: $File" -ForegroundColor Green
                $HasDiff = $true
            }
            else {
                # 比较内容
                $SnapshotContent = Get-Content $SnapshotFiles[$File] -Raw -ErrorAction SilentlyContinue
                $CurrentContent = Get-Content $CurrentFiles[$File] -Raw -ErrorAction SilentlyContinue
                
                if ($SnapshotContent -ne $CurrentContent) {
                    Write-Host "[~] 修改: $File" -ForegroundColor Yellow
                    $HasDiff = $true
                    
                    # 显示详细差异（如果文件较小）
                    $SnapshotLines = $SnapshotContent -split "`n"
                    $CurrentLines = $CurrentContent -split "`n"
                    
                    if ($SnapshotLines.Count -lt 100 -and $CurrentLines.Count -lt 100) {
                        $Diff = Compare-Object -ReferenceObject $SnapshotLines -DifferenceObject $CurrentLines -PassThru
                        if ($Diff) {
                            Write-Host "    ---" -ForegroundColor DarkGray
                            $Diff | Select-Object -First 10 | ForEach-Object {
                                if ($_.SideIndicator -eq "=>") {
                                    Write-Host "    + $_" -ForegroundColor Green
                                }
                                else {
                                    Write-Host "    - $_" -ForegroundColor Red
                                }
                            }
                            if ($Diff.Count -gt 10) {
                                Write-Host "    ... 还有 $($Diff.Count - 10) 处差异" -ForegroundColor DarkGray
                            }
                        }
                    }
                }
            }
        }

        if (-not $HasDiff) {
            Write-Host "✓ 无差异 - 当前版本与 $Version 相同" -ForegroundColor Green
        }

    }
    finally {
        # 清理临时目录
        if (Test-Path $TempDir) {
            Remove-Item $TempDir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

}
finally {
    Pop-Location
}

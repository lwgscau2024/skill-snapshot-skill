# ============================================================
# init.ps1 - Skill Snapshot 初始化脚本 (Windows PowerShell 版本)
# 功能：创建和配置 GitHub 私有仓库及本地克隆
# ============================================================

#Requires -Version 5.1
$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# 配置
$RepoName = "skill-snapshots"
$LocalPath = Join-Path $env:USERPROFILE ".claude\skill-snapshots"

# 检查 GitHub CLI 是否安装
function Test-GhInstalled {
    try {
        $null = Get-Command gh -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

# 检查 Git 是否安装
function Test-GitInstalled {
    try {
        $null = Get-Command git -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

# 主逻辑
Write-Host "=== Skill Snapshot 初始化 ===" -ForegroundColor Cyan
Write-Host ""

# 检查依赖
if (-not (Test-GhInstalled)) {
    Write-Host "错误: 未安装 GitHub CLI (gh)" -ForegroundColor Red
    Write-Host "请访问 https://cli.github.com/ 安装" -ForegroundColor Yellow
    exit 1
}

if (-not (Test-GitInstalled)) {
    Write-Host "错误: 未安装 Git" -ForegroundColor Red
    Write-Host "请访问 https://git-scm.com/ 安装" -ForegroundColor Yellow
    exit 1
}

# 获取 GitHub 用户名
try {
    $GitHubUser = gh api user -q '.login' 2>$null
    if ([string]::IsNullOrEmpty($GitHubUser)) {
        Write-Host "错误: 请先登录 GitHub CLI" -ForegroundColor Red
        Write-Host "执行: gh auth login" -ForegroundColor Yellow
        exit 1
    }
} catch {
    Write-Host "错误: 请先登录 GitHub CLI" -ForegroundColor Red
    Write-Host "执行: gh auth login" -ForegroundColor Yellow
    exit 1
}

Write-Host "GitHub 用户: $GitHubUser" -ForegroundColor Green

# 检查本地仓库是否存在
if (Test-Path (Join-Path $LocalPath ".git")) {
    Write-Host "✓ 本地仓库已存在: $LocalPath" -ForegroundColor Green
    
    # 同步远程更新
    Push-Location $LocalPath
    try {
        git pull --quiet origin main 2>$null
        Write-Host "✓ 已同步远程更新" -ForegroundColor Green
    } catch {
        # 忽略 pull 错误
    }
    Pop-Location
} else {
    # 检查远程仓库是否存在
    $RepoExists = $false
    try {
        $null = gh repo view "$GitHubUser/$RepoName" 2>$null
        $RepoExists = $true
    } catch {
        $RepoExists = $false
    }

    if (-not $RepoExists) {
        # 创建私有仓库
        Write-Host "→ 创建私有仓库..." -ForegroundColor Yellow
        gh repo create $RepoName --private --description "Claude Code Skills Snapshots (私有备份)" --clone=false
        Write-Host "✓ 私有仓库已创建" -ForegroundColor Green
    }

    # 检查仓库是否为空
    $IsEmpty = $false
    try {
        $EmptyCheck = gh repo view "$GitHubUser/$RepoName" --json isEmpty -q '.isEmpty' 2>$null
        $IsEmpty = $EmptyCheck -eq "true"
    } catch {
        $IsEmpty = $true
    }

    if ($IsEmpty) {
        # 空仓库，需要先初始化
        Write-Host "→ 初始化仓库..." -ForegroundColor Yellow
        
        # 创建本地目录
        New-Item -ItemType Directory -Path $LocalPath -Force | Out-Null
        Push-Location $LocalPath
        
        # 初始化 Git
        git init --quiet
        git remote add origin "https://github.com/$GitHubUser/$RepoName.git"
        
        # 创建 README
        @"
# Skill Snapshots

Claude Code 技能快照私有备份仓库。

## 结构

每个技能对应一个目录，使用 Git tags 管理版本：

```
├── <skill-name>/
│   ├── SKILL.md
│   └── scripts/
```

Tags 格式: `<skill-name>/v<n>`

## 使用

此仓库由 `skill-snapshot` 技能自动管理，请勿手动修改。
"@ | Set-Content -Path "README.md" -Encoding UTF8
        
        git add README.md
        git commit --quiet -m "Initial commit"
        git branch -M main
        git push --quiet -u origin main
        
        Pop-Location
        Write-Host "✓ 仓库已初始化" -ForegroundColor Green
    } else {
        # 克隆已存在的仓库
        Write-Host "→ 克隆到本地: $LocalPath" -ForegroundColor Yellow
        git clone --quiet "https://github.com/$GitHubUser/$RepoName.git" $LocalPath
        Write-Host "✓ 已克隆到本地" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "=== 初始化完成 ===" -ForegroundColor Cyan
Write-Host "私有仓库: https://github.com/$GitHubUser/$RepoName" -ForegroundColor White
Write-Host "本地路径: $LocalPath" -ForegroundColor White

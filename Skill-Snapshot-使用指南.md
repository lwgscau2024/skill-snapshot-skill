# Skill-Snapshot 使用指南 (Windows 版)

本指南详细介绍了如何在 Windows 环境下使用 **skill-snapshot** 技能来管理您的 Claude Code 技能版本。

---

## 🎯 简介

Skill-Snapshot 是一个专为 Claude Code 设计的技能版本管理工具。它允许您将本地技能备份到 GitHub 私有仓库，支持版本回退、差异对比等功能。

**Windows 特别版**：本项目已适配 Windows PowerShell，无需 WSL 即可直接运行。

---

## 一、快速开始

在 Claude Code 对话中，您只需要使用**自然语言**即可调用功能。

### 1. 首次使用初始化
首次使用前，请告诉 Claude 初始化仓库：
> **用户**: "初始化技能快照"
> **Claude**: (执行初始化脚本，创建 GitHub 私有仓库)

### 2. 扫描技能状态
查看哪些技能需要备份：
> **用户**: "扫描我的技能" 或 "看看哪些技能需要备份"
> **Claude**: (列出所有技能状态，标记出未备份或有更新的技能)

### 3. 保存快照
为某个技能创建备份：
> **用户**: "保存 gemini-image 技能快照，备注添加了高清模式"
> **Claude**: (创建 v2 版本并推送到远程仓库)

### 4. 恢复版本
如果技能出现问题，可以回退到旧版本：
> **用户**: "把 gemini-image 恢复到 v1 版本"
> **Claude**: (自动备份当前版本，然后回退到 v1)

---

## 二、功能详解与触发词

| 功能 | 常用触发词 | 说明 |
|------|-----------|------|
| **初始化** | "初始化技能快照"<br>"init snapshot" | 创建 `~/.claude/skill-snapshots` 本地仓库和 GitHub 私有仓库。 |
| **扫描** | "扫描技能"<br>"scan skills"<br>"检查备份" | 智能检测所有技能，识别未备份、有变更、需跳过的技能。 |
| **保存** | "保存 [技能] 快照"<br>"备份 [技能]"<br>"snapshot [skill]" | 创建新版本标签 (如 v1, v2)。支持附加备注信息。 |
| **列表** | "查看 [技能] 版本"<br>"列出快照"<br>"list snapshots" | 显示指定技能的所有历史版本、日期和备注。 |
| **恢复** | "恢复 [技能] 到 [版本]"<br>"回退 [技能]"<br>"restore [skill]" | 将本地技能替换为指定版本的快照内容。**操作前会自动备份当前版本**。 |
| **对比** | "对比 [技能] 差异"<br>"diff [skill]" | 比较本地当前版本与指定快照版本的文件内容差异。 |

---

## 三、常见场景示例

### 场景 A：日常备份
1. 输入 "**扫描技能**"，查看哪些技能有更新。
2. 发现 `my-new-skill` 未备份。
3. 输入 "**保存 my-new-skill 快照，完成第一版开发**"。

### 场景 B：版本回退
1. 您修改了 `data-analysis` 技能，但改坏了。
2. 输入 "**查看 data-analysis 版本历史**"。
3. 看到 `v3` 是昨天工作的版本。
4. 输入 "**对比 data-analysis 和 v3 的差异**"，确认改动内容。
5. 输入 "**恢复 data-analysis 到 v3**"。

---

## 四、高级：手动命令参考

如果您更喜欢在 PowerShell 终端直接操作，可以使用以下命令：

```powershell
# 设置执行策略 (首次)
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# 脚本路径变量
$ScriptPath = "$env:USERPROFILE\.claude\skills\skill-snapshot\scripts"

# 1. 初始化
powershell -File "$ScriptPath\init.ps1"

# 2. 扫描
powershell -File "$ScriptPath\scan.ps1"

# 3. 保存 (示例)
powershell -File "$ScriptPath\save.ps1" -SkillName "my-skill" -Message "Daily backup"

# 4. 列表
powershell -File "$ScriptPath\list.ps1" -SkillName "my-skill"

# 5. 恢复
powershell -File "$ScriptPath\restore.ps1" -SkillName "my-skill" -Version "v1"

# 6. 对比
powershell -File "$ScriptPath\diff.ps1" -SkillName "my-skill" -Version "v1"
```

---

## 五、文件结构与配置

- **本地仓库位置**: `C:\Users\<用户>\.claude\skill-snapshots`
- **GitHub 仓库**: 私有仓库 `skill-snapshots`
- **脚本位置**: `C:\Users\<用户>\.claude\skills\skill-snapshot\scripts`

### 跳过规则
扫描时会自动跳过：
- `archive/` 目录
- 外部安装的技能 (符号链接)
- 包含 `.git`, `node_modules`, `.venv` 的目录
- 体积超过 10MB 的技能

---

> **注意**：使用此技能需要系统已安装 **Git** 和 **GitHub CLI (`gh`)**，并已完成 `gh auth login` 登录。

---
name: skill-snapshot
description: 为 Claude Code 技能创建快照并管理版本回退。识别需要备份的技能，将其内容保存到本地仓库并推送到 GitHub 私有仓库。当用户提到“快照”、“snapshot”、“保存技能”、“备份技能”、“回退技能”、“恢复技能”、“restore skill”或使用命令“/skill-snapshot”时使用本技能。
license: Complete terms in LICENSE
---

# Skill Snapshot

为 Claude Code 技能创建快照，支持版本回退。存储在 GitHub 私有仓库。

## 触发词

- "快照"、"snapshot"、"保存技能"、"备份技能"
- "回退技能"、"恢复技能"、"restore skill"
- "/skill-snapshot"

## 命令

### 初始化 (首次使用必须执行)
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command '[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; & "$HOME\.claude\skills\skill-snapshot\scripts\init.ps1"'
```

### 扫描技能
扫描并识别哪些技能需要备份：
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command '[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; & "$HOME\.claude\skills\skill-snapshot\scripts\scan.ps1"'
```

### 保存快照
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command '[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; & "$HOME\.claude\skills\skill-snapshot\scripts\save.ps1" -SkillName "<技能名称>" -Message "<说明>"'
```

### 列出快照
列出所有技能快照：
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command '[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; & "$HOME\.claude\skills\skill-snapshot\scripts\list.ps1"'
```

列出特定技能的快照历史：
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command '[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; & "$HOME\.claude\skills\skill-snapshot\scripts\list.ps1" -SkillName "<技能名称>"'
```

### 恢复快照
查看可恢复版本：
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command '[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; & "$HOME\.claude\skills\skill-snapshot\scripts\restore.ps1" -SkillName "<技能名称>"'
```

恢复到指定版本：
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command '[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; & "$HOME\.claude\skills\skill-snapshot\scripts\restore.ps1" -SkillName "<技能名称>" -Version "v1"'
```

### 对比差异
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command '[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; & "$HOME\.claude\skills\skill-snapshot\scripts\diff.ps1" -SkillName "<技能名称>" -Version "v1"'
```

## 注意事项

1. **符号链接不备份**：通过符号链接安装的外部技能不会被备份
2. **archive 目录忽略**：不对 archive 目录下的技能做快照
3. **首次使用需 init**：首次使用前需执行 `init` 创建仓库
4. **网络依赖**：save/restore 需要网络连接推送到 GitHub

## 跳过规则

扫描时自动跳过以下技能：
- `archive/` 目录 - 归档技能
- 符号链接 - 外部安装的技能
- `skill-snapshot` 自身 - 避免自引用
- 包含 `.git/` - 已有版本控制
- 包含 `.venv/` 或 `node_modules/` - 大型依赖
- 体积 > 10MB - 过大
- 缺少 `SKILL.md` - 非有效技能

## 系统要求

- Windows 10/11
- PowerShell 5.1 或更高版本
- Git 已安装
- GitHub CLI (`gh`) 已安装并登录

## 存储结构

```
~/.claude/skill-snapshots/          # 本地仓库
├── my-skill/
│   ├── SKILL.md
│   └── scripts/
└── README.md

GitHub Tags:
├── my-skill/v1
├── my-skill/v2
└── another-skill/v1
```

## 使用示例

### 首次设置
用户: 初始化技能快照
Claude: [执行 init.ps1 创建私有仓库]

### 保存快照
用户: 保存 my-skill 的快照
Claude: [执行 save.ps1 -SkillName "my-skill"]

### 恢复版本
用户: 把 my-skill 恢复到 v2
Claude: [执行 restore.ps1 -SkillName "my-skill" -Version "v2"]

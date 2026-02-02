---
name: skill-snapshot
description: Claude Code 技能版本快照管理。支持保存、恢复、对比和批量备份技能快照,使用 GitHub 私有仓库存储。基于哈希缓存的智能增量备份,大幅提升批量操作性能。
---

# Skill Snapshot

为 Claude Code 技能创建 Git 版本快照,存储在 GitHub 私有仓库。支持由 Claude 自动管理技能的版本控制。

**✨ 性能优化**: 使用文件哈希缓存系统,`backup-all` 命令可智能跳过未变更的技能,性能提升 10-20倍。

## 前提条件

| 依赖 | 版本要求 | 安装命令 |
|------|----------|----------|
| Python | 3.7+ | 预装或从 python.org 安装 |
| Git | 任意版本 | `winget install Git.Git` |
| GitHub CLI | 任意版本 | `winget install GitHub.cli` |

> 首次使用需执行 `gh auth login` 完成 GitHub 认证。

## 快速指南

所有操作推荐通过 Python 脚本执行,兼容 Windows/macOS/Linux。

### 核心操作

1.  **初始化仓库** (首次必须)
    ```bash
    python scripts/snapshot_manager.py init
    ```

2.  **扫描技能**
    ```bash
    python scripts/snapshot_manager.py scan
    ```

3.  **保存快照**
    ```bash
    python scripts/snapshot_manager.py save <技能名> "<说明>"
    ```

4.  **查看所有快照**
    ```bash
    python scripts/snapshot_manager.py list-all
    ```

5.  **恢复快照**
    ```bash
    python scripts/snapshot_manager.py restore <技能名> [版本]
    ```

6.  **查看状态** (新增)
    ```bash
    python scripts/snapshot_manager.py status
    ```
    显示仓库状态、缓存状态和技能变更检测结果。

## 典型工作流

### 场景 1：技能开发前备份
防止修改出错,先保存当前状态。
```bash
# 1. 确认技能名称
python scripts/snapshot_manager.py scan

# 2. 保存快照
python scripts/snapshot_manager.py save my-skill "refactoring-start"
```

### 场景 2：恢复到之前的版本
实验失败,回退到稳定版。
```bash
# 1. 查看历史版本
python scripts/snapshot_manager.py list my-skill

# 2. 恢复指定版本
python scripts/snapshot_manager.py restore my-skill v1
```

### 场景 3：查看变更内容
查看当前代码与最新快照的区别。
```bash
python scripts/snapshot_manager.py diff my-skill
```

### 场景 4：缓存维护
优化版本使用文件哈希缓存加速 `backup-all`。如需维护缓存:
```bash
# 重建所有技能的缓存
python scripts/snapshot_manager.py rebuild-cache

# 清除所有缓存(下次运行会自动重建)
python scripts/snapshot_manager.py clear-cache
```

### 常见问题 (FAQ)

#### Q: 如何查看哈希缓存文件？

缓存文件存储在**快照仓库**的隐藏目录中，而不是技能代码目录。

**Windows 默认路径**:
`C:\Users\38259\.claude\skill-snapshots\.snapshot_cache\`

**查看缓存文件列表**:
```bash
# 列出所有缓存文件
dir C:\Users\38259\.claude\skill-snapshots\.snapshot_cache
```

**查看特定技能的缓存内容**:
```bash
# 查看 crawler-launcher 的缓存
type C:\Users\38259\.claude\skill-snapshots\.snapshot_cache\crawler-launcher.json
```

注意：目录名以 `.` 开头（`.snapshot_cache`），在某些文件管理器中默认是隐藏的。

## 更多资源

-   **[完整命令参考](references/commands.md)**: 包含删除、批量备份 (`backup-all`)、跳过规则和敏感文件过滤的详细说明。
-   **[故障排除](references/errors.md)**: 常见错误与解决方案。

# 故障排除 (Troubleshooting)

如果在使用 `skill-snapshot` 时遇到问题，请参考下表解决方案。

| 错误信息 | 原因 | 解决方案 |
|----------|------|----------|
| `gh: command not found` | 未安装 GitHub CLI | 执行 `winget install GitHub.cli` (Windows) 或 `brew install gh` (macOS) |
| `Not logged in to GitHub CLI` | GitHub CLI 未认证 | 执行 `gh auth login` 并按提示完成登录 |
| `No network connectivity` | 网络不可用 | 检查网络连接，因需访问 GitHub API |
| `Snapshot repository not initialized` | 本地仓库未初始化 | 执行 `python scripts/snapshot_manager.py init` |
| `Skill not found` | 技能名称错误或技能不存在 | 使用 `scan` 命令查看可用技能名称 |
| `Version not found` | 版本号错误 | 使用 `list <技能名>` 查看正确的版本号 (如 v1, v2) |
| `Cannot save/restore self` | 试图操作 `skill-snapshot` | 出于安全考虑，禁止对本工具自身进行回滚操作 |

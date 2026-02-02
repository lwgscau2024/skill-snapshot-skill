# 命令详情与配置参考

本文档包含 `skill-snapshot` 的完整命令说明及底层配置规则。

> **统一入口**: 推荐使用 `python scripts/snapshot_manager.py` 执行所有操作（跨平台兼容）。

## 命令列表

### 1. 初始化 (`init`)

创建 GitHub 私有仓库并配置本地环境。首次使用必须执行。

```bash
python scripts/snapshot_manager.py init
```

### 2. 扫描技能 (`scan`)

扫描 `skills` 目录，识别可备份的技能。会自动应用[跳过规则](#跳过规则)。

```bash
python scripts/snapshot_manager.py scan
```

### 3. 保存快照 (`save`)

将指定技能保存到本地 Git 仓库并推送到 GitHub。

```bash
python scripts/snapshot_manager.py save <技能名称> "<说明>"
```
*示例*: `python scripts/snapshot_manager.py save my-skill "Fix login bug"`

### 4. 列出快照 (`list`)

查看技能的历史版本。

```bash
# 列出所有快照
python scripts/snapshot_manager.py list
# 或者
python scripts/snapshot_manager.py list-all

# 列出特定技能的快照
python scripts/snapshot_manager.py list <技能名称>
```

### 5. 恢复快照 (`restore`)

将技能恢复到指定版本。**安全机制**: 恢复前会自动备份当前状态，如果恢复失败会自动回滚。

```bash
# 查看可用版本
python scripts/snapshot_manager.py restore <技能名称>

# 恢复到指定版本
python scripts/snapshot_manager.py restore <技能名称> v1
```

### 6. 删除快照 (`delete`)

删除本地和远程的指定版本快照。

```bash
python scripts/snapshot_manager.py delete <技能名称> <版本>
```
*示例*: `python scripts/snapshot_manager.py delete my-skill v1`

### 7. 对比差异 (`diff`)

比较当前工作区代码与快照版本的差异。

```bash
# 与最新快照对比
python scripts/snapshot_manager.py diff <技能名称>

# 与指定版本对比
python scripts/snapshot_manager.py diff <技能名称> v1
```

### 8. 批量备份 (`backup-all`)

对所有符合规则的技能进行快照保存。

```bash
python scripts/snapshot_manager.py backup-all "Weekly backup"
```

---

## 规则说明

### 跳过规则

扫描和备份时会自动跳过以下内容：
1.  `archive/` 目录
2.  符号链接 (Symbolic Links)
3.  `skill-snapshot` 自身 (防止自修改)
4.  包含 `.git/` 的目录
5.  包含 `.venv/` 或 `node_modules/` 的目录
6.  体积 > 10MB 的技能
7.  缺少 `SKILL.md` 的目录

### 敏感文件保护

为了保护隐私，以下文件模式在快照保存时会被 **自动忽略**（不包含在快照中）：
-   `.env`, `.env.*`
-   `*.pem`, `*.key`, `*.crt`
-   `id_rsa`, `id_dsa`
-   `*.log`
-   `__pycache__`, `.DS_Store` 等系统文件

### 存储结构

快照数据存储在用户主目录下的 `.claude` 文件夹中：

```text
~/.claude/skill-snapshots/          # 本地 Git 仓库
├── .git/                           # Git 元数据
├── README.md                       # 仓库说明
├── my-skill/                       # 技能快照内容
│   ├── SKILL.md
│   └── scripts/
└── ...

# Git 标签格式: <skill-name>/v<N>
# 例如: my-skill/v1, my-skill/v2
```

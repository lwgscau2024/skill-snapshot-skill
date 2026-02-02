#!/bin/bash
# ============================================================
# restore.sh - Skill Snapshot 恢复脚本 (macOS/Linux)
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/snapshot_manager.py"

# 检查 Python 环境
PYTHON_CMD=""
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo "错误: 未找到 Python。请安装 Python 3.7+ 并添加到 PATH。" >&2
    exit 1
fi

# 参数: $1 = 技能名称, $2 = 版本（可选）
if [ -z "$1" ]; then
    echo "用法: restore.sh <技能名称> [版本]" >&2
    exit 1
fi

if [ -n "$2" ]; then
    $PYTHON_CMD "$PYTHON_SCRIPT" restore "$1" "$2"
else
    $PYTHON_CMD "$PYTHON_SCRIPT" restore "$1"
fi

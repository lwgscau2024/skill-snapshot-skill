#!/bin/bash
export GCM_INTERACTIVE=never
export GIT_TERMINAL_PROMPT=0

set -e

SKILL_NAME="$1"
VERSION="$2"
SKILLS_DIR="$HOME/.claude/skills"
LOCAL_REPO="$HOME/.claude/skill-snapshots"

if [ -z "$SKILL_NAME" ]; then
    echo "错误: 请指定技能名称"
    echo "用法: restore.sh <skill-name> [version]"
    exit 1
fi

if [ ! -d "$LOCAL_REPO/.git" ]; then
    echo "错误: 仓库未初始化，请先执行 init"
    exit 1
fi

cd "$LOCAL_REPO"

git pull --quiet origin main 2>/dev/null || true
git fetch --tags --quiet

AVAILABLE_TAGS=$(git tag -l "$SKILL_NAME/v*" 2>/dev/null | sort -V)

if [ -z "$AVAILABLE_TAGS" ]; then
    echo "错误: 没有找到 $SKILL_NAME 的快照"
    exit 1
fi

if [ -z "$VERSION" ]; then
    echo "=== $SKILL_NAME 可用版本 ==="
    echo ""
    for tag in $AVAILABLE_TAGS; do
        ver=$(echo "$tag" | sed "s|$SKILL_NAME/||")
        msg=$(git tag -l "$tag" -n1 | sed "s|$tag ||")
        date=$(git log -1 --format="%ci" "$tag" 2>/dev/null | cut -d' ' -f1)
        echo "  $ver - $date - $msg"
    done
    echo ""
    echo "请指定要恢复的版本，如: restore $SKILL_NAME v2"
    exit 0
fi

TAG_NAME="$SKILL_NAME/$VERSION"

if ! git tag -l "$TAG_NAME" | grep -q "$TAG_NAME"; then
    echo "错误: 版本不存在: $TAG_NAME"
    echo "可用版本:"
    echo "$AVAILABLE_TAGS" | sed "s|$SKILL_NAME/||g" | sed 's/^/  /'
    exit 1
fi

SKILL_PATH="$SKILLS_DIR/$SKILL_NAME"

if [ -L "$SKILL_PATH" ]; then
    echo "错误: $SKILL_NAME 是符号链接（外部安装），不支持恢复"
    exit 1
fi

echo "=== 恢复快照 ==="
echo "技能: $SKILL_NAME"
echo "版本: $VERSION"
echo ""

if [ -d "$SKILL_PATH" ]; then
    BACKUP_DIR="$SKILLS_DIR/.snapshot-backup"
    mkdir -p "$BACKUP_DIR"
    BACKUP_NAME="$SKILL_NAME-$(date '+%Y%m%d%H%M%S')"
    cp -r "$SKILL_PATH" "$BACKUP_DIR/$BACKUP_NAME"
    echo "→ 当前版本已备份到: .snapshot-backup/$BACKUP_NAME"
fi

git checkout --quiet "$TAG_NAME"

rm -rf "$SKILL_PATH"
mkdir -p "$SKILL_PATH"
rsync -a --exclude='.git' --exclude='__pycache__' --exclude='.DS_Store' \
    "$LOCAL_REPO/$SKILL_NAME/" "$SKILL_PATH/"

git checkout --quiet main

echo "✓ 已恢复到 $TAG_NAME"
echo "→ 技能位置: $SKILL_PATH"

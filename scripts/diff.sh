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
    echo "用法: diff.sh <skill-name> [version]"
    exit 1
fi

SKILL_PATH="$SKILLS_DIR/$SKILL_NAME"

if [ ! -d "$SKILL_PATH" ]; then
    echo "错误: 技能不存在: $SKILL_PATH"
    exit 1
fi

if [ ! -d "$LOCAL_REPO/.git" ]; then
    echo "错误: 仓库未初始化，请先执行 init"
    exit 1
fi

cd "$LOCAL_REPO"

git fetch --tags --quiet 2>/dev/null || true

AVAILABLE_TAGS=$(git tag -l "$SKILL_NAME/v*" 2>/dev/null | sort -V)

if [ -z "$AVAILABLE_TAGS" ]; then
    echo "没有找到 $SKILL_NAME 的快照，无法对比"
    exit 0
fi

if [ -z "$VERSION" ]; then
    TAG_NAME=$(echo "$AVAILABLE_TAGS" | tail -1)
    VERSION=$(echo "$TAG_NAME" | sed "s|$SKILL_NAME/||")
else
    TAG_NAME="$SKILL_NAME/$VERSION"
    if ! echo "$AVAILABLE_TAGS" | grep -q "^$TAG_NAME$"; then
        echo "错误: 版本不存在: $TAG_NAME"
        echo "可用版本:"
        echo "$AVAILABLE_TAGS" | sed "s|$SKILL_NAME/||g" | sed 's/^/  /'
        exit 1
    fi
fi

echo "=== 对比差异 ==="
echo "技能: $SKILL_NAME"
echo "快照版本: $VERSION"
echo "当前版本: (本地)"
echo ""

TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

git archive "$TAG_NAME" "$SKILL_NAME/" | tar -x -C "$TEMP_DIR"

# 执行 diff
if diff -rq "$TEMP_DIR/$SKILL_NAME" "$SKILL_PATH" --exclude='.DS_Store' --exclude='__pycache__' &>/dev/null; then
    echo "✓ 无差异 - 当前版本与 $VERSION 相同"
else
    echo "--- 快照 ($VERSION)"
    echo "+++ 当前 (本地)"
    echo ""
    diff -ru "$TEMP_DIR/$SKILL_NAME" "$SKILL_PATH" \
        --exclude='.DS_Store' --exclude='__pycache__' \
        | sed "s|$TEMP_DIR/$SKILL_NAME|snapshot|g" \
        | sed "s|$SKILL_PATH|current|g" \
        || true
fi

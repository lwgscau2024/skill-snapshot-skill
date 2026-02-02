#!/bin/bash
export GCM_INTERACTIVE=never
export GIT_TERMINAL_PROMPT=0

set -e

SKILL_NAME="$1"
MESSAGE="$2"
SKILLS_DIR="$HOME/.claude/skills"
LOCAL_REPO="$HOME/.claude/skill-snapshots"

if [ -z "$SKILL_NAME" ]; then
    echo "错误: 请指定技能名称"
    echo "用法: save.sh <skill-name> [message]"
    exit 1
fi

SKILL_PATH="$SKILLS_DIR/$SKILL_NAME"

if [ ! -d "$SKILL_PATH" ]; then
    echo "错误: 技能不存在: $SKILL_PATH"
    exit 1
fi

if [ -L "$SKILL_PATH" ]; then
    echo "错误: $SKILL_NAME 是符号链接（外部安装），不支持快照"
    exit 1
fi

if [ ! -d "$LOCAL_REPO/.git" ]; then
    echo "错误: 仓库未初始化，请先执行 init"
    exit 1
fi

cd "$LOCAL_REPO"

git pull --quiet origin main 2>/dev/null || true
git fetch --tags --quiet

EXISTING_TAGS=$(git tag -l "$SKILL_NAME/v*" 2>/dev/null | sort -V | tail -1)
if [ -z "$EXISTING_TAGS" ]; then
    NEXT_VERSION="v1"
else
    LAST_NUM=$(echo "$EXISTING_TAGS" | sed "s|$SKILL_NAME/v||")
    NEXT_VERSION="v$((LAST_NUM + 1))"
fi

TAG_NAME="$SKILL_NAME/$NEXT_VERSION"

if [ -z "$MESSAGE" ]; then
    MESSAGE="Snapshot at $(date '+%Y-%m-%d %H:%M')"
fi

echo "=== 保存快照 ==="
echo "技能: $SKILL_NAME"
echo "版本: $NEXT_VERSION"
echo "说明: $MESSAGE"
echo ""

rm -rf "$LOCAL_REPO/$SKILL_NAME"
mkdir -p "$LOCAL_REPO/$SKILL_NAME"

cp -r "$SKILL_PATH/"* "$LOCAL_REPO/$SKILL_NAME/"
find "$LOCAL_REPO/$SKILL_NAME" -name ".git" -type d -exec rm -rf {} + 2>/dev/null || true
find "$LOCAL_REPO/$SKILL_NAME" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find "$LOCAL_REPO/$SKILL_NAME" -name ".DS_Store" -type f -delete 2>/dev/null || true

git add "$SKILL_NAME/"

if git diff --cached --quiet; then
    echo "✓ 无变化 - 内容与最新快照相同，无需保存"
    LATEST_TAG=$(git tag -l "$SKILL_NAME/v*" 2>/dev/null | sort -V | tail -1)
    if [ -n "$LATEST_TAG" ]; then
        echo "→ 最新快照: $LATEST_TAG"
    fi
    exit 0
fi

git commit --quiet -m "[$SKILL_NAME] $NEXT_VERSION: $MESSAGE"
git tag -a "$TAG_NAME" -m "$MESSAGE"
git push --quiet origin main
git push --quiet origin "$TAG_NAME"

echo "✓ 快照已保存: $TAG_NAME"
echo "→ 可用 'restore $SKILL_NAME $NEXT_VERSION' 恢复"

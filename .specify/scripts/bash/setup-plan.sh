#!/usr/bin/env bash

set -e

# 解析命令行参数
JSON_MODE=false
ARGS=()

for arg in "$@"; do
    case "$arg" in
        --json) JSON_MODE=true ;;
        --help|-h) 
            echo "用法: $0 [--json]"
            exit 0 
            ;; 
        *) ARGS+=("$arg") ;; 
    esac
done

SCRIPT_DIR="$(CDPATH="" cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# 从通用函数获取所有路径和变量
eval $(get_feature_paths)

# [优化] 仅警告，不要退出。
# 这支持在保留在 main 分支上的同时创建计划。
check_feature_branch "$CURRENT_BRANCH" "$HAS_GIT" || true

# 确保功能目录存在
mkdir -p "$FEATURE_DIR"

# 如果存在，复制计划模板
TEMPLATE="$REPO_ROOT/.specify/templates/plan-template.md"
if [[ -f "$TEMPLATE" ]]; then
    cp "$TEMPLATE" "$IMPL_PLAN"
    if ! $JSON_MODE; then echo "已将计划模板复制到 $IMPL_PLAN"; fi
else
    if ! $JSON_MODE; then echo "警告: 未在 $TEMPLATE 找到计划模板"; fi
    touch "$IMPL_PLAN"
fi

# 输出结果
if $JSON_MODE; then
    printf '{"FEATURE_SPEC":"%s","IMPL_PLAN":"%s","SPECS_DIR":"%s","BRANCH":"%s","FEATURE_NAME":"%s"}\n' \
        "$FEATURE_SPEC" "$IMPL_PLAN" "$FEATURE_DIR" "$CURRENT_BRANCH" "$FEATURE_NAME"
else
    echo "FEATURE_SPEC: $FEATURE_SPEC"
    echo "IMPL_PLAN: $IMPL_PLAN" 
    echo "SPECS_DIR: $FEATURE_DIR"
    echo "FEATURE_NAME: $FEATURE_NAME" # 使用逻辑名称
    echo "GIT_BRANCH: $CURRENT_BRANCH" # 显示物理分支
fi

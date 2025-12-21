#!/usr/bin/env bash

# 综合先决条件检查脚本
# 针对灵活的 git 工作流进行了优化

set -e

# 解析命令行参数
JSON_MODE=false
REQUIRE_TASKS=false
INCLUDE_TASKS=false
PATHS_ONLY=false

for arg in "$@"; do
    case "$arg" in
        --json) JSON_MODE=true ;;
        --require-tasks) REQUIRE_TASKS=true ;;
        --include-tasks) INCLUDE_TASKS=true ;;
        --paths-only) PATHS_ONLY=true ;;
        --help|-h) 
            echo "用法: check-prerequisites.sh [选项]"
            exit 0
            ;;
        *) 
            echo "错误: 未知选项 '$arg'." >&2
            exit 1
            ;;
    esac
done

# 源公共函数
SCRIPT_DIR="$(CDPATH="" cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# 获取功能路径
eval $(get_feature_paths)

# [优化] 验证分支但不因不匹配而退出
# 这允许在针对规范文件夹的同时在 'main' 上工作
check_feature_branch "$CURRENT_BRANCH" "$HAS_GIT" || true

# 如果是仅路径模式，输出路径并退出
if $PATHS_ONLY; then
    if $JSON_MODE; then
        printf '{"REPO_ROOT":"%s","BRANCH":"%s","FEATURE_NAME":"%s","FEATURE_DIR":"%s","FEATURE_SPEC":"%s","IMPL_PLAN":"%s","TASKS":"%s"}\n' \
            "$REPO_ROOT" "$CURRENT_BRANCH" "$FEATURE_NAME" "$FEATURE_DIR" "$FEATURE_SPEC" "$IMPL_PLAN" "$TASKS"
    else
        echo "REPO_ROOT: $REPO_ROOT"
        echo "BRANCH: $CURRENT_BRANCH"
        echo "FEATURE_NAME: $FEATURE_NAME"
        echo "FEATURE_DIR: $FEATURE_DIR"
        echo "FEATURE_SPEC: $FEATURE_SPEC"
        echo "IMPL_PLAN: $IMPL_PLAN"
        echo "TASKS: $TASKS"
    fi
    exit 0
fi

# 验证所需的目录和文件
# 我们依赖目录的存在而不是 git 分支名称
if [[ ! -d "$FEATURE_DIR" ]]; then
    echo "错误: 未找到功能目录: $FEATURE_DIR" >&2
    echo "当前上下文指向: $FEATURE_NAME" >&2
    echo "请先运行 /speckit.specify 以创建功能结构。" >&2
    exit 1
fi

if [[ ! -f "$IMPL_PLAN" ]]; then
    echo "错误: 在 $FEATURE_DIR 中未找到 plan.md" >&2
    echo "请先运行 /speckit.plan 以创建实施计划。" >&2
    exit 1
fi

# 如果需要，检查 tasks.md
if $REQUIRE_TASKS && [[ ! -f "$TASKS" ]]; then
    echo "错误: 在 $FEATURE_DIR 中未找到 tasks.md" >&2
    echo "请先运行 /speckit.tasks 以创建任务列表。" >&2
    exit 1
fi

# 构建可用文档列表
docs=()
[[ -f "$RESEARCH" ]] && docs+=("research.md")
[[ -f "$DATA_MODEL" ]] && docs+=("data-model.md")
if [[ -d "$CONTRACTS_DIR" ]] && [[ -n "$(ls -A "$CONTRACTS_DIR" 2>/dev/null)" ]]; then
    docs+=("contracts/")
fi
[[ -f "$QUICKSTART" ]] && docs+=("quickstart.md")
if $INCLUDE_TASKS && [[ -f "$TASKS" ]]; then
    docs+=("tasks.md")
fi

# 输出结果
if $JSON_MODE; then
    if [[ ${#docs[@]} -eq 0 ]]; then
        json_docs="[]"
    else
        json_docs=$(printf '"%s",' "${docs[@]}")
        json_docs="[${json_docs%,}]"
    fi
    printf '{"FEATURE_DIR":"%s","AVAILABLE_DOCS":%s}\n' "$FEATURE_DIR" "$json_docs"
else
    echo "FEATURE_DIR:$FEATURE_DIR"
    echo "AVAILABLE_DOCS:"
    check_file "$RESEARCH" "research.md"
    check_file "$DATA_MODEL" "data-model.md"
    check_dir "$CONTRACTS_DIR" "contracts/"
    check_file "$QUICKSTART" "quickstart.md"
    if $INCLUDE_TASKS; then
        check_file "$TASKS" "tasks.md"
    fi
fi

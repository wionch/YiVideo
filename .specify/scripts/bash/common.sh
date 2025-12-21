#!/usr/bin/env bash
# 所有脚本的通用函数和变量

# 获取仓库根目录，为非 git 仓库提供回退
get_repo_root() {
    if git rev-parse --show-toplevel >/dev/null 2>&1; then
        git rev-parse --show-toplevel
    else
        # 为非 git 仓库回退到脚本位置
        local script_dir="$(CDPATH="" cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        (cd "$script_dir/../../.." && pwd)
    fi
}

# 获取当前上下文（逻辑功能名称），与 Git 分支区分开
get_current_feature_context() {
    # 1. 高优先级：显式环境变量（由 create-new-feature.sh 设置）
    if [[ -n "${SPECIFY_FEATURE:-}" ]]; then
        echo "$SPECIFY_FEATURE"
        return
    fi

    # 2. 检查实际 Git 分支是否看起来像一个功能 (###-name)
    if git rev-parse --abbrev-ref HEAD >/dev/null 2>&1; then
        local git_branch=$(git rev-parse --abbrev-ref HEAD)
        if [[ "$git_branch" =~ ^[0-9]{3}- ]]; then
            echo "$git_branch"
            return
        fi
    fi

    # 3. 回退：尝试在 specs/ 中查找最新修改的功能目录
    # 这允许在 "main" 上工作，同时上下文暗示最新的规范
    local repo_root=$(get_repo_root)
    local specs_dir="$repo_root/specs"

    if [[ -d "$specs_dir" ]]; then
        local latest_feature=""
        local highest=0

        for dir in "$specs_dir"/*; do
            if [[ -d "$dir" ]]; then
                local dirname=$(basename "$dir")
                if [[ "$dirname" =~ ^([0-9]{3})- ]]; then
                    local number=${BASH_REMATCH[1]}
                    number=$((10#$number))
                    if [[ "$number" -gt "$highest" ]]; then
                        highest=$number
                        latest_feature=$dirname
                    fi
                fi
            fi
        done

        if [[ -n "$latest_feature" ]]; then
            echo "$latest_feature"
            return
        fi
    fi

    # 4. 最终回退：仅返回 git 分支（例如，main）
    if git rev-parse --abbrev-ref HEAD >/dev/null 2>&1; then
        git rev-parse --abbrev-ref HEAD
    else
        echo "main"
    fi
}

# 检查我们是否有 git 可用
has_git() {
    git rev-parse --show-toplevel >/dev/null 2>&1
}

check_feature_branch() {
    local branch="$1"
    local has_git_repo="$2"

    # 对于非 git 仓库，跳过验证
    if [[ "$has_git_repo" != "true" ]]; then
        return 0
    fi

    # [优化]
    # 放宽验证：如果不匹配模式则警告但不要失败。
    # 这允许用户在 'main' 或特定实现分支上工作
    # 同时将规范保留在 'specs/001-xxx' 中。
    if [[ ! "$branch" =~ ^[0-9]{3}- ]]; then
        echo "[specify] 注意：当前 Git 分支 '$branch' 不匹配功能模式 (###-name)。" >&2
        echo "[specify] 继续使用逻辑功能上下文。" >&2
        # 返回 0 (成功) 以允许脚本继续
        return 0
    fi

    return 0
}

get_feature_dir() { echo "$1/specs/$2"; }

# 通过前缀或精确匹配查找功能目录
find_feature_dir_by_prefix() {
    local repo_root="$1"
    local feature_name="$2"
    local specs_dir="$repo_root/specs"

    # 提取数字前缀（例如，从 "004-whatever" 中提取 "004"）
    if [[ ! "$feature_name" =~ ^([0-9]{3})- ]]; then
        echo "$specs_dir/$feature_name"
        return
    fi

    local prefix="${BASH_REMATCH[1]}"

    # 在 specs/ 中搜索以此前缀开头的目录
    local matches=()
    if [[ -d "$specs_dir" ]]; then
        for dir in "$specs_dir"/"$prefix"-*; do
            if [[ -d "$dir" ]]; then
                matches+=("$(basename "$dir")")
            fi
        done
    fi

    if [[ ${#matches[@]} -eq 1 ]]; then
        echo "$specs_dir/${matches[0]}"
    else
        echo "$specs_dir/$feature_name"
    fi
}

get_feature_paths() {
    local repo_root=$(get_repo_root)
    # 获取逻辑功能名称（可能与 git 分支不同）
    local current_feature=$(get_current_feature_context)
    
    # 获取实际 git 分支以供参考
    local actual_git_branch="unknown"
    if has_git; then
        actual_git_branch=$(git rev-parse --abbrev-ref HEAD)
    fi
    local has_git_repo=$(has_git && echo "true" || echo "false")

    # 使用基于前缀的查找来查找物理目录
    local feature_dir=$(find_feature_dir_by_prefix "$repo_root" "$current_feature")
    
    # 提取真实目录名称作为规范的 FEATURE_NAME
    local canonical_feature_name=$(basename "$feature_dir")

    cat <<EOF
REPO_ROOT='$repo_root'
CURRENT_BRANCH='$actual_git_branch'
FEATURE_NAME='$canonical_feature_name'
HAS_GIT='$has_git_repo'
FEATURE_DIR='$feature_dir'
FEATURE_SPEC='$feature_dir/spec.md'
IMPL_PLAN='$feature_dir/plan.md'
TASKS='$feature_dir/tasks.md'
RESEARCH='$feature_dir/research.md'
DATA_MODEL='$feature_dir/data-model.md'
QUICKSTART='$feature_dir/quickstart.md'
CONTRACTS_DIR='$feature_dir/contracts'
EOF
}

check_file() { [[ -f "$1" ]] && echo "  ✓ $2" || echo "  ✗ $2"; }
check_dir() { [[ -d "$1" && -n $(ls -A "$1" 2>/dev/null) ]] && echo "  ✓ $2" || echo "  ✗ $2"; }

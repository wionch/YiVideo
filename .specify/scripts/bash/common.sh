#!/usr/bin/env bash
# Common functions and variables for all scripts

# Get repository root, with fallback for non-git repositories
get_repo_root() {
    if git rev-parse --show-toplevel >/dev/null 2>&1; then
        git rev-parse --show-toplevel
    else
        # Fall back to script location for non-git repos
        local script_dir="$(CDPATH="" cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        (cd "$script_dir/../../.." && pwd)
    fi
}

# Get current context (Logical Feature Name), distinguishing from Git Branch
get_current_feature_context() {
    # 1. High Priority: Explicit environment variable (set by create-new-feature.sh)
    if [[ -n "${SPECIFY_FEATURE:-}" ]]; then
        echo "$SPECIFY_FEATURE"
        return
    fi

    # 2. Check actual Git branch if it looks like a feature (###-name)
    if git rev-parse --abbrev-ref HEAD >/dev/null 2>&1; then
        local git_branch=$(git rev-parse --abbrev-ref HEAD)
        if [[ "$git_branch" =~ ^[0-9]{3}- ]]; then
            echo "$git_branch"
            return
        fi
    fi

    # 3. Fallback: Try to find the latest modified feature directory in specs/
    # This allows working on "main" while context implies the latest spec
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

    # 4. Final Fallback: Just return the git branch (e.g., main)
    if git rev-parse --abbrev-ref HEAD >/dev/null 2>&1; then
        git rev-parse --abbrev-ref HEAD
    else
        echo "main"
    fi
}

# Check if we have git available
has_git() {
    git rev-parse --show-toplevel >/dev/null 2>&1
}

check_feature_branch() {
    local branch="$1"
    local has_git_repo="$2"

    # For non-git repos, skip validation
    if [[ "$has_git_repo" != "true" ]]; then
        return 0
    fi

    # [OPTIMIZATION]
    # Relaxed validation: Warn but DO NOT fail if branch doesn't match pattern.
    # This allows users to work on 'main' or specific implementation branches
    # while keeping specs in 'specs/001-xxx'.
    if [[ ! "$branch" =~ ^[0-9]{3}- ]]; then
        echo "[specify] Note: Current Git branch '$branch' does not match feature pattern (###-name)." >&2
        echo "[specify] Proceeding with logical feature context." >&2
        # Return 0 (success) to allow the script to continue
        return 0
    fi

    return 0
}

get_feature_dir() { echo "$1/specs/$2"; }

# Find feature directory by prefix or exact match
find_feature_dir_by_prefix() {
    local repo_root="$1"
    local feature_name="$2"
    local specs_dir="$repo_root/specs"

    # Extract numeric prefix (e.g., "004" from "004-whatever")
    if [[ ! "$feature_name" =~ ^([0-9]{3})- ]]; then
        echo "$specs_dir/$feature_name"
        return
    fi

    local prefix="${BASH_REMATCH[1]}"

    # Search for directories in specs/ that start with this prefix
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
    # Get the logical feature name (may differ from git branch)
    local current_feature=$(get_current_feature_context)
    
    # Get actual git branch for reference
    local actual_git_branch="unknown"
    if has_git; then
        actual_git_branch=$(git rev-parse --abbrev-ref HEAD)
    fi
    local has_git_repo=$(has_git && echo "true" || echo "false")

    # Use prefix-based lookup to find the physical directory
    local feature_dir=$(find_feature_dir_by_prefix "$repo_root" "$current_feature")
    
    # Extract the true directory name as the canonical FEATURE_NAME
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
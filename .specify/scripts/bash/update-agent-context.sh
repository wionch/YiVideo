#!/usr/bin/env bash

# 使用来自 plan.md 的信息更新代理上下文文件
# 优化为使用功能名称而不是 Git 分支进行文档记录

set -e
set -u
set -o pipefail

#==============================================================================
# 配置和全局变量
#==============================================================================

SCRIPT_DIR="$(CDPATH="" cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# 从通用函数获取所有路径和变量
eval $(get_feature_paths)

# [优化] 使用 FEATURE_NAME（逻辑文件夹名称）作为文档 ID
# 确保即使在 'main' 分支上记录也是正确的。
DOC_ID="$FEATURE_NAME"

NEW_PLAN="$IMPL_PLAN"
AGENT_TYPE="${1:-}"

# 代理特定文件路径（未更改）
CLAUDE_FILE="$REPO_ROOT/CLAUDE.md"
GEMINI_FILE="$REPO_ROOT/GEMINI.md"
COPILOT_FILE="$REPO_ROOT/.github/agents/copilot-instructions.md"
CURSOR_FILE="$REPO_ROOT/.cursor/rules/specify-rules.mdc"
QWEN_FILE="$REPO_ROOT/QWEN.md"
AGENTS_FILE="$REPO_ROOT/AGENTS.md"
WINDSURF_FILE="$REPO_ROOT/.windsurf/rules/specify-rules.md"
KILOCODE_FILE="$REPO_ROOT/.kilocode/rules/specify-rules.md"
AUGGIE_FILE="$REPO_ROOT/.augment/rules/specify-rules.md"
ROO_FILE="$REPO_ROOT/.roo/rules/specify-rules.md"
CODEBUDDY_FILE="$REPO_ROOT/CODEBUDDY.md"
QODER_FILE="$REPO_ROOT/QODER.md"
AMP_FILE="$REPO_ROOT/AGENTS.md"
SHAI_FILE="$REPO_ROOT/SHAI.md"
Q_FILE="$REPO_ROOT/AGENTS.md"
BOB_FILE="$REPO_ROOT/AGENTS.md"

TEMPLATE_FILE="$REPO_ROOT/.specify/templates/agent-file-template.md"

# 解析计划数据的全局变量
NEW_LANG=""
NEW_FRAMEWORK=""
NEW_DB=""
NEW_PROJECT_TYPE=""

#==============================================================================
# 实用函数
#==============================================================================

log_info() { echo "信息: $1"; }
log_success() { echo "✓ $1"; }
log_error() { echo "错误: $1" >&2; }
log_warning() { echo "警告: $1" >&2; }

cleanup() {
    local exit_code=$?
    rm -f /tmp/agent_update_*_$$
    exit $exit_code
}
trap cleanup EXIT INT TERM

#==============================================================================
# 验证函数
#==============================================================================

validate_environment() {
    # [优化] 检查功能目录而不是严格的分支匹配
    if [[ -z "$FEATURE_NAME" ]]; then
        log_error "无法确定当前功能上下文"
        log_info "请先设置 SPECIFY_FEATURE 环境变量或创建一个功能"
        exit 1
    fi
    
    if [[ ! -f "$NEW_PLAN" ]]; then
        log_error "在 $NEW_PLAN 未找到 plan.md"
        log_info "当前上下文: $FEATURE_NAME"
        exit 1
    fi
    
    if [[ ! -f "$TEMPLATE_FILE" ]]; then
        log_warning "在 $TEMPLATE_FILE 未找到模板文件"
    fi
}

#==============================================================================
# 计划解析函数（逻辑不变，仅合并）
#==============================================================================

extract_plan_field() {
    local field_pattern="$1"
    local plan_file="$2"
    grep "^**${field_pattern}**: " "$plan_file" 2>/dev/null | \
        head -1 | sed "s|^fected**${field_pattern}**: ||" | \
        sed 's/^[ 	]*//;s/[ 	]*$//' | grep -v "NEEDS CLARIFICATION" | grep -v "^N/A$" || echo ""
}

parse_plan_data() {
    local plan_file="$1"
    if [[ ! -f "$plan_file" ]]; then return 1; fi
    
    log_info "正在解析功能 $DOC_ID 的计划数据"
    
    NEW_LANG=$(extract_plan_field "Language/Version" "$plan_file")
    NEW_FRAMEWORK=$(extract_plan_field "Primary Dependencies" "$plan_file")
    NEW_DB=$(extract_plan_field "Storage" "$plan_file")
    NEW_PROJECT_TYPE=$(extract_plan_field "Project Type" "$plan_file")
}

format_technology_stack() {
    local lang="$1"
    local framework="$2"
    local parts=()
    [[ -n "$lang" && "$lang" != "NEEDS CLARIFICATION" ]] && parts+=("$lang")
    [[ -n "$framework" && "$framework" != "NEEDS CLARIFICATION" && "$framework" != "N/A" ]] && parts+=("$framework")
    
    if [[ ${#parts[@]} -eq 0 ]]; then echo ""; elif [[ ${#parts[@]} -eq 1 ]]; then echo "${parts[0]}"; else
        local result="${parts[0]}"
        for ((i=1; i<${#parts[@]}; i++)); do result="$result + ${parts[i]}"; done
        echo "$result"
    fi
}

#==============================================================================
# 模板和内容生成函数
#==============================================================================

get_project_structure() {
    local project_type="$1"
    if [[ "$project_type" == *"web"* ]]; then echo "backend/\nfrontend/\ntests/"; else echo "src/\ntests/"; fi
}

get_commands_for_language() {
    local lang="$1"
    case "$lang" in
        *"Python"*) echo "cd src && pytest && ruff check ." ;;
        *"Rust"*) echo "cargo test && cargo clippy" ;;
        *"JavaScript"*|*"TypeScript"*) echo "npm test \&\& npm run lint" ;;
        *) echo "# 为 $lang 添加命令" ;;
    esac
}

get_language_conventions() {
    local lang="$1"
    echo "$lang: 遵循标准约定"
}

create_new_agent_file() {
    local target_file="$1"
    local temp_file="$2"
    local project_name="$3"
    local current_date="$4"
    
    if ! cp "$TEMPLATE_FILE" "$temp_file"; then return 1; fi
    
    local project_structure=$(get_project_structure "$NEW_PROJECT_TYPE")
    local commands=$(get_commands_for_language "$NEW_LANG")
    local language_conventions=$(get_language_conventions "$NEW_LANG")
    
    local escaped_lang=$(printf '%s\n' "$NEW_LANG" | sed 's/[\\\[\.\*^$()+{}|]/\\&/g')
    local escaped_framework=$(printf '%s\n' "$NEW_FRAMEWORK" | sed 's/[\\\[\.\*^$()+{}|]/\\&/g')
    # [优化] 使用 DOC_ID (功能名称) 而不是原始分支名称
    local escaped_branch=$(printf '%s\n' "$DOC_ID" | sed 's/[\\\[\.\*^$()+{}|]/\\&/g')
    
    local tech_stack
    if [[ -n "$escaped_lang" && -n "$escaped_framework" ]]; then
        tech_stack="- $escaped_lang + $escaped_framework ($escaped_branch)"
    elif [[ -n "$escaped_lang" ]]; then
        tech_stack="- $escaped_lang ($escaped_branch)"
    else
        tech_stack="- ($escaped_branch)"
    fi

    local recent_change
    if [[ -n "$escaped_lang" ]]; then
        recent_change="- $escaped_branch: 添加了 $escaped_lang"
    else
        recent_change="- $escaped_branch: 添加了新功能"
    fi

    local substitutions=(
        "s|\\[PROJECT NAME\\]|$project_name|"
        "s|\\[DATE\\]|$current_date|"
        "s|\\[EXTRACTED FROM ALL PLAN.MD FILES\\]|$tech_stack|"
        "s|\\[ACTUAL STRUCTURE FROM PLANS\\]|$project_structure|g"
        "s|\\[ONLY COMMANDS FOR ACTIVE TECHNOLOGIES\\]|$commands|"
        "s|\\[LANGUAGE-SPECIFIC, ONLY FOR LANGUAGES IN USE\\]|$language_conventions|"
        "s|\\[LAST 3 FEATURES AND WHAT THEY ADDED\\]|$recent_change|"
    )
    
    for substitution in "${substitutions[@]}"; do
        sed -i.bak -e "$substitution" "$temp_file"
    done
    
    newline=$(printf '\n')
    sed -i.bak2 "s/\\\\n/${newline}/g" "$temp_file"
    rm -f "$temp_file.bak" "$temp_file.bak2"
    return 0
}

update_existing_agent_file() {
    local target_file="$1"
    local current_date="$2"
    
    log_info "正在更新现有的代理上下文文件..."
    local temp_file=$(mktemp) || return 1
    
    local tech_stack=$(format_technology_stack "$NEW_LANG" "$NEW_FRAMEWORK")
    local new_tech_entries=()
    local new_change_entry=""
    
    # [优化] 使用 DOC_ID (功能名称) 作为条目
    if [[ -n "$tech_stack" ]] && ! grep -q "$tech_stack" "$target_file"; then
        new_tech_entries+=("- $tech_stack ($DOC_ID)")
    fi
    
    if [[ -n "$NEW_DB" ]] && [[ "$NEW_DB" != "N/A" ]] && [[ "$NEW_DB" != "NEEDS CLARIFICATION" ]] && ! grep -q "$NEW_DB" "$target_file"; then
        new_tech_entries+=("- $NEW_DB ($DOC_ID)")
    fi
    
    if [[ -n "$tech_stack" ]]; then
        new_change_entry="- $DOC_ID: 添加了 $tech_stack"
    elif [[ -n "$NEW_DB" ]] && [[ "$NEW_DB" != "N/A" ]]; then
        new_change_entry="- $DOC_ID: 添加了 $NEW_DB"
    fi
    
    # 逐行处理文件 (逻辑保持不变，仅上面更改了变量)
    local in_tech_section=false
    local in_changes_section=false
    local tech_entries_added=false
    local changes_entries_added=false
    local existing_changes_count=0
    
    while IFS= read -r line || [[ -n "$line" ]]; do
        if [[ "$line" == "## Active Technologies" ]]; then
            echo "$line" >> "$temp_file"
            in_tech_section=true
            continue
        elif [[ $in_tech_section == true ]] && [[ "$line" =~ ^##[[:space:]] ]]; then
            if [[ $tech_entries_added == false ]] && [[ ${#new_tech_entries[@]} -gt 0 ]]; then
                printf '%s\n' "${new_tech_entries[@]}" >> "$temp_file"
                tech_entries_added=true
            fi
            echo "$line" >> "$temp_file"
            in_tech_section=false
            continue
        elif [[ $in_tech_section == true ]] && [[ -z "$line" ]]; then
            if [[ $tech_entries_added == false ]] && [[ ${#new_tech_entries[@]} -gt 0 ]]; then
                printf '%s\n' "${new_tech_entries[@]}" >> "$temp_file"
                tech_entries_added=true
            fi
            echo "$line" >> "$temp_file"
            continue
        fi
        
        if [[ "$line" == "## Recent Changes" ]]; then
            echo "$line" >> "$temp_file"
            if [[ -n "$new_change_entry" ]]; then
                echo "$new_change_entry" >> "$temp_file"
            fi
            in_changes_section=true
            changes_entries_added=true
            continue
        elif [[ $in_changes_section == true ]] && [[ "$line" =~ ^##[[:space:]] ]]; then
            echo "$line" >> "$temp_file"
            in_changes_section=false
            continue
        elif [[ $in_changes_section == true ]] && [[ "$line" == "- "* ]]; then
            if [[ $existing_changes_count -lt 2 ]]; then
                echo "$line" >> "$temp_file"
                ((existing_changes_count++))
            fi
            continue
        fi
        
        if [[ "$line" =~ \*\*Last\ updated\*\*:.*[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] ]]; then
            echo "$line" | sed "s/[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]/$current_date/" >> "$temp_file"
        else
            echo "$line" >> "$temp_file"
        fi
    done < "$target_file"
    
    # 如果部分缺失则追加
    if [[ $in_tech_section == true ]] && [[ $tech_entries_added == false ]] && [[ ${#new_tech_entries[@]} -gt 0 ]]; then
        printf '%s\n' "${new_tech_entries[@]}" >> "$temp_file"
    fi
    
    if ! grep -q "^## Active Technologies" "$target_file" && [[ ${#new_tech_entries[@]} -gt 0 ]]; then
        echo "" >> "$temp_file"; echo "## Active Technologies" >> "$temp_file"
        printf '%s\n' "${new_tech_entries[@]}" >> "$temp_file"
    fi
    
    if ! grep -q "^## Recent Changes" "$target_file" && [[ -n "$new_change_entry" ]]; then
        echo "" >> "$temp_file"; echo "## Recent Changes" >> "$temp_file"
        echo "$new_change_entry" >> "$temp_file"
    fi
    
    mv "$temp_file" "$target_file"
    return 0
}

#==============================================================================
# 主代理文件更新函数 (简化)
#==============================================================================

update_agent_file() {
    local target_file="$1"
    local agent_name="$2"
    local project_name=$(basename "$REPO_ROOT")
    local current_date=$(date +%Y-%m-%d)
    
    local target_dir=$(dirname "$target_file")
    mkdir -p "$target_dir"
    
    if [[ ! -f "$target_file" ]]; then
        local temp_file=$(mktemp) || return 1
        if create_new_agent_file "$target_file" "$temp_file" "$project_name" "$current_date"; then
            mv "$temp_file" "$target_file"
            log_success "创建了新的 $agent_name 文件"
        else
            rm -f "$temp_file"; return 1
        fi
    else
        update_existing_agent_file "$target_file" "$current_date" && log_success "更新了 $agent_name 文件"
    fi
}

#==============================================================================
# 代理选择 (简化 Case 语句)
#==============================================================================

update_specific_agent() {
    local agent_type="$1"
    case "$agent_type" in
        claude) update_agent_file "$CLAUDE_FILE" "Claude Code" ;;
        gemini) update_agent_file "$GEMINI_FILE" "Gemini CLI" ;;
        copilot) update_agent_file "$COPILOT_FILE" "GitHub Copilot" ;;
        cursor-agent) update_agent_file "$CURSOR_FILE" "Cursor IDE" ;;
        qwen) update_agent_file "$QWEN_FILE" "Qwen Code" ;;
        opencode) update_agent_file "$AGENTS_FILE" "opencode" ;;
        codex) update_agent_file "$AGENTS_FILE" "Codex CLI" ;;
        windsurf) update_agent_file "$WINDSURF_FILE" "Windsurf" ;;
        kilocode) update_agent_file "$KILOCODE_FILE" "Kilo Code" ;;
        auggie) update_agent_file "$AUGGIE_FILE" "Auggie CLI" ;;
        roo) update_agent_file "$ROO_FILE" "Roo Code" ;;
        codebuddy) update_agent_file "$CODEBUDDY_FILE" "CodeBuddy CLI" ;;
        qoder) update_agent_file "$QODER_FILE" "Qoder CLI" ;;
        amp) update_agent_file "$AMP_FILE" "Amp" ;;
        shai) update_agent_file "$SHAI_FILE" "SHAI" ;;
        q) update_agent_file "$Q_FILE" "Amazon Q Developer CLI" ;;
        bob) update_agent_file "$BOB_FILE" "IBM Bob" ;;
        *) log_error "未知的代理类型 '$agent_type'"; exit 1 ;;
    esac
}

update_all_existing_agents() {
    local found_agent=false
    local files=("$CLAUDE_FILE" "$GEMINI_FILE" "$COPILOT_FILE" "$CURSOR_FILE" "$QWEN_FILE" "$AGENTS_FILE" "$WINDSURF_FILE" "$KILOCODE_FILE" "$AUGGIE_FILE" "$ROO_FILE" "$CODEBUDDY_FILE" "$SHAI_FILE" "$QODER_FILE" "$Q_FILE" "$BOB_FILE")
    local names=("Claude" "Gemini" "Copilot" "Cursor" "Qwen" "Agents" "Windsurf" "Kilo" "Auggie" "Roo" "CodeBuddy" "SHAI" "Qoder" "Amazon Q" "Bob")
    
    for i in "${!files[@]}"; do
        if [[ -f "${files[$i]}" ]]; then
            update_agent_file "${files[$i]}" "${names[$i]}"
            found_agent=true
        fi
    done
    
    if [[ "$found_agent" == false ]]; then
        log_info "未找到现有的代理文件，正在创建默认的 Claude 文件..."
        update_agent_file "$CLAUDE_FILE" "Claude Code"
    fi
}

main() {
    validate_environment
    log_info "=== 正在更新功能 $DOC_ID 的代理上下文 ===" # 使用功能名称记录
    parse_plan_data "$NEW_PLAN"
    
    if [[ -z "$AGENT_TYPE" ]]; then
        update_all_existing_agents
    else
        update_specific_agent "$AGENT_TYPE"
    fi
    
    echo
    log_info "摘要:"
    [[ -n "$NEW_LANG" ]] && echo "  - 语言: $NEW_LANG"
    [[ -n "$NEW_FRAMEWORK" ]] && echo "  - 框架: $NEW_FRAMEWORK"
    log_success "更新完成"
}

if [[ "	${BASH_SOURCE[0]}" == "	${0}" ]]; then main "$@"; fi
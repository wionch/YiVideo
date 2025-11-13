#!/usr/bin/env python3
"""
Serena 强制使用工具
拦截 Bash/Read/Grep 的代码分析操作，引导使用 Serena MCP
"""
import json
import sys
import re
from pathlib import Path


# 配置
CODE_EXTENSIONS = {'.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cpp', 
                   '.c', '.go', '.rs', '.rb', '.php', '.swift', '.kt', '.sh',
                   '.html', '.css', '.scss', '.sass', '.vue', '.svelte'}
ALLOWED_BASH_COMMANDS = {'pwd', 'echo', 'env', 'whoami', 'date', 'which', 'cd'}
CONFIG_DIRS = {'.claude/', '.git/', 'node_modules/', 'venv/', '__pycache__/'}
ALLOWED_FILE_TYPES = {'.md', '.txt', '.json', '.yaml', '.yml', '.toml', 
                      '.ini', '.cfg', '.conf', '.log'}


def is_code_file(filename):
    """检查是否为代码文件"""
    if not filename:
        return False
    suffix = Path(filename).suffix.lower()
    return suffix in CODE_EXTENSIONS


def extract_file_path(tool_input):
    """
    从 tool_input 中提取文件路径
    尝试多种可能的参数名称
    """
    # 尝试常见的参数名
    path = (tool_input.get('path') or 
            tool_input.get('file_path') or 
            tool_input.get('filepath') or 
            tool_input.get('filename') or 
            tool_input.get('file') or '')
    
    # 如果没找到，遍历所有参数查找看起来像路径的值
    if not path:
        for key, value in tool_input.items():
            if isinstance(value, str) and value:
                # 检查是否包含路径分隔符或文件扩展名
                if '/' in value or '\\' in value or '.' in value:
                    path = value
                    break
    
    return path


def check_bash_command(command):
    """
    检查 Bash 命令是否为文件分析操作
    返回: (should_block, reason)
    """
    # 允许配置目录操作
    if any(cfg_dir in command for cfg_dir in CONFIG_DIRS):
        return False, None
    
    # 检查第一个命令是否在白名单中
    first_cmd = command.strip().split()[0] if command.strip() else ''
    if first_cmd in ALLOWED_BASH_COMMANDS:
        return False, None
    
    # 文件操作命令（使用词边界匹配）
    file_ops = {
        r'\bcat\b': 'cat',
        r'\bless\b': 'less',
        r'\bmore\b': 'more',
        r'\bls\b': 'ls',
        r'\bgrep\b': 'grep',
        r'\bfind\b': 'find',
        r'\bhead\b': 'head',
        r'\btail\b': 'tail',
        r'\bawk\b': 'awk',
        r'\bsed\b': 'sed',
        r'\bcut\b': 'cut',
        r'\bsort\b': 'sort',
        r'\buniq\b': 'uniq'
    }
    
    for pattern, cmd_name in file_ops.items():
        if re.search(pattern, command):
            return True, f"检测到文件分析命令: {cmd_name}"
    
    return False, None


def should_allow_read(path):
    """
    检查是否应该允许读取该文件
    """
    if not path:
        return True
    
    path_lower = path.lower()
    
    # 允许配置目录
    if any(cfg_dir in path for cfg_dir in CONFIG_DIRS):
        return True
    
    # 允许特定文件类型
    suffix = Path(path).suffix.lower()
    if suffix in ALLOWED_FILE_TYPES:
        return True
    
    return False


def main():
    try:
        input_data = json.loads(sys.stdin.read())
        tool_name = input_data.get('tool_name', '')
        tool_input = input_data.get('tool_input', {})
        
        should_block = False
        reason = ""
        
        # 检查 Bash 命令
        if tool_name == 'Bash':
            command = tool_input.get('command', '')
            should_block, reason = check_bash_command(command)
            if should_block:
                reason = f"Bash 命令被拦截\n命令: {command}\n原因: {reason}"
        
        # 检查 Read 工具
        elif tool_name == 'Read':
            path = extract_file_path(tool_input)
            
            # 允许读取非代码文件
            if should_allow_read(path):
                should_block = False
            # 拦截代码文件
            elif is_code_file(path):
                should_block = True
                reason = f"Read 代码文件被拦截\n文件: {path}"
            # 路径为空，默认允许（避免误拦截）
            else:
                should_block = False
        
        # 检查 Grep 工具
        elif tool_name == 'Grep':
            should_block = True
            reason = "Grep 工具已被禁用"
        
        # 构造响应
        if should_block:
            response = {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": f"""
📋 代码分析规范提醒

{reason}

请使用 Serena MCP 工具进行代码分析：
• 执行 /mcp 查看 serena 工具列表
• 常用工具：
  - serena_search: 语义搜索代码
  - serena_list_code_definitions: 查看代码结构
  - serena_read_file: 读取文件内容
  - serena_grep: 搜索代码

优势：
✓ 理解代码语义和结构
✓ 跨文件智能搜索
✓ 符号引用追踪
"""
                }
            }
        else:
            response = {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "allow"
                }
            }
        
        print(json.dumps(response))
        sys.exit(0)
        
    except Exception as e:
        # 出错时默认允许，避免阻塞正常工作流
        error_response = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow"
            }
        }
        print(json.dumps(error_response), file=sys.stderr)
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()

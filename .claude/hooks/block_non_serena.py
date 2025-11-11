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
                   '.c', '.go', '.rs', '.rb', '.php', '.swift', '.kt', '.sh'}
ALLOWED_BASH_COMMANDS = {'pwd', 'echo', 'env', 'whoami', 'date', 'which', 'cd'}
CONFIG_DIRS = {'.claude/', '.git/', 'node_modules/', 'venv/', '__pycache__/'}

def is_code_file(filename):
    """检查是否为代码文件"""
    return Path(filename).suffix in CODE_EXTENSIONS

def check_bash_command(command):
    """
    检查 Bash 命令是否为文件分析操作
    返回: (should_block, reason)
    """
    if any(cfg_dir in command for cfg_dir in CONFIG_DIRS):
        return False, None
    
    first_cmd = command.strip().split()[0] if command.strip() else ''
    if first_cmd in ALLOWED_BASH_COMMANDS:
        return False, None
    
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
        r'\bsed\b': 'sed'
    }
    
    for pattern, cmd_name in file_ops.items():
        if re.search(pattern, command):
            return True, f"检测到文件分析命令: {cmd_name}"
    
    return False, None

def main():
    try:
        input_data = json.loads(sys.stdin.read())
        tool_name = input_data.get('tool_name', '')
        tool_input = input_data.get('tool_input', {})
        
        should_block = False
        reason = ""
        
        if tool_name == 'Bash':
            command = tool_input.get('command', '')
            should_block, reason = check_bash_command(command)
            if should_block:
                reason = f"Bash 命令被拦截\n命令: {command}\n原因: {reason}"
        
        elif tool_name == 'Read':
            path = tool_input.get('path', '')
            if is_code_file(path):
                should_block = True
                reason = f"Read 代码文件被拦截\n文件: {path}"
        
        elif tool_name == 'Grep':
            should_block = True
            reason = "Grep 工具已被禁用"
        
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

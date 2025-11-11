#!/usr/bin/env python3
"""
Sequential Thinking 触发器
检测复杂任务并建议使用 Sequential Thinking
"""
import json
import sys
import os
from datetime import datetime
from pathlib import Path

# 配置
COOLDOWN_SECONDS = 300  # 5分钟冷却时间
COOLDOWN_FILE = '/tmp/claude_st_cooldown'
DEBUG_LOG = '.claude/hooks/debug.log'
FORCE_REMINDER = os.getenv('CLAUDE_FORCE_ST_REMINDER', 'true').lower() == 'true'

def log_debug(message):
    """安全写入调试日志"""
    try:
        log_path = Path(DEBUG_LOG)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(f"{datetime.now().isoformat()} - {message}\n")
    except Exception as e:
        print(f"Log error: {e}", file=sys.stderr)

def check_cooldown():
    """检查冷却时间"""
    if not FORCE_REMINDER:
        return False
    
    try:
        if os.path.exists(COOLDOWN_FILE):
            mtime = os.path.getmtime(COOLDOWN_FILE)
            if (datetime.now().timestamp() - mtime) < COOLDOWN_SECONDS:
                return True
        Path(COOLDOWN_FILE).touch()
    except Exception as e:
        log_debug(f"Cooldown check error: {e}")
    return False

def main():
    try:
        input_data = json.loads(sys.stdin.read())
        user_prompt = input_data.get('prompt', '')
        
        log_debug(f"UserPromptSubmit: {user_prompt[:100]}")
        
        complex_keywords = [
            '排查', '重构', '优化', '分析', '设计', '实现',
            '迁移', '升级', '修复', 'debug', '调试',
            '改进', '整理', '清理', '梳理', '构建',
            '开发', '创建', '编写', '重写',
            'bug', '错误', '问题', '故障',
            '架构', '规划', '方案', '复杂', '困难', '挑战',
            'refactor', 'optimize', 'analyze', 'design', 'implement'
        ]
        
        already_using_st = any(kw in user_prompt.lower() for kw in [
            'sequential', 'thinking', '/mcp', '规划', '分解'
        ])
        
        is_complex = any(kw in user_prompt.lower() for kw in complex_keywords)
        
        if check_cooldown():
            log_debug("Skipped: in cooldown period")
            response = {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "modifiedPrompt": user_prompt
                }
            }
            print(json.dumps(response))
            sys.exit(0)
        
        if is_complex and not already_using_st:
            enhanced_prompt = f"""⚠️ 检测到复杂任务，强烈建议使用 Sequential Thinking

{user_prompt}

---
💡 **最佳实践**：复杂任务应该先规划再执行
- 使用 `/mcp sequential_thinking` 工具分解任务
- 环境变量 CLAUDE_FORCE_ST_REMINDER=false 可禁用此提示
"""
            log_debug("Complex task detected, reminder injected")
            
            response = {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "modifiedPrompt": enhanced_prompt
                }
            }
        else:
            response = {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "modifiedPrompt": user_prompt
                }
            }
        
        print(json.dumps(response))
        sys.exit(0)
        
    except json.JSONDecodeError as e:
        log_debug(f"JSON decode error: {e}")
        error_response = {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "modifiedPrompt": input_data.get('prompt', '')
            }
        }
        print(json.dumps(error_response), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        log_debug(f"Unexpected error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()

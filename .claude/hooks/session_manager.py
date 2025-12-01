#!/usr/bin/env python3
"""
会话管理器 - 统一管理会话标记和日志
"""
import sys
from pathlib import Path
from datetime import datetime

PLANNING_DONE = '/tmp/claude_planning_done'
PLANNING_IN_PROGRESS = '/tmp/claude_planning_in_progress'
DEBUG_LOG = '.claude/hooks/debug.log'

def log(message):
    """写入日志"""
    try:
        log_path = Path(DEBUG_LOG)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(f"{datetime.now().isoformat()} - {message}\n")
    except Exception:
        pass

def session_start():
    """会话开始"""
    Path(PLANNING_DONE).unlink(missing_ok=True)
    Path(PLANNING_IN_PROGRESS).unlink(missing_ok=True)
    log("Session started")
    print("📋 会话开始 - 复杂任务需要先规划")

def session_end():
    """会话结束"""
    Path(PLANNING_DONE).unlink(missing_ok=True)
    log("Session ended")

def planning_complete():
    """规划完成"""
    Path(PLANNING_DONE).touch()
    Path(PLANNING_IN_PROGRESS).unlink(missing_ok=True)
    log("Planning completed")
    print("✅ 规划已完成")

if __name__ == '__main__':
    action = sys.argv[1] if len(sys.argv) > 1 else ''
    
    if action == 'start':
        session_start()
    elif action == 'end':
        session_end()
    elif action == 'complete':
        planning_complete()

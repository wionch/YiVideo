# services/common/state_manager.py
import json
import os
from datetime import datetime
from datetime import timezone

import redis

# 确保可以从公共模块导入
from services.common.context import WorkflowContext

# --- Redis Connection ---
REDIS_HOST = os.environ.get('REDIS_HOST', 'redis')
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))
DB_STATE_STORE = int(os.environ.get('DB_STATE_STORE', 3))
WORKFLOW_TTL_DAYS = int(os.environ.get('WORKFLOW_TTL_DAYS', 7))

try:
    redis_conn = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=DB_STATE_STORE)
    redis_conn.ping()
    print(f"成功连接到 Redis (for state store): {REDIS_HOST}:{REDIS_PORT}")
except redis.exceptions.ConnectionError as e:
    print(f"错误：无法连接到 Redis (for state store)。请检查 Redis 服务。错误: {e}")
    redis_conn = None

def get_workflow_key(workflow_id: str) -> str:
    return f"workflow_state:{workflow_id}"

def create_workflow_state(context: WorkflowContext):
    if not redis_conn:
        raise ConnectionError("Redis not connected.")
    key = get_workflow_key(context.workflow_id)
    value = json.dumps(context.dict(), indent=4)
    pipe = redis_conn.pipeline()
    pipe.set(key, value)
    pipe.expire(key, WORKFLOW_TTL_DAYS * 24 * 60 * 60)
    pipe.execute()
    print(f"为工作流 {context.workflow_id} 创建了状态记录。")

def update_workflow_state(context: WorkflowContext):
    """原子性地更新（覆盖）Redis中的工作流状态记录。"""
    if not redis_conn:
        # 在worker中，如果redis连不上，可以选择仅打印警告而不是抛出异常，以避免任务重试
        print("警告: Redis 未连接，无法更新工作流状态。")
        return
    try:
        key = get_workflow_key(context.workflow_id)
        value = json.dumps(context.dict(), indent=4)
        # 直接使用SET覆盖旧值，TTL会保持不变
        redis_conn.set(key, value)
        print(f"更新了工作流 {context.workflow_id} 的状态记录。")
    except Exception as e:
        print(f"警告: 更新工作流 {context.workflow_id} 状态时发生错误: {e}")

def get_workflow_state(workflow_id: str) -> dict:
    if not redis_conn:
        raise ConnectionError("Redis not connected.")
    key = get_workflow_key(workflow_id)
    value = redis_conn.get(key)
    if value:
        return json.loads(value)
    return None

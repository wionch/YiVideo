# services/api_gateway/app/state_manager.py
# -*- coding: utf-8 -*-

"""
管理工作流状态的模块。

提供与Redis交互的函数，用于创建、更新、查询和删除工作流的持久化状态。
"""

import os
import json
import logging
from redis import Redis
from typing import Dict, Any

# 导入在Stage 1中创建的标准化上下文
from services.common.context import WorkflowContext

# --- 日志和Redis连接配置 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

REDIS_HOST = os.environ.get('REDIS_HOST', 'redis')
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))
# 使用config.yml中为状态存储定义的DB
REDIS_STATE_DB = int(os.environ.get('REDIS_STATE_DB', 3)) 
# TODO: 从config.yml动态加载TTL
WORKFLOW_TTL_DAYS = int(os.environ.get('WORKFLOW_TTL_DAYS', 7))
WORKFLOW_TTL_SECONDS = WORKFLOW_TTL_DAYS * 24 * 60 * 60

try:
    redis_client = Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_STATE_DB)
    redis_client.ping()
    logging.info(f"状态管理器成功连接到Redis at {REDIS_HOST}:{REDIS_PORT}/{REDIS_STATE_DB}")
except Exception as e:
    logging.error(f"状态管理器无法连接到Redis. 错误: {e}")
    redis_client = None

# --- 核心功能 ---

def _get_key(workflow_id: str) -> str:
    """生成用于Redis的标准化键。"""
    return f"workflow_state:{workflow_id}"

def create_workflow_state(context: WorkflowContext) -> None:
    """
    在Redis中创建一个新的工作流状态记录。

    Args:
        context (WorkflowContext): 要持久化的工作流上下文对象。
    """
    if not redis_client:
        logging.error("Redis未连接，无法创建工作流状态。")
        return

    key = _get_key(context.workflow_id)
    # 将Pydantic模型序列化为JSON字符串
    state_json = context.model_dump_json()
    
    # 使用setex原子地设置键、值和过期时间
    redis_client.setex(key, WORKFLOW_TTL_SECONDS, state_json)
    logging.info(f"已为 workflow_id='{context.workflow_id}' 创建初始状态，TTL为 {WORKFLOW_TTL_DAYS} 天。")

def update_workflow_state(context: WorkflowContext) -> None:
    """
    更新Redis中已存在的工作流状态记录。

    这通常由Celery任务在执行前后调用。
    它会保留现有的TTL。

    Args:
        context (WorkflowContext): 包含最新状态的上下文对象。
    """
    if not redis_client:
        logging.error("Redis未连接，无法更新工作流状态。")
        return

    key = _get_key(context.workflow_id)
    state_json = context.model_dump_json()
    
    # 使用set并保留TTL
    redis_client.set(key, state_json, keepttl=True)
    logging.info(f"已更新 workflow_id='{context.workflow_id}' 的状态。")

def get_workflow_state(workflow_id: str) -> Dict[str, Any]:
    """
    从Redis中检索一个工作流的状态。

    Args:
        workflow_id (str): 要查询的工作流ID。

    Returns:
        Dict[str, Any]: 代表工作流状态的字典。如果找不到，则返回一个错误信息。
    """
    if not redis_client:
        logging.error("Redis未连接，无法获取工作流状态。")
        return {"error": "State manager could not connect to Redis."}

    key = _get_key(workflow_id)
    state_json = redis_client.get(key)

    if not state_json:
        logging.warning(f"尝试获取一个不存在的工作流状态: workflow_id='{workflow_id}'")
        return {"error": f"Workflow with id '{workflow_id}' not found."}

    return json.loads(state_json)
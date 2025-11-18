# services/common/state_manager.py
# -*- coding: utf-8 -*-

"""
管理工作流状态的模块。

提供与Redis交互的函数，用于创建、更新、查询和删除工作流的持久化状态。
"""

import os

from services.common.logger import get_logger

logger = get_logger('state_manager')
import json
import logging
from typing import Any
from typing import Optional
from typing import Dict

from redis import Redis

# 导入callback管理器
try:
    from services.api_gateway.app.callback_manager import get_callback_manager
except ImportError:
    # 如果无法导入回调管理器，说明不在API Gateway环境中
    get_callback_manager = None
# 导入在Stage 1中创建的标准化上下文
from services.common.context import WorkflowContext

# --- 日志和Redis连接配置 ---
# 日志已统一管理，使用 services.common.logger

# 使用统一的配置加载器，确保与环境变量配置一致
from services.common.config_loader import get_redis_config

# 使用config.yml中为状态存储定义的DB
REDIS_STATE_DB = int(os.environ.get('REDIS_STATE_DB', 3))
# TODO: 从config.yml动态加载TTL
WORKFLOW_TTL_DAYS = int(os.environ.get('WORKFLOW_TTL_DAYS', 7))
WORKFLOW_TTL_SECONDS = WORKFLOW_TTL_DAYS * 24 * 60 * 60

try:
    redis_config = get_redis_config()
    REDIS_HOST = redis_config['host']
    REDIS_PORT = redis_config['port']
    
    redis_client = Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_STATE_DB)
    redis_client.ping()
    logger.info(f"状态管理器成功连接到Redis at {REDIS_HOST}:{REDIS_PORT}/{REDIS_STATE_DB}")
except ValueError as e:
    logger.error(f"Redis配置错误: {e}")
    redis_client = None
except Exception as e:
    logger.error(f"状态管理器无法连接到Redis. 错误: {e}")
    redis_client = None

# --- 核心功能 ---
def _upload_files_to_minio(context: WorkflowContext) -> None:
    """
    自动检测并上传工作流中的文件到MinIO
    
    Args:
        context: 工作流上下文对象
    """
    try:
        from services.common.file_service import get_file_service
        
        file_service = get_file_service()
        
        # 遍历所有阶段的输出
        for stage_name, stage in context.stages.items():
            if stage.status != 'SUCCESS' or not stage.output:
                continue
            
            # 检查输出中的文件路径字段 - 优先处理转录结果文件
            file_keys = ['segments_file', 'transcribe_data_file', 'audio_path', 'video_path', 'subtitle_path', 'output_path']
            
            for key in file_keys:
                if key not in stage.output:
                    continue
                
                file_path = stage.output[key]
                
                # 跳过已经是URL的路径
                if isinstance(file_path, str) and (file_path.startswith('http://') or file_path.startswith('https://')):
                    logger.info(f"跳过已是URL的路径: {key} = {file_path}")
                    continue
                
                # 检查文件是否存在
                if isinstance(file_path, str) and os.path.exists(file_path):
                    try:
                        file_name = os.path.basename(file_path)
                        minio_path = f"{context.workflow_id}/{file_name}"
                        
                        logger.info(f"准备上传文件: {file_path} -> {minio_path}")
                        
                        # 上传到MinIO
                        minio_url = file_service.upload_to_minio(file_path, minio_path)
                        
                        # 更新输出中的路径为MinIO URL
                        stage.output[key] = minio_url
                        logger.info(f"文件已上传并更新路径: {key} = {minio_url}")
                        
                    except Exception as e:
                        logger.warning(f"上传文件失败: {file_path}, 错误: {e}", exc_info=True)
                        
    except Exception as e:
        logger.error(f"文件上传过程出错: {e}", exc_info=True)

def _check_and_trigger_callback(context: WorkflowContext) -> None:
    """
    检查是否需要触发callback
    
    Args:
        context: 工作流上下文对象
    """
    # 检查是否在API Gateway环境中
    if get_callback_manager is None:
        return
        
    try:
        # 获取callback管理器实例
        callback_manager = get_callback_manager()
        
        # 检查是否是单任务并且有callback URL
        input_params = context.input_params
        if not input_params or not input_params.get('callback_url'):
            return
            
        # 检查任务是否已完成
        stages = context.stages
        if not stages:
            return
            
        # 找到第一个阶段的状态
        stage_status = None
        stage_name = None
        for name, stage in stages.items():
            stage_status = stage.status
            stage_name = name
            break
            
        # 只有在任务最终完成（成功或失败）时才触发callback
        if stage_status in ['SUCCESS', 'FAILED']:
            task_id = context.workflow_id
            callback_url = input_params.get('callback_url')
            
            # 构建结果数据 - 修复JSON序列化问题
            # 将StageExecution对象转换为字典
            stages_dict = {}
            for name, stage in stages.items():
                stages_dict[name] = stage.model_dump()
            
            result = {
                'workflow_id': task_id,
                'create_at': context.create_at,
                'input_params': input_params,
                'shared_storage_path': context.shared_storage_path,
                'stages': stages_dict,
                'error': context.error
            }
            
            # 检查是否有minio_files信息
            minio_files = stage.output.get('minio_files') if stage.output else None
            
            # 发送callback
            success = callback_manager.send_result(
                task_id, result, minio_files, callback_url
            )
            
            callback_status = "sent" if success else "failed"
            logger.info(f"Callback发送完成: {task_id}, 状态: {callback_status}")
            
    except Exception as e:
        logger.error(f"Callback触发失败: {e}", exc_info=True)

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
        logger.error("Redis未连接，无法创建工作流状态。")
        return

    key = _get_key(context.workflow_id)
    # 将Pydantic模型序列化为JSON字符串
    state_json = context.model_dump_json()
    
    # 使用setex原子地设置键、值和过期时间
    redis_client.setex(key, WORKFLOW_TTL_SECONDS, state_json)
    logger.info(f"已为 workflow_id='{context.workflow_id}' 创建初始状态，TTL为 {WORKFLOW_TTL_DAYS} 天。")

def update_workflow_state(context: WorkflowContext) -> None:
    """
    更新Redis中已存在的工作流状态记录。

    这通常由Celery任务在执行前后调用。
    它会保留现有的TTL。

    Args:
        context (WorkflowContext): 包含最新状态的上下文对象。
    """
    if not redis_client:
        logger.error("Redis未连接，无法更新工作流状态。")
        return

    # 自动上传文件到MinIO
    _upload_files_to_minio(context)

    key = _get_key(context.workflow_id)
    state_json = context.model_dump_json()
    
    # 使用set并保留TTL
    redis_client.set(key, state_json, keepttl=True)
    
    # 检查是否需要触发callback
    _check_and_trigger_callback(context)
    logger.info(f"已更新 workflow_id='{context.workflow_id}' 的状态。")

def get_workflow_state(workflow_id: str) -> Dict[str, Any]:
    """
    从Redis中检索一个工作流的状态。

    Args:
        workflow_id (str): 要查询的工作流ID。

    Returns:
        Dict[str, Any]: 代表工作流状态的字典。如果找不到，则返回一个错误信息。
    """
    if not redis_client:
        logger.error("Redis未连接，无法获取工作流状态。")
        return {"error": "State manager could not connect to Redis."}

    key = _get_key(workflow_id)
    state_json = redis_client.get(key)

    if not state_json:
        logger.warning(f"尝试获取一个不存在的工作流状态: workflow_id='{workflow_id}'")
        return {"error": f"Workflow with id '{workflow_id}' not found."}

    return json.loads(state_json)

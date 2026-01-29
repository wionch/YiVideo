# services/common/state_manager.py
# -*- coding: utf-8 -*-

"""
管理工作流状态的模块。

提供与Redis交互的函数，用于创建、更新、查询和删除工作流的持久化状态。
"""

import os
from datetime import datetime

from services.common.logger import get_logger

logger = get_logger('state_manager')
import json
import logging
from typing import Any
from typing import Optional
from typing import Dict
from typing import List

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
from services.common.config_loader import get_config
from services.common.config_loader import get_redis_config

# 使用config.yml中为状态存储定义的DB
REDIS_STATE_DB = int(os.environ.get('REDIS_STATE_DB', 3))
# 任务节点状态统一保留 1 天
NODE_TTL_DAYS = 1
NODE_TTL_SECONDS = NODE_TTL_DAYS * 24 * 60 * 60

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

def _is_auto_upload_enabled() -> bool:
    """读取全局开关，控制是否自动上传到 MinIO。"""
    try:
        config = get_config() or {}
        raw_value = config.get("core", {}).get("auto_upload_to_minio", True)
        if isinstance(raw_value, bool):
            return raw_value
        if isinstance(raw_value, str):
            return raw_value.lower() in ("true", "1", "yes", "on")
    except Exception as e:
        logger.warning(f"读取 auto_upload_to_minio 配置失败，使用默认 True: {e}", exc_info=True)
    return True


# --- 核心功能 ---
def _upload_files_to_minio(context: WorkflowContext) -> None:
    """
    自动检测并上传工作流中的文件到MinIO

    去重逻辑:
    - 检查 {key}_minio_url 字段是否已存在且值有效（非空字符串）
    - 如果存在有效URL,跳过上传并记录日志
    - 如果不存在或为空,执行上传并生成 MinIO URL

    Args:
        context: 工作流上下文对象
    """
    try:
        from services.common.file_service import get_file_service
        from services.common.minio_url_convention import MinioUrlNamingConvention
        from services.common.path_builder import convert_local_to_minio_path

        file_service = get_file_service()
        convention = MinioUrlNamingConvention()

        # 遍历所有阶段的输出
        for stage_name, stage in context.stages.items():
            if stage.status != 'SUCCESS' or not stage.output:
                continue

            # 自动检测所有路径字段（而非硬编码列表）
            file_keys = []
            directory_keys = []

            for key in stage.output.keys():
                # 跳过已经是 MinIO URL 的字段
                if '_minio_url' in key:
                    continue

                # 检查是否为路径字段
                if convention.is_path_field(key):
                    value = stage.output[key]
                    # 判断是文件还是目录
                    if isinstance(value, str) and os.path.exists(value):
                        if os.path.isdir(value):
                            directory_keys.append(key)
                        else:
                            file_keys.append(key)
                    elif isinstance(value, list):
                        # 数组字段（如 all_audio_files）
                        file_keys.append(key)
            
            # 处理普通文件字段
            for key in file_keys:
                if key not in stage.output:
                    continue

                file_value = stage.output[key]
                minio_field_name = convention.get_minio_url_field_name(key)

                # 处理数组字段（如 all_audio_files）
                if isinstance(file_value, list):
                    # 检查是否已有有效的 MinIO URL 数组（非空且包含有效URL）
                    existing_urls = stage.output.get(minio_field_name)
                    if existing_urls and isinstance(existing_urls, list) and len(existing_urls) > 0:
                        # 验证至少有一个有效URL
                        has_valid_url = any(
                            isinstance(url, str) and url.strip() and 
                            (url.startswith('http://') or url.startswith('https://'))
                            for url in existing_urls
                        )
                        if has_valid_url:
                            logger.info(f"跳过已上传的文件数组: {key} (已有 {minio_field_name})")
                            continue

                    minio_urls = []
                    for file_path in file_value:
                        # 跳过已经是URL的路径
                        if isinstance(file_path, str) and (file_path.startswith('http://') or file_path.startswith('https://')):
                            logger.info(f"跳过已是URL的路径: {file_path}")
                            continue

                        # 检查文件是否存在
                        if isinstance(file_path, str) and os.path.exists(file_path):
                            try:
                                # 使用 path_builder 生成 MinIO 路径
                                minio_path = convert_local_to_minio_path(file_path)

                                logger.info(f"准备上传文件: {file_path} -> {minio_path}")

                                # 上传到MinIO
                                minio_url = file_service.upload_to_minio(file_path, minio_path)
                                minio_urls.append(minio_url)

                                logger.info(f"文件已上传: {minio_url}")

                            except Exception as e:
                                logger.warning(f"上传文件失败: {file_path}, 错误: {e}", exc_info=True)

                    # 保存所有 MinIO URLs
                    if minio_urls:
                        stage.output[minio_field_name] = minio_urls
                        logger.info(f"数组字段已上传: {minio_field_name} = {len(minio_urls)} 个文件")

                # 处理单个文件字段
                elif isinstance(file_value, str):
                    # 检查是否已有有效的 MinIO URL（非空字符串且是有效URL）
                    existing_url = stage.output.get(minio_field_name)
                    if existing_url and isinstance(existing_url, str) and existing_url.strip():
                        # 验证是有效的URL而非空字符串
                        if existing_url.startswith('http://') or existing_url.startswith('https://'):
                            logger.info(f"跳过已上传的文件: {key} (已有 {minio_field_name} = {existing_url})")
                            continue
                        else:
                            logger.warning(f"检测到无效的MinIO URL: {minio_field_name} = '{existing_url}', 将重新上传")

                    # 跳过已经是URL的路径
                    if file_value.startswith('http://') or file_value.startswith('https://'):
                        logger.info(f"跳过已是URL的路径: {key} = {file_value}")
                        continue

                    # 检查文件是否存在
                    if os.path.exists(file_value):
                        try:
                            # 使用 path_builder 生成 MinIO 路径
                            minio_path = convert_local_to_minio_path(file_value)

                            logger.info(f"准备上传文件: {file_value} -> {minio_path}")

                            # 上传到MinIO
                            minio_url = file_service.upload_to_minio(file_value, minio_path)

                            # 追加 MinIO URL，保留原始本地路径
                            stage.output[minio_field_name] = minio_url
                            logger.info(f"文件已上传: {minio_field_name} = {minio_url}")

                        except Exception as e:
                            logger.warning(f"上传文件失败: {file_value}, 错误: {e}", exc_info=True)
            
            # 处理目录字段（压缩上传）
            for key in directory_keys:
                if key not in stage.output:
                    continue

                dir_path = stage.output[key]

                # 跳过已经是URL的路径
                if isinstance(dir_path, str) and (dir_path.startswith('http://') or dir_path.startswith('https://')):
                    logger.info(f"跳过已是URL的路径: {key} = {dir_path}")
                    continue

                # 检查目录是否存在
                if isinstance(dir_path, str) and os.path.exists(dir_path) and os.path.isdir(dir_path):
                    try:
                        # 使用压缩上传模块
                        from services.common.minio_directory_upload import upload_directory_compressed

                        logger.info(f"准备压缩并上传目录: {dir_path} (workflow_id: {context.workflow_id})")

                        # 使用 path_builder 生成 MinIO 路径
                        minio_base_path = convert_local_to_minio_path(dir_path)

                        # 压缩并上传目录到MinIO
                        upload_result = upload_directory_compressed(
                            local_dir=dir_path,
                            minio_base_path=minio_base_path,
                            file_pattern="*",  # 上传所有文件
                            compression_format="zip",  # 使用 ZIP 格式
                            compression_level="default",  # 默认压缩级别
                            delete_local=False,  # 不删除本地目录
                            workflow_id=context.workflow_id  # 传递 workflow_id 用于临时文件
                        )

                        if upload_result["success"]:
                            # 追加压缩包 URL，保留原始本地目录
                            minio_field_name = convention.get_minio_url_field_name(key)
                            stage.output[minio_field_name] = upload_result["archive_url"]

                            # 添加压缩信息
                            compression_info = upload_result.get("compression_info", {})
                            stage.output[f"{key}_compression_info"] = {
                                "files_count": compression_info.get("files_count", 0),
                                "original_size": compression_info.get("original_size", 0),
                                "compressed_size": compression_info.get("compressed_size", 0),
                                "compression_ratio": compression_info.get("compression_ratio", 0),
                                "format": compression_info.get("format", "zip")
                            }

                            logger.info(
                                f"目录压缩上传成功: {minio_field_name} = {upload_result['archive_url']}, "
                                f"文件数: {compression_info.get('files_count', 0)}, "
                                f"压缩率: {compression_info.get('compression_ratio', 0):.1%}"
                            )
                        else:
                            logger.warning(f"目录压缩上传失败: {dir_path}, 错误: {upload_result.get('error', '未知错误')}")
                            # 即使上传失败也保留原始目录路径
                            stage.output[f"{key}_upload_error"] = upload_result.get("error")

                    except Exception as e:
                        logger.warning(f"压缩上传目录失败: {dir_path}, 错误: {e}", exc_info=True)
                        stage.output[f"{key}_upload_error"] = str(e)
                        
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
            
        target_name = input_params.get('task_name')
        target_stage = stages.get(target_name) if target_name else None
        if not target_stage:
            # 回落到第一个阶段
            target_name, target_stage = next(iter(stages.items()))

        # 统一读取阶段字段
        stage_status = getattr(target_stage, "status", None) if target_stage else None
        stage_output = getattr(target_stage, "output", None) if target_stage else None
        stage_error = getattr(target_stage, "error", None) if target_stage else None
        stage_duration = getattr(target_stage, "duration", None) if target_stage else None

        if isinstance(target_stage, dict):
            stage_status = target_stage.get("status")
            stage_output = target_stage.get("output")
            stage_error = target_stage.get("error")
            stage_duration = target_stage.get("duration")

        if not stage_status or stage_status.upper() not in ['SUCCESS', 'FAILED']:
            return

        task_id = context.workflow_id
        callback_url = input_params.get('callback_url')

        # 构建结果数据 - 修复JSON序列化问题
        stages_dict = {}
        for name, stage in stages.items():
            if hasattr(stage, "model_dump"):
                stages_dict[name] = stage.model_dump()
            else:
                stages_dict[name] = stage

        filtered_stages = stages_dict
        if target_name in stages_dict:
            filtered_stages = {target_name: stages_dict[target_name]}
        else:
            filtered_stages = {}

        result = {
            'workflow_id': task_id,
            'create_at': context.create_at,
            'input_params': input_params,
            'shared_storage_path': context.shared_storage_path,
            'stages': filtered_stages,
            'error': context.error,
            'reuse_info': getattr(context, "reuse_info", None) or context.__dict__.get("reuse_info")
        }

        # 补充阶段状态字段，便于回调端判断
        if target_name in result['stages']:
            result['stages'][target_name]["duration"] = stage_duration
            result['stages'][target_name]["error"] = stage_error

        # 检查是否有minio_files信息
        minio_files = None
        if isinstance(stage_output, dict):
            minio_files = stage_output.get('minio_files')

        # 发送callback
        success = callback_manager.send_result(
            task_id, result, minio_files, callback_url
        )

        callback_status = "sent" if success else "failed"
        logger.info(f"Callback发送完成: {task_id}, 状态: {callback_status}")
            
    except Exception as e:
        logger.error(f"Callback触发失败: {e}", exc_info=True)

def _get_node_key(task_id: str, task_name: str) -> str:
    """生成用于Redis的节点键。"""
    return f"{task_id}:node:{task_name}"


def _build_node_view(context: WorkflowContext) -> Optional[WorkflowContext]:
    """仅保留当前 task_name 的阶段数据，生成单节点视图。"""
    data = context.model_dump()
    input_params = data.get("input_params") or {}
    task_name = input_params.get("task_name")
    stages = data.get("stages") or {}

    if not task_name:
        if len(stages) == 1:
            task_name = next(iter(stages.keys()))
            input_params["task_name"] = task_name
            data["input_params"] = input_params
        else:
            logger.error("无法识别 task_name，节点写入已跳过")
            return None

    node_stage = stages.get(task_name)
    data["stages"] = {task_name: node_stage} if node_stage else {}
    return WorkflowContext(**data)


def _parse_time(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _merge_states(states: List[Dict[str, Any]], workflow_id: str) -> Dict[str, Any]:
    """合并多个节点状态为一个聚合视图。"""
    if not states:
        return {}

    merged: Dict[str, Any] = {"stages": {}}
    latest_state: Optional[Dict[str, Any]] = None
    latest_time: Optional[datetime] = None

    for item in states:
        for name, stage in (item.get("stages") or {}).items():
            merged["stages"][name] = stage

        candidate_time = _parse_time(item.get("updated_at")) or _parse_time(item.get("create_at"))
        if latest_state is None:
            latest_state = item
            latest_time = candidate_time
            continue
        if candidate_time and (latest_time is None or candidate_time > latest_time):
            latest_state = item
            latest_time = candidate_time

    if latest_state:
        for key, value in latest_state.items():
            if key == "stages":
                continue
            merged[key] = value

    merged.setdefault("workflow_id", workflow_id)
    return merged

def create_workflow_state(context: WorkflowContext) -> None:
    """
    在Redis中创建一个新的工作流状态记录。

    Args:
        context (WorkflowContext): 要持久化的工作流上下文对象。
    """
    if not redis_client:
        logger.error("Redis未连接，无法创建工作流状态。")
        return

    node_context = _build_node_view(context)
    if not node_context:
        return
    task_name = (node_context.input_params or {}).get("task_name")
    if not task_name:
        logger.error("task_name 缺失，无法创建节点状态。")
        return

    key = _get_node_key(node_context.workflow_id, task_name)
    state_json = node_context.model_dump_json()

    # 使用setex原子地设置键、值和过期时间
    redis_client.setex(key, NODE_TTL_SECONDS, state_json)
    logger.info(f"已为 workflow_id='{node_context.workflow_id}' 创建节点状态，TTL为 {NODE_TTL_DAYS} 天。")

def update_workflow_state(context: WorkflowContext, skip_side_effects: bool = False) -> None:
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

    # 自动上传文件到MinIO（尊重配置开关），可按需跳过副作用
    if not skip_side_effects:
        if _is_auto_upload_enabled():
            _upload_files_to_minio(context)
        else:
            logger.info("auto_upload_to_minio 已关闭，跳过上传。")

    node_context = _build_node_view(context)
    if not node_context:
        return
    task_name = (node_context.input_params or {}).get("task_name")
    if not task_name:
        logger.error("task_name 缺失，无法更新节点状态。")
        return

    key = _get_node_key(node_context.workflow_id, task_name)
    state_json = node_context.model_dump_json()

    # 使用setex刷新TTL
    redis_client.setex(key, NODE_TTL_SECONDS, state_json)
    
    # 检查是否需要触发callback
    if not skip_side_effects:
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

    states: List[Dict[str, Any]] = []
    try:
        for key in redis_client.scan_iter(match=f"{workflow_id}:node:*"):
            state_json = redis_client.get(key)
            if not state_json:
                continue
            try:
                states.append(json.loads(state_json))
            except Exception as e:
                logger.error(f"解析Redis节点状态失败: {key}, 错误: {e}")
    except Exception as e:
        logger.error(f"扫描Redis节点状态失败: workflow_id='{workflow_id}', 错误: {e}")
        return {"error": f"Workflow with id '{workflow_id}' not found."}

    if not states:
        logger.warning(f"尝试获取一个不存在的工作流状态: workflow_id='{workflow_id}'")
        return {"error": f"Workflow with id '{workflow_id}' not found."}

    return _merge_states(states, workflow_id)

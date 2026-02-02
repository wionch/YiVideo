# services/api_gateway/app/single_task_executor.py
# 注意：callback机制已迁移到state_manager统一处理
# -*- coding: utf-8 -*-

"""
单任务执行器。

负责执行单个工作流节点任务的逻辑。
"""

import os
import json
import uuid
import shutil
import tempfile
import requests
from copy import deepcopy
from datetime import datetime
from threading import Thread
from typing import Dict, Any, List, Optional
from celery import Celery, signature
from celery.result import AsyncResult

from services.common.logger import get_logger
from services.common.celery_config import BROKER_URL, BACKEND_URL
from services.common.context import WorkflowContext
from services.common.state_manager import (
    create_workflow_state,
    get_workflow_state,
    update_workflow_state,
)
from services.common import state_manager

from .minio_service import get_minio_service
from .callback_manager import get_callback_manager
from .single_task_models import (
    SingleTaskRequest,
    SingleTaskResponse,
    TaskStatusResponse,
    ErrorResponse,
    TaskDeletionResult,
    ResourceDeletionItem,
    DeletionResource,
    DeletionResourceStatus,
    TaskDeletionStatus,
)

logger = get_logger('single_task_executor')


class SingleTaskExecutor:
    """单任务执行器类"""
    
    def __init__(self):
        """初始化单任务执行器"""
        # 创建Celery应用实例
        self.celery_app = Celery('single_task_executor', broker=BROKER_URL, backend=BACKEND_URL)
        
        # 获取MinIO服务和Callback管理器
        self.minio_service = get_minio_service()
        self.callback_manager = get_callback_manager()
        
        logger.info("单任务执行器初始化完成")
    
    def _filter_context_for_response(self, context: Dict[str, Any], task_name: str) -> Dict[str, Any]:
        """
        过滤上下文，仅返回单节点结果。
        用于 API 响应和回调载荷，确保单任务视图的一致性。
        """
        if not context or not task_name:
            return {}

        stages = context.get("stages") or {}
        stage = stages.get(task_name)
        if not stage:
            return {}

        return state_manager.build_single_node_result(task_name, stage)

    def execute_task(self, task_name: str, task_id: str, input_data: Dict[str, Any],
                    callback_url: Optional[str] = None) -> Dict[str, Any]:
        """
        执行单个任务
        
        Args:
            task_name: 工作流节点名称
            task_id: 任务唯一标识符
            input_data: 任务输入数据
            callback_url: 回调URL（可选）
            
        Returns:
            str: Celery任务ID
        """
        logger.info(f"开始执行单任务: {task_name}, ID: {task_id}")
        
        # 验证task_name格式
        if not self._validate_task_name(task_name):
            raise ValueError(f"无效的任务名称格式: {task_name}")
        
        # 处理输入数据中的HTTP文件路径
        # 创建任务上下文
        # 注意：移除了文件预处理步骤，文件路径将直接传递给 worker
        context = self._create_task_context(task_id, task_name, input_data, callback_url)

        # 复用判定：已有成功阶段且输出非空，直接回调并返回 completed
        reuse_result = self._check_reuse(task_id, task_name, callback_url)
        if reuse_result["reuse_hit"]:
            if reuse_result["state"] == "completed":
                logger.info(f"命中复用，跳过调度: {task_name}, ID: {task_id}")
                return {
                    "mode": "reuse_completed",
                    "reuse_info": reuse_result["reuse_info"],
                    "context": reuse_result["context"]
                }
            if reuse_result["state"] == "pending":
                logger.info(f"复用命中但阶段未完成: {task_name}, ID: {task_id}")
                return {
                    "mode": "reuse_pending",
                    "reuse_info": reuse_result["reuse_info"],
                    "context": reuse_result["context"]
                }

        # 创建任务状态记录（累积写入现有阶段）
        self._create_task_record(task_id, context, "pending")

        # 将当前 Redis 状态作为调度上下文，确保已有阶段不丢失
        context_from_state = self._get_task_state(task_id)
        if context_from_state and not context_from_state.get("error"):
            context = context_from_state
            context["status"] = "pending"
        
        try:
            # 构建Celery任务签名
            task_signature = self._build_task_signature(task_name, context)
            
            # 异步执行任务
            celery_result = task_signature.apply_async()
            celery_task_id = celery_result.id
            
            # 更新任务状态为running
            self._update_task_status(task_id, "running", {"celery_task_id": celery_task_id})
            
            logger.info(f"单任务提交成功: {task_name}, ID: {task_id}, Celery Task ID: {celery_task_id}")
            return {
                "mode": "scheduled",
                "celery_task_id": celery_task_id
            }
            
        except Exception as e:
            # 更新任务状态为failed
            self._update_task_status(task_id, "failed", {"error": str(e)})
            logger.error(f"单任务执行失败: {task_name}, ID: {task_id}, 错误: {e}")
            raise
    
    def handle_task_completion(self, task_id: str, celery_task_id: str):
        """
        处理任务完成后的逻辑
        
        Args:
            task_id: 任务ID
            celery_task_id: Celery任务ID
        """
        logger.info(f"处理任务完成: {task_id}")
        
        try:
            # 获取Celery任务结果
            celery_result = AsyncResult(celery_task_id, app=self.celery_app)
            
            if celery_result.ready():
                # 任务已完成
                if celery_result.successful():
                    # 任务成功
                    result = celery_result.result
                    logger.info(f"任务执行成功: {task_id}, 结果: {result}")
                    
                    # 上传生成的文件到MinIO
                    minio_files = self._upload_result_files(task_id, result)
                    
                    # 更新任务状态
                    self._update_task_status(task_id, "completed", {
                        "result": result,
                        "minio_files": minio_files
                    })
                    
                    # 发送callback（如果需要）
                    self._send_callback_if_needed(task_id, result, minio_files)
                    
                else:
                    # 任务失败
                    error = str(celery_result.info) if celery_result.info else "未知错误"
                    logger.error(f"任务执行失败: {task_id}, 错误: {error}")
                    
                    self._update_task_status(task_id, "failed", {
                        "error": error
                    })
                    
                    # 发送callback（如果需要）
                    self._send_callback_if_needed(task_id, {"status": "FAILED", "error": error}, None)
            else:
                logger.warning(f"任务尚未完成: {task_id}")
                
        except Exception as e:
            logger.error(f"处理任务完成时出错: {task_id}, 错误: {e}")
    
    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """
        获取任务状态
        
        Args:
            task_id: 任务ID
            
        Returns:
            Dict: 任务状态信息
        """
        try:
            # 从Redis获取任务状态
            state = self._get_task_state(task_id)
            
            if not state:
                return {
                    "task_id": task_id,
                    "status": "not_found",
                    "message": "任务不存在"
                }

            task_name = (state.get("input_params") or {}).get("task_name")
            stages = state.get("stages") or {}
            stage = stages.get(task_name) if task_name else None
            node_result = (
                state_manager.build_single_node_result(task_name, stage)
                if task_name and stage is not None
                else None
            )

            return {
                "task_id": task_id,
                "status": state.get("status"),
                "message": state.get("message") or "任务状态获取成功",
                "result": node_result,
                "minio_files": state.get("minio_files"),
                "create_at": state.get("create_at"),
                "updated_at": state.get("updated_at"),
                "callback_status": state.get("callback_status"),
            }
            
        except Exception as e:
            logger.error(f"获取任务状态失败: {task_id}, 错误: {e}")
            return {
                "task_id": task_id,
                "status": "error",
                "message": f"获取任务状态失败: {str(e)}"
            }
    
    def _validate_task_name(self, task_name: str) -> bool:
        """验证任务名称格式"""
        if not task_name:
            return False
        
        # 检查是否包含服务名前缀，如 "ffmpeg.extract_audio"
        parts = task_name.split('.')
        if len(parts) != 2:
            return False
        
        service_name, method_name = parts
        
        # 验证服务名和方法名
        valid_services = {
            'ffmpeg', 'faster_whisper', 'qwen3_asr', 'funasr', 'audio_separator',
            'pyannote_audio', 'paddleocr', 'indextts', 'wservice'
        }
        
        return service_name in valid_services and method_name
    
    def _create_task_context(self, task_id: str, task_name: str, input_data: Dict[str, Any], 
                           callback_url: Optional[str] = None) -> Dict[str, Any]:
        """创建任务上下文"""
        shared_storage_path = f"/share/workflows/{task_id}"
        os.makedirs(shared_storage_path, exist_ok=True)
        
        context = {
            "workflow_id": task_id,
            "create_at": datetime.now().isoformat(),
            "input_params": {
                "task_name": task_name,
                "input_data": input_data,
                "callback_url": callback_url
            },
            "shared_storage_path": shared_storage_path,
            "stages": {
                task_name: {
                    "status": "pending",
                    "output": {},
                    "start_time": None,
                    "end_time": None
                }
            },
            "error": None
        }
        
        return context
    
    def _create_task_record(self, task_id: str, context: Dict[str, Any], status: str):
        """创建任务记录"""
        try:
            context["status"] = status
            task_name = context.get("input_params", {}).get("task_name")
            existing_state = self._get_task_state(task_id)

            if existing_state and not existing_state.get("error"):
                merged_state = deepcopy(existing_state)
                merged_state["status"] = status
                merged_state["workflow_id"] = task_id
                merged_state["input_params"] = context["input_params"]
                merged_state["shared_storage_path"] = merged_state.get("shared_storage_path") or context.get("shared_storage_path")
                merged_state.setdefault("stages", {})
                if task_name:
                    merged_state["stages"][task_name] = context["stages"][task_name]
                if not merged_state.get("create_at"):
                    merged_state["create_at"] = context.get("create_at")

                workflow_context = WorkflowContext(**merged_state)
                update_workflow_state(workflow_context, skip_side_effects=True)
                logger.info(f"合并更新任务记录: {task_id}, 状态: {status}")
            else:
                workflow_context = WorkflowContext(**context)
                create_workflow_state(workflow_context)
                logger.info(f"创建任务记录: {task_id}, 状态: {status}")
        except Exception as e:
            logger.error(f"创建任务记录失败: {task_id}, 错误: {e}")
            raise

    def _check_reuse(self, task_id: str, task_name: str, callback_url: Optional[str]) -> Dict[str, Any]:
        """检查是否存在可复用的成功阶段"""
        try:
            existing_state = self._get_task_state(task_id)
            if not existing_state or existing_state.get("error"):
                return {"reuse_hit": False, "state": "miss", "reuse_info": None, "context": None}

            stages = existing_state.get("stages", {})
            stage_data = stages.get(task_name)
            if not stage_data:
                return {"reuse_hit": False, "state": "miss", "reuse_info": None, "context": existing_state}

            output = stage_data.get("output") or {}
            status = (stage_data.get("status") or "").lower()
            reuse_info = {
                "reuse_hit": True,
                "task_name": task_name,
                "source": "redis",
                "cached_at": stage_data.get("end_time") or datetime.now().isoformat()
            }

            if status == "success" and output:
                # 使用最新的回调地址进行回调，避免依赖旧请求；避免重复上传副作用
                state_copy = deepcopy(existing_state)
                state_copy["workflow_id"] = task_id
                state_copy["status"] = "completed"
                state_copy["reuse_info"] = reuse_info
                state_copy.setdefault("input_params", {})
                if callback_url:
                    state_copy["input_params"]["callback_url"] = callback_url
                state_copy.setdefault("stages", {})
                state_copy["stages"][task_name] = stage_data

                workflow_context = WorkflowContext(**state_copy)
                update_workflow_state(workflow_context, skip_side_effects=True)

                minio_files = output.get("minio_files") if isinstance(output, dict) else None
                if callback_url:
                    self._send_reuse_callback_async(task_id, state_copy, minio_files, callback_url)

                # Filter context for response
                filtered_context = self._filter_context_for_response(state_copy, task_name)

                return {
                    "reuse_hit": True,
                    "state": "completed",
                    "reuse_info": reuse_info,
                    "context": filtered_context
                }

            if status in ["pending", "running"]:
                reuse_info["state"] = status
                # Filter context for response
                filtered_context = self._filter_context_for_response(existing_state, task_name)
                
                return {
                    "reuse_hit": True,
                    "state": status,
                    "reuse_info": reuse_info,
                    "context": filtered_context
                }

            return {"reuse_hit": False, "state": "miss", "reuse_info": None, "context": existing_state}

        except Exception as e:
            logger.error(f"复用检查失败: {task_id}, 错误: {e}")
            return {"reuse_hit": False, "state": "miss", "reuse_info": None, "context": None}
    
    def _send_reuse_callback_async(self, task_id: str, payload: Dict[str, Any], minio_files: Optional[List[Dict[str, str]]], callback_url: str) -> None:
        """异步发送复用命中的callback，避免阻塞同步响应"""
        def _worker():
            cb_status = None
            try:
                if not self.callback_manager.validate_callback_url(callback_url):
                    cb_status = "invalid_url"
                else:
                    # Filter payload for callback consistency
                    task_name = payload.get("reuse_info", {}).get("task_name")
                    filtered_payload = self._filter_context_for_response(payload, task_name) if task_name else payload
                    
                    success = self.callback_manager.send_result(task_id, filtered_payload, minio_files, callback_url)
                    cb_status = "sent" if success else "failed"
            except Exception as e:
                logger.error(f"复用callback发送失败: {task_id}, 错误: {e}")
                cb_status = "failed"
            finally:
                try:
                    state = self._get_task_state(task_id) or {}
                    state["callback_status"] = cb_status
                    workflow_context = WorkflowContext(**state)
                    update_workflow_state(workflow_context, skip_side_effects=True)
                except Exception as e:
                    logger.error(f"复用callback状态更新失败: {task_id}, 错误: {e}")

        Thread(target=_worker, daemon=True).start()
    
    def _update_task_status(self, task_id: str, status: str, additional_data: Optional[Dict] = None):
        """更新任务状态"""
        try:
            # 获取现有状态
            state = self._get_task_state(task_id)
            if not state:
                raise ValueError(f"任务不存在: {task_id}")
            
            # 更新状态
            state["status"] = status
            state["updated_at"] = datetime.now().isoformat()
            
            if additional_data:
                for key, value in additional_data.items():
                    if key == "result":
                        state["result"] = value
                    elif key == "minio_files":
                        state["minio_files"] = value
                    elif key == "error":
                        state["error"] = value
                    else:
                        state[key] = value
            
            # 保存到Redis
            workflow_context = WorkflowContext(**state)
            update_workflow_state(workflow_context, skip_side_effects=True)

            logger.info(f"更新任务状态: {task_id} -> {status}")
            
        except Exception as e:
            logger.error(f"更新任务状态失败: {task_id}, 错误: {e}")
            raise
    
    def _get_task_state(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        return get_workflow_state(task_id)

    def _build_deletion_plan(self, task_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
        """构建删除计划，包括本地目录、Redis键和MinIO前缀"""
        shared_dir = state.get("shared_storage_path") or f"/share/workflows/{task_id}"
        redis_key_pattern = f"{task_id}:*:*"
        minio_prefix = f"{task_id}/"
        return {
            "local_dir": shared_dir,
            "redis_key_pattern": redis_key_pattern,
            "minio_prefix": minio_prefix,
        }

    def _delete_local_directory(self, directory_path: str) -> ResourceDeletionItem:
        """删除本地目录（幂等，限制在/share下）"""
        try:
            if not directory_path:
                return ResourceDeletionItem(
                    resource=DeletionResource.LOCAL_DIRECTORY,
                    status=DeletionResourceStatus.SKIPPED,
                    message="目录路径缺失",
                )
            if ".." in directory_path or not directory_path.startswith("/share/"):
                return ResourceDeletionItem(
                    resource=DeletionResource.LOCAL_DIRECTORY,
                    status=DeletionResourceStatus.FAILED,
                    message="无效目录路径，已拒绝越权访问",
                    retriable=False,
                )
            if not os.path.exists(directory_path):
                return ResourceDeletionItem(
                    resource=DeletionResource.LOCAL_DIRECTORY,
                    status=DeletionResourceStatus.SKIPPED,
                    message="目录不存在，已幂等",
                )
            if not os.path.isdir(directory_path):
                return ResourceDeletionItem(
                    resource=DeletionResource.LOCAL_DIRECTORY,
                    status=DeletionResourceStatus.FAILED,
                    message="目标路径不是目录",
                    retriable=False,
                )
            shutil.rmtree(directory_path)
            return ResourceDeletionItem(
                resource=DeletionResource.LOCAL_DIRECTORY,
                status=DeletionResourceStatus.DELETED,
                message=f"目录已删除: {directory_path}",
            )
        except PermissionError as e:
            logger.error(f"删除目录权限不足: {directory_path}, 错误: {e}")
            return ResourceDeletionItem(
                resource=DeletionResource.LOCAL_DIRECTORY,
                status=DeletionResourceStatus.FAILED,
                message="删除目录权限不足",
                retriable=False,
            )
        except Exception as e:
            logger.error(f"删除目录失败: {directory_path}, 错误: {e}", exc_info=True)
            return ResourceDeletionItem(
                resource=DeletionResource.LOCAL_DIRECTORY,
                status=DeletionResourceStatus.FAILED,
                message=f"删除目录失败: {e}",
                retriable=True,
            )

    def _delete_redis_state(self, redis_key_pattern: str) -> ResourceDeletionItem:
        """删除Redis状态键（按模式扫描，幂等）"""
        client = getattr(state_manager, "redis_client", None)
        if client is None:
            return ResourceDeletionItem(
                resource=DeletionResource.REDIS,
                status=DeletionResourceStatus.FAILED,
                message="Redis 未连接，无法删除状态",
                retriable=True,
            )
        try:
            keys = list(client.scan_iter(match=redis_key_pattern))
            if not keys:
                return ResourceDeletionItem(
                    resource=DeletionResource.REDIS,
                    status=DeletionResourceStatus.SKIPPED,
                    message="Redis 键不存在，已幂等",
                )
            removed = client.delete(*keys)
            return ResourceDeletionItem(
                resource=DeletionResource.REDIS,
                status=DeletionResourceStatus.DELETED,
                message=f"Redis 键已删除: {redis_key_pattern} ({removed})",
            )
        except Exception as e:
            logger.error(f"删除 Redis 键失败: {redis_key_pattern}, 错误: {e}", exc_info=True)
            return ResourceDeletionItem(
                resource=DeletionResource.REDIS,
                status=DeletionResourceStatus.FAILED,
                message=f"删除 Redis 键失败: {e}",
                retriable=True,
            )

    def _delete_minio_objects(self, prefix: str) -> ResourceDeletionItem:
        """删除 MinIO 前缀下的对象（幂等）"""
        try:
            objects = list(
                self.minio_service.client.list_objects(
                    self.minio_service.default_bucket,
                    prefix=prefix,
                    recursive=True,
                )
            )
            if not objects:
                return ResourceDeletionItem(
                    resource=DeletionResource.MINIO,
                    status=DeletionResourceStatus.SKIPPED,
                    message="未找到匹配对象",
                )
            deleted = 0
            for obj in objects:
                try:
                    self.minio_service.client.remove_object(
                        self.minio_service.default_bucket, obj.object_name
                    )
                    deleted += 1
                except Exception as e:
                    logger.warning(f"删除对象失败: {obj.object_name}, 错误: {e}", exc_info=True)
            if deleted == len(objects):
                return ResourceDeletionItem(
                    resource=DeletionResource.MINIO,
                    status=DeletionResourceStatus.DELETED,
                    message=f"已删除 {deleted} 个对象，前缀 {prefix}",
                )
            return ResourceDeletionItem(
                resource=DeletionResource.MINIO,
                status=DeletionResourceStatus.FAILED,
                message=f"部分对象删除失败，成功 {deleted}/{len(objects)}",
                retriable=True,
                details={"deleted": deleted, "total": len(objects)},
            )
        except Exception as e:
            logger.error(f"删除 MinIO 对象失败: 前缀 {prefix}, 错误: {e}", exc_info=True)
            return ResourceDeletionItem(
                resource=DeletionResource.MINIO,
                status=DeletionResourceStatus.FAILED,
                message=f"删除 MinIO 对象失败: {e}",
                retriable=True,
            )

    def delete_task(self, task_id: str, force: bool = False) -> TaskDeletionResult:
        """
        删除任务数据：本地目录、Redis 状态、MinIO 对象
        """
        state = self._get_task_state(task_id)
        if not state or state.get("status") == "not_found" or state.get("error"):
            raise ValueError(f"任务不存在: {task_id}")

        current_status = state.get("status")
        if not force and current_status in ("pending", "running"):
            raise PermissionError("任务执行中，未开启 force，不允许删除")

        plan = self._build_deletion_plan(task_id, state)
        results: List[ResourceDeletionItem] = []

        results.append(self._delete_local_directory(plan["local_dir"]))
        results.append(self._delete_redis_state(plan["redis_key_pattern"]))
        results.append(self._delete_minio_objects(plan["minio_prefix"]))

        has_failed = any(item.status == DeletionResourceStatus.FAILED for item in results)
        has_deleted = any(item.status == DeletionResourceStatus.DELETED for item in results)

        if has_failed and has_deleted:
            overall_status = TaskDeletionStatus.PARTIAL_FAILED
        elif has_failed:
            overall_status = TaskDeletionStatus.FAILED
        else:
            overall_status = TaskDeletionStatus.SUCCESS

        warnings = [
            item.message
            for item in results
            if (item.retriable or item.status == DeletionResourceStatus.SKIPPED) and item.message
        ]

        return TaskDeletionResult(
            status=overall_status,
            results=results,
            warnings=warnings or None,
            timestamp=datetime.utcnow().isoformat() + "Z",
        )
    
    def _build_task_signature(self, task_name: str, context: Dict[str, Any]):
        """构建Celery任务签名"""
        try:
            # 从任务名推断队列名
            queue_name = f"{task_name.split('.')[0]}_queue"
            task_options = {'queue': queue_name}
            
            # 创建任务签名
            task_sig = self.celery_app.signature(
                task_name,
                kwargs={'context': context},
                options=task_options,
                immutable=True
            )
            
            return task_sig
            
        except Exception as e:
            logger.error(f"构建任务签名失败: {task_name}, 错误: {e}")
            raise
    
    def _upload_result_files(self, task_id: str, result: Dict[str, Any]) -> List[Dict[str, str]]:
        """上传任务结果文件到MinIO"""
        minio_files = []
        
        try:
            logger.info(f"开始上传结果文件，task_id: {task_id}")
            # 查找结果中的文件路径
            file_paths = self._extract_file_paths(result)
            
            if not file_paths:
                logger.warning(f"未找到任何文件路径，task_id: {task_id}")
                return []
            
            for file_path in file_paths:
                if os.path.exists(file_path):
                    # 上传到MinIO
                    file_name = os.path.basename(file_path)
                    minio_path = f"{task_id}/{file_name}"
                    
                    logger.info(f"正在上传文件: {file_path} -> {minio_path}")
                    
                    # 直接使用文件路径上传，避免读取到内存
                    self.minio_service.client.fput_object(
                        self.minio_service.default_bucket,
                        minio_path,
                        file_path
                    )
                    
                    # 获取文件大小
                    file_size = os.path.getsize(file_path)
                    
                    # 生成下载URL
                    download_url = f"http://{self.minio_service.host}:{self.minio_service.port}/{self.minio_service.default_bucket}/{minio_path}"
                    
                    minio_files.append({
                        "name": file_name,
                        "url": download_url,
                        "type": self._get_file_type(file_name),
                        "size": file_size
                    })
                    
                    logger.info(f"文件上传成功: {minio_path}, URL: {download_url}")
                else:
                    logger.warning(f"文件不存在，跳过: {file_path}")
            
            logger.info(f"上传完成，共上传 {len(minio_files)} 个文件")
            return minio_files
            
        except Exception as e:
            logger.error(f"上传结果文件失败: {task_id}, 错误: {e}", exc_info=True)
            return []
    
    def _extract_file_paths(self, result: Dict[str, Any]) -> List[str]:
        """从结果中提取文件路径"""
        file_paths = []
        tracked_keys = [
            'audio_path', 'video_path', 'subtitle_path', 'output_path',
            'keyframe_dir', 'audio_segments_dir', 'cropped_images_path',
            'vocal_audio', 'instrumental_audio', 'background_audio',
            'all_audio_files'
        ]

        def maybe_append_path(value, key_name=None):
            if isinstance(value, str) and os.path.exists(value):
                file_paths.append(value)
                if key_name:
                    logger.info(f"找到文件路径: {key_name} = {value}")

        def extract_paths_recursive(obj):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if key in tracked_keys:
                        maybe_append_path(value, key)
                    elif key in ['audio_list', 'all_audio_files'] and isinstance(value, list):
                        for item in value:
                            maybe_append_path(item, f"{key}[]")
                    extract_paths_recursive(value)
            elif isinstance(obj, list):
                for item in obj:
                    extract_paths_recursive(item)

        logger.info(f"开始提取文件路径，result keys: {list(result.keys())}")
        extract_paths_recursive(result)
        logger.info(f"提取到 {len(file_paths)} 个文件路径: {file_paths}")
        return list(set(file_paths))  # 去重
    
    def _get_file_type(self, filename: str) -> str:
        """根据文件名获取文件类型"""
        extension = filename.lower().split('.')[-1]
        
        type_mapping = {
            'mp4': 'video',
            'avi': 'video', 
            'mov': 'video',
            'wav': 'audio',
            'mp3': 'audio',
            'flac': 'audio',
            'srt': 'subtitle',
            'vtt': 'subtitle',
            'txt': 'text',
            'json': 'data',
            'jpg': 'image',
            'png': 'image'
        }
        
        return type_mapping.get(extension, 'unknown')
    
    def _send_callback_if_needed(self, task_id: str, result: Dict[str, Any], 
                               minio_files: Optional[List[Dict[str, str]]]):
        """如果需要则发送callback"""
        try:
            # 获取任务的callback URL
            state = self._get_task_state(task_id)
            if not state:
                return
            
            callback_url = state.get("input_params", {}).get("callback_url")
            if not callback_url:
                return
            
            # 验证callback URL
            if not self.callback_manager.validate_callback_url(callback_url):
                logger.warning(f"无效的callback URL: {callback_url}")
                self._update_task_status(task_id, state["status"], {
                    "callback_status": "invalid_url"
                })
                return
            
            # Filter result for callback consistency
            task_name = state.get("input_params", {}).get("task_name")
            filtered_result = self._filter_context_for_response(result, task_name) if task_name else result

            # 发送callback
            success = self.callback_manager.send_result(
                task_id, filtered_result, minio_files, callback_url
            )
            
            callback_status = "sent" if success else "failed"
            self._update_task_status(task_id, state["status"], {
                "callback_status": callback_status
            })
            
            logger.info(f"Callback发送完成: {task_id}, 状态: {callback_status}")
            
        except Exception as e:
            logger.error(f"发送callback失败: {task_id}, 错误: {e}")
            self._update_task_status(task_id, "completed", {
                "callback_status": "error"
            })

# 单例模式
_single_task_executor_instance = None

def get_single_task_executor() -> SingleTaskExecutor:
    """获取单任务执行器实例"""
    global _single_task_executor_instance
    if _single_task_executor_instance is None:
        _single_task_executor_instance = SingleTaskExecutor()
    return _single_task_executor_instance

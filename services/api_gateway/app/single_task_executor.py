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
from datetime import datetime
from typing import Dict, Any, List, Optional
from celery import Celery, signature
from celery.result import AsyncResult

from services.common.logger import get_logger
from services.common.celery_config import BROKER_URL, BACKEND_URL
from services.common.context import WorkflowContext
from services.common.state_manager import create_workflow_state, get_workflow_state, update_workflow_state

from .minio_service import get_minio_service
from .callback_manager import get_callback_manager

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
    
    def execute_task(self, task_name: str, task_id: str, input_data: Dict[str, Any],
                    callback_url: Optional[str] = None) -> str:
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
        
        # 创建任务状态记录
        self._create_task_record(task_id, context, "pending")
        
        try:
            # 构建Celery任务签名
            task_signature = self._build_task_signature(task_name, context)
            
            # 异步执行任务
            celery_result = task_signature.apply_async()
            celery_task_id = celery_result.id
            
            # 更新任务状态为running
            self._update_task_status(task_id, "running", {"celery_task_id": celery_task_id})
            
            logger.info(f"单任务提交成功: {task_name}, ID: {task_id}, Celery Task ID: {celery_task_id}")
            return celery_task_id
            
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
            
            return state
            
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
            'ffmpeg', 'faster_whisper', 'audio_separator', 'pyannote_audio',
            'paddleocr', 'indextts', 'wservice'
        }
        
        return service_name in valid_services and method_name
    
    def _create_task_context(self, task_id: str, task_name: str, input_data: Dict[str, Any], 
                           callback_url: Optional[str] = None) -> Dict[str, Any]:
        """创建任务上下文"""
        shared_storage_path = f"/share/single_tasks/{task_id}"
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
            workflow_context = WorkflowContext(**context)
            create_workflow_state(workflow_context)
            logger.info(f"创建任务记录: {task_id}, 状态: {status}")
        except Exception as e:
            logger.error(f"创建任务记录失败: {task_id}, 错误: {e}")
            raise
    
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
            update_workflow_state(workflow_context)
            
            logger.info(f"更新任务状态: {task_id} -> {status}")
            
        except Exception as e:
            logger.error(f"更新任务状态失败: {task_id}, 错误: {e}")
            raise
    
    def _get_task_state(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        return get_workflow_state(task_id)
    
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
        
        def extract_paths_recursive(obj):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if key in ['audio_path', 'video_path', 'subtitle_path', 'output_path',
                              'keyframe_dir', 'audio_segments_dir', 'cropped_images_path']:
                        if isinstance(value, str) and os.path.exists(value):
                            file_paths.append(value)
                            logger.info(f"找到文件路径: {key} = {value}")
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
            
            # 发送callback
            success = self.callback_manager.send_result(
                task_id, result, minio_files, callback_url
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
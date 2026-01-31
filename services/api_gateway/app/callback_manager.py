# services/api_gateway/app/callback_manager.py
# -*- coding: utf-8 -*-

"""
Callback管理器。

负责处理任务完成后的callback通知机制。
"""

import time
import requests
from datetime import datetime
from typing import Dict, Any, List, Optional
from services.common.logger import get_logger

logger = get_logger('callback_manager')


class CallbackManager:
    """Callback管理器类"""
    
    def __init__(self):
        """初始化Callback管理器"""
        self.max_retries = 5
        self.retry_delays = [5, 5, 5, 5]  # 固定 5 秒间隔
        self.timeout = 30  # 请求超时时间
        logger.info("Callback管理器初始化完成")
    
    def send_result(self, task_id: str, result: Dict[str, Any],
                   minio_files: Optional[List[Dict[str, str]]], callback_url: str) -> bool:
        """
        发送任务结果到callback URL

        Args:
            task_id: 任务ID
            result: 任务执行结果
            minio_files: MinIO文件信息列表
            callback_url: callback URL

        Returns:
            bool: 是否发送成功
        """
        if not callback_url:
            logger.warning(f"任务 {task_id} 没有提供callback URL")
            return False

        # 构建callback数据
        callback_data = self._build_callback_data(task_id, result, minio_files)

        logger.info(f"开始发送callback，任务ID: {task_id}, URL: {callback_url}")

        # 重试发送 - 所有错误都重试5次
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    callback_url,
                    json=callback_data,
                    headers={
                        'Content-Type': 'application/json',
                        'User-Agent': 'YiVideo-API-Gateway/1.0'
                    },
                    timeout=self.timeout
                )
                response.raise_for_status()

                logger.info(f"Callback发送成功，任务ID: {task_id}, 状态码: {response.status_code}")
                return True

            except requests.exceptions.Timeout:
                logger.warning(f"Callback超时，任务ID: {task_id}, 尝试: {attempt + 1}/{self.max_retries}")
            except requests.exceptions.ConnectionError as e:
                logger.warning(f"Callback连接错误，任务ID: {task_id}, 尝试: {attempt + 1}/{self.max_retries}, 错误: {e}")
            except requests.exceptions.HTTPError as e:
                logger.warning(f"Callback HTTP错误，任务ID: {task_id}, 尝试: {attempt + 1}/{self.max_retries}, 错误: {e}")
            except Exception as e:
                logger.warning(f"Callback发送未知错误，任务ID: {task_id}, 尝试: {attempt + 1}/{self.max_retries}, 错误: {e}")

            # 如果不是最后一次尝试，等待后重试
            if attempt < self.max_retries - 1:
                delay = self.retry_delays[min(attempt, len(self.retry_delays) - 1)]
                logger.info(f"等待 {delay} 秒后重试...")
                time.sleep(delay)

        logger.error(f"所有callback尝试都失败，任务ID: {task_id}")
        return False
    
    def _build_callback_data(self, task_id: str, result: Dict[str, Any], 
                           minio_files: Optional[List[Dict[str, str]]]) -> Dict[str, Any]:
        """
        构建callback数据
        
        Args:
            task_id: 任务ID
            result: 任务执行结果
            minio_files: MinIO文件信息列表
            
        Returns:
            Dict: callback数据
        """
        # 确定任务状态
        task_status = "completed"
        if result.get('status') == 'FAILED':
            task_status = "failed"
        elif result.get('error'):  # 检查error的值而非键
            task_status = "failed"
        
        callback_data = {
            "task_id": task_id,
            "status": task_status,
            "result": result,
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }
        
        # 添加MinIO文件信息
        if minio_files:
            callback_data["minio_files"] = minio_files
        
        return callback_data
    
    def validate_callback_url(self, callback_url: str) -> bool:
        """
        验证callback URL的有效性
        
        Args:
            callback_url: 要验证的callback URL
            
        Returns:
            bool: URL是否有效
        """
        if not callback_url:
            return False
        
        # 基本的URL格式验证
        if not (callback_url.startswith('http://') or callback_url.startswith('https://')):
            logger.warning(f"callback URL格式不正确: {callback_url}")
            return False
        
        # 检查URL长度
        if len(callback_url) > 2048:
            logger.warning(f"callback URL过长: {len(callback_url)} 字符")
            return False
        
        # 简单的域名验证（避免内网地址）
        import urllib.parse
        try:
            parsed = urllib.parse.urlparse(callback_url)
            if parsed.hostname:
                hostname = parsed.hostname.lower()
                # 阻止localhost、127.0.0.1等本地地址
                if hostname in ['localhost', '127.0.0.1', '0.0.0.0'] or hostname.endswith('.local'):
                    logger.warning(f"callback URL不允许使用本地地址: {callback_url}")
                    return False
        except Exception as e:
            logger.warning(f"callback URL解析失败: {callback_url}, 错误: {e}")
            return False
        
        return True
    
    def send_batch_results(self, callbacks: List[Dict[str, Any]]) -> Dict[str, bool]:
        """
        批量发送callback结果
        
        Args:
            callbacks: callback信息列表，每个元素包含 task_id, result, minio_files, callback_url
            
        Returns:
            Dict: task_id 到发送结果的映射
        """
        results = {}
        
        logger.info(f"开始批量发送 {len(callbacks)} 个callback")
        
        for callback_info in callbacks:
            task_id = callback_info.get('task_id')
            if not task_id:
                logger.warning("callback信息中缺少task_id")
                continue
            
            result = callback_info.get('result', {})
            minio_files = callback_info.get('minio_files', [])
            callback_url = callback_info.get('callback_url')
            
            success = self.send_result(task_id, result, minio_files, callback_url)
            results[task_id] = success
        
        success_count = sum(1 for success in results.values() if success)
        logger.info(f"批量callback发送完成，成功: {success_count}/{len(results)}")
        
        return results
    
    def get_callback_retry_info(self, attempt: int, max_attempts: int) -> Dict[str, Any]:
        """
        获取callback重试信息
        
        Args:
            attempt: 当前尝试次数
            max_attempts: 最大尝试次数
            
        Returns:
            Dict: 重试信息
        """
        if attempt >= max_attempts:
            return {
                "should_retry": False,
                "reason": "已达到最大重试次数"
            }
        
        delay = self.retry_delays[min(attempt, len(self.retry_delays) - 1)]
        
        return {
            "should_retry": True,
            "delay": delay,
            "next_attempt": attempt + 1,
            "remaining_attempts": max_attempts - attempt - 1
        }


# 单例模式
_callback_manager_instance = None

def get_callback_manager() -> CallbackManager:
    """获取Callback管理器实例"""
    global _callback_manager_instance
    if _callback_manager_instance is None:
        _callback_manager_instance = CallbackManager()
    return _callback_manager_instance

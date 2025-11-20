# -*- coding: utf-8 -*-

"""
MinIO目录下载模块

提供从MinIO下载整个目录的功能，支持：
- 批量下载目录中的所有文件
- 保留目录结构
- 错误处理和日志记录
"""

import os
import glob
from pathlib import Path
from typing import List, Dict, Optional, Union
from services.common.logger import get_logger
from services.common.file_service import get_file_service

logger = get_logger('minio_directory_download')

class MinioDirectoryDownloader:
    """MinIO目录下载器"""
    
    def __init__(self, file_service=None):
        """
        初始化目录下载器
        
        Args:
            file_service: 文件服务实例（可选，默认使用全局实例）
        """
        self.file_service = file_service or get_file_service()
        
    def download_directory(self, 
                          minio_url: str,
                          local_dir: str,
                          file_pattern: str = "*",
                          create_structure: bool = True) -> Dict[str, Union[str, List[str]]]:
        """
        从MinIO下载目录到本地
        
        Args:
            minio_url: MinIO目录URL（格式：minio://bucket/path/to/dir）
            local_dir: 本地目标目录
            file_pattern: 文件匹配模式（默认 "*" 匹配所有文件）
            create_structure: 是否在本地创建相同的目录结构（默认True）
            
        Returns:
            Dict: 包含下载结果和文件列表的字典
            {
                "success": True/False,
                "local_dir": "/local/download/path",
                "downloaded_files": ["file1.jpg", "file2.jpg", ...],
                "total_files": 10,
                "failed_files": ["file3.jpg", ...],
                "error": "错误信息（如果有）"
            }
            
        Raises:
            ValueError: MinIO URL格式无效
            FileNotFoundError: MinIO路径不存在
        """
        # 参数验证
        if not minio_url or not minio_url.strip().startswith('minio://'):
            raise ValueError(f"无效的MinIO URL格式: {minio_url}")
            
        if not local_dir or not local_dir.strip():
            raise ValueError("local_dir 不能为空")
        
        # 解析MinIO URL
        from urllib.parse import urlparse
        parsed_url = urlparse(minio_url)
        bucket_name = parsed_url.netloc
        minio_base_path = parsed_url.path.lstrip('/')
        
        if not bucket_name:
            raise ValueError(f"无法从URL中提取bucket名称: {minio_url}")
        
        # 构建结果字典
        result = {
            "success": False,
            "local_dir": local_dir,
            "downloaded_files": [],
            "failed_files": [],
            "total_files": 0,
            "error": None
        }
        
        try:
            logger.info(f"开始下载MinIO目录: {minio_url}")
            
            # 确保本地目录存在
            os.makedirs(local_dir, exist_ok=True)
            
            # 获取bucket中所有对象
            objects_list = list(self.file_service.minio_client.list_objects(
                bucket_name, 
                prefix=minio_base_path.rstrip('/') + '/',
                recursive=True
            ))
            
            if not objects_list:
                logger.warning(f"MinIO目录为空或不存在: {minio_base_path}")
                result["success"] = True  # 空目录不算失败
                return result
            
            # 过滤出匹配的文件
            files_to_download = []
            for obj in objects_list:
                if obj.object_name.endswith('/'):
                    continue  # 跳过目录
                
                # 检查是否匹配文件模式
                if self._matches_pattern(obj.object_name, minio_base_path, file_pattern):
                    files_to_download.append(obj)
            
            result["total_files"] = len(files_to_download)
            
            if not files_to_download:
                logger.warning(f"目录中没有匹配模式的文件: {minio_base_path} / {file_pattern}")
                result["success"] = True  # 无匹配文件不算失败
                return result
            
            logger.info(f"找到 {len(files_to_download)} 个文件需要下载")

            # 并发下载文件（使用线程池）
            from concurrent.futures import ThreadPoolExecutor, as_completed

            def download_single_file(obj):
                """单文件下载任务"""
                try:
                    # 计算相对路径
                    if create_structure:
                        # 保留目录结构
                        rel_path = os.path.relpath(obj.object_name, minio_base_path)
                        local_file_path = os.path.join(local_dir, rel_path)
                    else:
                        # 只保留文件名
                        local_file_path = os.path.join(local_dir, os.path.basename(obj.object_name))

                    # 确保本地目录存在
                    os.makedirs(os.path.dirname(local_file_path), exist_ok=True)

                    # 下载文件
                    self.file_service.minio_client.fget_object(
                        bucket_name,
                        obj.object_name,
                        local_file_path
                    )

                    return {
                        'success': True,
                        'file': obj.object_name,
                        'local_path': local_file_path,
                        'rel_path': os.path.relpath(local_file_path, local_dir).replace('\\', '/')
                    }

                except Exception as e:
                    # 返回失败信息
                    file_name = os.path.basename(obj.object_name)
                    logger.error(f"文件下载失败: {obj.object_name}, 错误: {e}")
                    return {
                        'success': False,
                        'file': obj.object_name,
                        'error': str(e)
                    }

            # 使用线程池并发下载，限制最大并发数避免HTTP连接池过载
            # 限制为10，与urllib3默认HTTP连接池大小保持一致，避免"Connection pool is full"警告
            max_workers = min(10, (len(files_to_download) + 1) // 2)
            logger.info(f"使用 {max_workers} 个并发线程下载 {len(files_to_download)} 个文件")
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 提交所有下载任务
                future_to_obj = {executor.submit(download_single_file, obj): obj for obj in files_to_download}

                # 收集结果
                for future in as_completed(future_to_obj):
                    download_result = future.result()
                    if download_result['success']:
                        result["downloaded_files"].append(download_result['rel_path'])
                    else:
                        result["failed_files"].append(os.path.basename(download_result['file']))
            
            # 判断整体是否成功
            if not result["failed_files"]:
                result["success"] = True
                logger.info(f"目录下载完成: {len(result['downloaded_files'])}/{result['total_files']} 个文件下载成功")
            else:
                result["error"] = f"{len(result['failed_files'])} 个文件下载失败"
                logger.warning(f"目录下载部分失败: {len(result['downloaded_files'])}/{result['total_files']} 个文件下载成功")
                
            return result
            
        except Exception as e:
            logger.error(f"目录下载过程中发生错误: {e}", exc_info=True)
            result["error"] = str(e)
            return result
    
    def _matches_pattern(self, object_name: str, base_path: str, pattern: str) -> bool:
        """检查对象名是否匹配文件模式"""
        if pattern == "*":
            return True
        
        # 获取相对路径
        rel_path = os.path.relpath(object_name, base_path)
        
        # 简单的通配符匹配（只支持 *）
        if "*" in pattern:
            pattern_regex = pattern.replace(".", r"\.").replace("*", ".*")
            import re
            return bool(re.match(f"^{pattern_regex}$", rel_path))
        else:
            return rel_path == pattern

def download_directory_from_minio(minio_url: str,
                                 local_dir: str,
                                 file_pattern: str = "*",
                                 create_structure: bool = True) -> Dict[str, Union[str, List[str]]]:
    """
    便捷函数：从MinIO下载目录
    
    Args:
        minio_url: MinIO目录URL
        local_dir: 本地目标目录
        file_pattern: 文件匹配模式
        create_structure: 是否保留目录结构
        
    Returns:
        Dict: 下载结果字典
    """
    downloader = MinioDirectoryDownloader()
    return downloader.download_directory(
        minio_url=minio_url,
        local_dir=local_dir,
        file_pattern=file_pattern,
        create_structure=create_structure
    )

def download_keyframes_directory(minio_url: str,
                                workflow_id: str,
                                local_dir: str) -> Dict[str, Union[str, List[str]]]:
    """
    专门用于下载关键帧目录的便捷函数
    
    Args:
        minio_url: 关键帧目录的MinIO URL
        workflow_id: 工作流ID，用于验证路径（可选）
        local_dir: 本地目标目录
        
    Returns:
        Dict: 下载结果字典
    """
    # 只下载JPEG图片文件
    file_pattern = "*.jpg"
    
    return download_directory_from_minio(
        minio_url=minio_url,
        local_dir=local_dir,
        file_pattern=file_pattern,
        create_structure=True
    )
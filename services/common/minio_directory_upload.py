# -*- coding: utf-8 -*-

"""
MinIO目录上传模块

提供递归上传整个目录到MinIO的功能，支持：
- 批量上传目录中的所有文件
- 保留目录结构
- 可选的本地目录清理
- 错误处理和日志记录
"""

import os
import glob
from pathlib import Path
from typing import List, Dict, Optional, Union
from services.common.logger import get_logger
from services.common.file_service import get_file_service

logger = get_logger('minio_directory_upload')

class MinioDirectoryUploader:
    """MinIO目录上传器"""
    
    def __init__(self, file_service=None):
        """
        初始化目录上传器
        
        Args:
            file_service: 文件服务实例（可选，默认使用全局实例）
        """
        self.file_service = file_service or get_file_service()
        
    def upload_directory(self, 
                        local_dir: str, 
                        minio_base_path: str, 
                        bucket_name: Optional[str] = None,
                        file_pattern: str = "*",
                        delete_local: bool = False,
                        preserve_structure: bool = True) -> Dict[str, Union[str, List[str]]]:
        """
        递归上传目录到MinIO
        
        Args:
            local_dir: 本地目录路径
            minio_base_path: MinIO中的基础路径（不包含bucket）
            bucket_name: 存储桶名称（默认使用default_bucket）
            file_pattern: 文件匹配模式（默认 "*" 匹配所有文件）
            delete_local: 上传成功后是否删除本地目录（默认False）
            preserve_structure: 是否保留目录结构（默认True）
            
        Returns:
            Dict: 包含上传结果和文件列表的字典
            {
                "success": True/False,
                "minio_base_url": "http://minio:9000/bucket/path",
                "uploaded_files": ["file1.jpg", "file2.jpg", ...],
                "total_files": 10,
                "failed_files": ["file3.jpg", ...],
                "error": "错误信息（如果有）"
            }
            
        Raises:
            FileNotFoundError: 本地目录不存在
            ValueError: 参数无效
        """
        # 参数验证
        if not os.path.exists(local_dir):
            raise FileNotFoundError(f"本地目录不存在: {local_dir}")
            
        if not os.path.isdir(local_dir):
            raise ValueError(f"路径不是目录: {local_dir}")
            
        if not minio_base_path or not minio_base_path.strip():
            raise ValueError("minio_base_path 不能为空")
            
        bucket_name = bucket_name or self.file_service.default_bucket
        
        # 构建结果字典
        result = {
            "success": False,
            "minio_base_url": "",
            "uploaded_files": [],
            "failed_files": [],
            "total_files": 0,
            "error": None
        }
        
        try:
            # 查找所有匹配的文件
            if preserve_structure:
                # 保留目录结构，递归查找
                search_pattern = os.path.join(local_dir, "**", file_pattern)
                all_files = glob.glob(search_pattern, recursive=True)
                # 过滤出文件（排除目录）
                files_to_upload = [f for f in all_files if os.path.isfile(f)]
            else:
                # 不保留结构，只在顶层目录查找
                search_pattern = os.path.join(local_dir, file_pattern)
                all_files = glob.glob(search_pattern)
                files_to_upload = [f for f in all_files if os.path.isfile(f)]
            
            result["total_files"] = len(files_to_upload)
            
            if not files_to_upload:
                logger.warning(f"目录中没有找到匹配模式的文件: {local_dir} / {file_pattern}")
                result["success"] = True  # 空目录不算失败
                result["minio_base_url"] = f"http://{self.file_service.minio_host}:{self.file_service.minio_port}/{bucket_name}/{minio_base_path}"
                return result
            
            logger.info(f"开始上传目录 {local_dir} 到 MinIO 路径: {bucket_name}/{minio_base_path}")
            logger.info(f"找到 {len(files_to_upload)} 个文件需要上传")
            
            # 逐个上传文件
            for local_file_path in sorted(files_to_upload):
                try:
                    # 计算相对路径
                    if preserve_structure:
                        rel_path = os.path.relpath(local_file_path, local_dir)
                    else:
                        rel_path = os.path.basename(local_file_path)
                    
                    # 构建MinIO对象路径
                    minio_object_path = f"{minio_base_path.rstrip('/')}/{rel_path}".replace('\\', '/')
                    
                    # 上传文件
                    minio_url = self.file_service.upload_to_minio(
                        local_file_path, 
                        minio_object_path, 
                        bucket_name
                    )
                    
                    # 添加到成功列表
                    result["uploaded_files"].append(rel_path.replace('\\', '/'))
                    logger.debug(f"上传成功: {local_file_path} -> {minio_object_path}")
                    
                except Exception as e:
                    # 添加到失败列表
                    file_name = os.path.basename(local_file_path)
                    result["failed_files"].append(file_name)
                    logger.error(f"文件上传失败: {local_file_path}, 错误: {e}")
            
            # 构建基础URL
            result["minio_base_url"] = f"http://{self.file_service.minio_host}:{self.file_service.minio_port}/{bucket_name}/{minio_base_path.rstrip('/')}"
            
            # 判断整体是否成功
            if not result["failed_files"]:
                result["success"] = True
                logger.info(f"目录上传完成: {len(result['uploaded_files'])}/{result['total_files']} 个文件上传成功")
            else:
                result["error"] = f"{len(result['failed_files'])} 个文件上传失败"
                logger.warning(f"目录上传部分失败: {len(result['uploaded_files'])}/{result['total_files']} 个文件上传成功")
                
            # 可选：删除本地目录
            if delete_local and result["success"]:
                try:
                    import shutil
                    shutil.rmtree(local_dir)
                    logger.info(f"已删除本地目录: {local_dir}")
                except Exception as e:
                    logger.warning(f"删除本地目录失败: {local_dir}, 错误: {e}")
            
            return result
            
        except Exception as e:
            logger.error(f"目录上传过程中发生错误: {e}", exc_info=True)
            result["error"] = str(e)
            return result

def upload_directory_to_minio(local_dir: str, 
                             minio_base_path: str, 
                             bucket_name: Optional[str] = None,
                             file_pattern: str = "*",
                             delete_local: bool = False,
                             preserve_structure: bool = True) -> Dict[str, Union[str, List[str]]]:
    """
    便捷函数：上传目录到MinIO
    
    Args:
        local_dir: 本地目录路径
        minio_base_path: MinIO中的基础路径
        bucket_name: 存储桶名称
        file_pattern: 文件匹配模式
        delete_local: 上传成功后是否删除本地目录
        preserve_structure: 是否保留目录结构
        
    Returns:
        Dict: 上传结果字典
    """
    uploader = MinioDirectoryUploader()
    return uploader.upload_directory(
        local_dir=local_dir,
        minio_base_path=minio_base_path,
        file_pattern=file_pattern,
        delete_local=delete_local,
        preserve_structure=preserve_structure
    )

def upload_keyframes_directory(local_dir: str, 
                              workflow_id: str,
                              delete_local: bool = False) -> Dict[str, Union[str, List[str]]]:
    """
    专门用于上传关键帧目录的便捷函数
    
    Args:
        local_dir: 关键帧本地目录路径
        workflow_id: 工作流ID，用于构建MinIO路径
        delete_local: 上传成功后是否删除本地目录（默认False）
        
    Returns:
        Dict: 上传结果字典
    """
    # 构建关键帧在MinIO中的路径
    minio_base_path = f"{workflow_id}/keyframes"
    
    # 只上传JPEG图片文件
    file_pattern = "*.jpg"
    
    return upload_directory_to_minio(
        local_dir=local_dir,
        minio_base_path=minio_base_path,
        file_pattern=file_pattern,
        delete_local=delete_local,
        preserve_structure=True
    )
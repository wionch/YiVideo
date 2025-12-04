# -*- coding: utf-8 -*-

"""
MinIO目录上传模块

提供递归上传整个目录到MinIO的功能，支持：
- 批量上传目录中的所有文件
- 保留目录结构
- 可选的本地目录清理
- 错误处理和日志记录
- 压缩包上传（新增）
- 压缩前上传（新增）
"""

import os
import glob
import tempfile
import shutil
from pathlib import Path
from typing import List, Dict, Optional, Union, Callable
from services.common.logger import get_logger
from services.common.file_service import get_file_service
from services.common.directory_compression import (
    DirectoryCompressor, 
    CompressionFormat, 
    CompressionLevel,
    CompressionProgress,
    compress_directory,
    decompress_archive
)
from services.common.temp_path_utils import get_temp_path

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
        self.compressor = DirectoryCompressor()
        
    def upload_directory_compressed(self,
                                   local_dir: str,
                                   minio_base_path: str,
                                   bucket_name: Optional[str] = None,
                                   file_pattern: str = "*",
                                   compression_format: CompressionFormat = CompressionFormat.ZIP,
                                   compression_level: CompressionLevel = CompressionLevel.DEFAULT,
                                   delete_local: bool = False,
                                   preserve_structure: bool = True,
                                   progress_callback: Optional[Callable[[CompressionProgress], None]] = None,
                                   workflow_id: Optional[str] = None) -> Dict[str, Union[str, List[str], Dict]]:
        """
        压缩目录并上传到MinIO
        
        Args:
            local_dir: 本地目录路径
            minio_base_path: MinIO中的基础路径（不包含bucket）
            bucket_name: 存储桶名称（默认使用default_bucket）
            file_pattern: 文件匹配模式
            compression_format: 压缩格式
            compression_level: 压缩级别
            delete_local: 上传成功后是否删除本地目录（默认False）
            preserve_structure: 是否保留目录结构（默认True）
            progress_callback: 压缩进度回调函数
            workflow_id: 工作流ID，用于构建任务特定的临时目录（可选）
            
        Returns:
            Dict: 包含上传结果和压缩信息的字典
            {
                "success": True/False,
                "minio_base_url": "http://minio:9000/bucket/path",
                "archive_url": "http://minio:9000/bucket/path/archive.zip",
                "compression_info": {
                    "original_size": 450000000,
                    "compressed_size": 150000000,
                    "compression_ratio": 0.67,
                    "files_count": 15230,
                    "compression_time": 45.2,
                    "checksum": "sha256:..."
                },
                "total_files": 15230,
                "error": "错误信息（如果有）"
            }
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
            "archive_url": "",
            "compression_info": {},
            "total_files": 0,
            "error": None
        }
        
        # 临时压缩包路径
        temp_archive_path = None
        
        try:
            # 确保 workflow_id 存在
            if not workflow_id:
                raise ValueError("workflow_id is required for temporary file creation")
            
            source_name = os.path.basename(local_dir) or "directory"
            
            # 生成基于工作流ID的临时压缩包路径
            suffix = ".zip" if compression_format == CompressionFormat.ZIP else ".tar.gz"
            temp_archive_path = get_temp_path(
                workflow_id, 
                f"_{source_name}_compressed{suffix}"
            )

            logger.info(f"开始压缩目录: {local_dir}")
            logger.info(f"压缩格式: {compression_format.value}, 级别: {compression_level.name}")
            
            # 执行压缩
            # 将逗号分隔的文件模式字符串转换为列表
            file_patterns_list = None
            if file_pattern != "*":
                # 分割逗号分隔的模式字符串，并去除空格
                file_patterns_list = [p.strip() for p in file_pattern.split(',') if p.strip()]

            compression_result = self.compressor.compress_directory(
                source_dir=local_dir,
                output_path=temp_archive_path,
                compression_format=compression_format,
                compression_level=compression_level,
                progress_callback=progress_callback,
                file_patterns=file_patterns_list
            )

            if not compression_result.success:
                result["error"] = f"压缩失败: {compression_result.error_message}"
                return result

            # 获取压缩包信息
            archive_info = self.compressor.get_archive_info(temp_archive_path)

            # 构建MinIO对象路径（压缩包路径）
            archive_object_path = f"{minio_base_path.rstrip('/')}/{source_name}_compressed.{compression_format.value}"
            
            logger.info(f"开始上传压缩包: {temp_archive_path} -> {archive_object_path}")
            
            # 上传压缩包
            minio_url = self.file_service.upload_to_minio(
                temp_archive_path,
                archive_object_path,
                bucket_name
            )
            
            # 构建基础URL（压缩包目录）
            base_url = f"http://{self.file_service.minio_host}:{self.file_service.minio_port}/{bucket_name}/{minio_base_path.rstrip('/')}"
            archive_url = f"http://{self.file_service.minio_host}:{self.file_service.minio_port}/{bucket_name}/{archive_object_path}"
            
            result.update({
                "success": True,
                "minio_base_url": base_url,
                "archive_url": archive_url,
                "compression_info": {
                    "original_size": compression_result.original_size,
                    "compressed_size": compression_result.compressed_size,
                    "compression_ratio": compression_result.compression_ratio,
                    "files_count": compression_result.files_count,
                    "compression_time": compression_result.compression_time,
                    "checksum": compression_result.checksum,
                    "format": compression_format.value
                },
                "total_files": compression_result.files_count
            })
            
            logger.info(f"压缩上传完成: {compression_result.compression_ratio:.1%} 压缩率, "
                       f"{compression_result.files_count} 个文件")
            
            # 可选：删除本地目录和压缩包
            if delete_local:
                try:
                    shutil.rmtree(local_dir)
                    logger.info(f"已删除本地目录: {local_dir}")
                except Exception as e:
                    logger.warning(f"删除本地目录失败: {local_dir}, 错误: {e}")
            
            return result
            
        except Exception as e:
            error_msg = f"压缩上传过程中发生错误: {str(e)}"
            logger.error(error_msg, exc_info=True)
            result["error"] = error_msg
            return result
            
        finally:
            # 清理临时压缩包
            if temp_archive_path and os.path.exists(temp_archive_path):
                try:
                    os.remove(temp_archive_path)
                    logger.debug(f"已清理临时压缩包: {temp_archive_path}")
                except Exception as e:
                    logger.warning(f"清理临时压缩包失败: {temp_archive_path}, 错误: {e}")
            
            # 清理临时目录（如果是基于workflow_id创建的）
            if workflow_id:
                temp_base_dir = os.path.join("/share/workflows", workflow_id, "tmp")
                try:
                    if os.path.exists(temp_base_dir) and not os.listdir(temp_base_dir):
                        os.rmdir(temp_base_dir)
                        logger.debug(f"已清理空临时目录: {temp_base_dir}")
                except Exception as e:
                    logger.debug(f"清理临时目录失败（可能非空）: {temp_base_dir}, 错误: {e}")
    
    def download_and_extract(self,
                            minio_url: str,
                            local_dir: str,
                            auto_extract: bool = True,
                            overwrite: bool = False,
                            progress_callback: Optional[Callable[[CompressionProgress], None]] = None) -> Dict[str, Union[str, bool]]:
        """
        从MinIO下载压缩包并自动解压
        
        Args:
            minio_url: MinIO压缩包URL
            local_dir: 本地目标目录
            auto_extract: 是否自动解压
            overwrite: 是否覆盖已存在的文件
            progress_callback: 解压进度回调函数
            
        Returns:
            Dict: 下载和解压结果
            {
                "success": True/False,
                "downloaded_file": "/tmp/downloaded.zip",
                "extracted_dir": "/path/to/extracted/files",
                "extracted_files": 15230,
                "error": "错误信息（如果有）"
            }
        """
        result = {
            "success": False,
            "downloaded_file": "",
            "extracted_dir": "",
            "extracted_files": 0,
            "error": None
        }
        
        # 下载压缩包
        try:
            downloaded_file = self.file_service.download_from_minio(minio_url, local_dir)
            result["downloaded_file"] = downloaded_file
            
            if not auto_extract:
                result["success"] = True
                return result
            
            # 自动解压
            extraction_dir = os.path.join(local_dir, "extracted")
            os.makedirs(extraction_dir, exist_ok=True)
            
            logger.info(f"开始解压: {downloaded_file} -> {extraction_dir}")
            
            decompression_result = decompress_archive(
                archive_path=downloaded_file,
                output_dir=extraction_dir,
                progress_callback=progress_callback,
                overwrite=overwrite
            )
            
            if decompression_result.success:
                result.update({
                    "success": True,
                    "extracted_dir": extraction_dir,
                    "extracted_files": decompression_result.extracted_files
                })
                logger.info(f"解压完成: {decompression_result.extracted_files} 个文件")
            else:
                result["error"] = f"解压失败: {decompression_result.error_message}"
            
            return result
            
        except Exception as e:
            error_msg = f"下载解压过程中发生错误: {str(e)}"
            logger.error(error_msg, exc_info=True)
            result["error"] = error_msg
            return result
        
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
            patterns = [p.strip() for p in file_pattern.split(',')]
            all_files_set = set()
            
            for pattern in patterns:
                if preserve_structure:
                    # 保留目录结构，递归查找
                    search_pattern = os.path.join(local_dir, "**", pattern)
                    found_files = glob.glob(search_pattern, recursive=True)
                else:
                    # 不保留结构，只在顶层目录查找
                    search_pattern = os.path.join(local_dir, pattern)
                    found_files = glob.glob(search_pattern)
                
                all_files_set.update(found_files)
            
            # 过滤出文件（排除目录）
            files_to_upload = [f for f in all_files_set if os.path.isfile(f)]
            
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

def upload_directory_compressed(local_dir: str,
                               minio_base_path: str,
                               bucket_name: Optional[str] = None,
                               file_pattern: str = "*",
                               compression_format: Union[str, CompressionFormat] = "zip",
                               compression_level: Union[str, CompressionLevel] = "default",
                               delete_local: bool = False,
                               progress_callback: Optional[Callable[[CompressionProgress], None]] = None,
                               workflow_id: Optional[str] = None) -> Dict[str, Union[str, List[str], Dict]]:
    """
    便捷函数：压缩目录并上传到MinIO

    Args:
        local_dir: 本地目录路径
        minio_base_path: MinIO中的基础路径
        bucket_name: 存储桶名称
        file_pattern: 文件匹配模式
        compression_format: 压缩格式 ("zip", "tar.gz")，也可以是枚举类型
        compression_level: 压缩级别 ("store", "fast", "default", "maximum")，也可以是枚举类型
        delete_local: 上传成功后是否删除本地目录
        progress_callback: 压缩进度回调函数
        workflow_id: 工作流ID，用于构建任务特定的临时目录（可选）

    Returns:
        Dict: 包含压缩上传结果的字典
    """
    # 如果是字符串类型才转换；如果是枚举类型直接使用
    if isinstance(compression_format, str):
        format_enum = CompressionFormat(compression_format)
    else:
        format_enum = compression_format

    # 压缩级别字符串到枚举值的映射
    level_mapping = {
        "store": CompressionLevel.STORE,
        "fast": CompressionLevel.FAST,
        "default": CompressionLevel.DEFAULT,
        "maximum": CompressionLevel.MAXIMUM
    }

    # 如果是字符串类型才转换；如果是枚举类型直接使用
    if isinstance(compression_level, str):
        level_enum = level_mapping.get(compression_level.lower(), CompressionLevel.DEFAULT)
    else:
        level_enum = compression_level

    uploader = MinioDirectoryUploader()
    return uploader.upload_directory_compressed(
        local_dir=local_dir,
        minio_base_path=minio_base_path,
        bucket_name=bucket_name,
        file_pattern=file_pattern,
        compression_format=format_enum,
        compression_level=level_enum,
        delete_local=delete_local,
        progress_callback=progress_callback,
        workflow_id=workflow_id
    )

def upload_cropped_images_compressed(local_dir: str,
                                    workflow_id: str,
                                    delete_local: bool = False,
                                    compression_format: str = "zip",
                                    compression_level: Union[str, CompressionLevel] = "default",
                                    progress_callback: Optional[Callable[[CompressionProgress], None]] = None) -> Dict[str, Union[str, List[str], Dict]]:
    """
    专门用于上传裁剪图片目录的便捷函数（压缩版本）
    
    Args:
        local_dir: 裁剪图片本地目录路径
        workflow_id: 工作流ID，用于构建MinIO路径
        delete_local: 上传成功后是否删除本地目录
        compression_format: 压缩格式
        compression_level: 压缩级别（字符串或枚举）
        progress_callback: 压缩进度回调函数
        
    Returns:
        Dict: 包含压缩上传结果的字典
    """
    # 构建裁剪图片在MinIO中的路径
    minio_base_path = f"{workflow_id}/cropped_images"
    
    # 支持多种图片格式
    file_pattern = "*.jpg,*.jpeg,*.png,*.bmp,*.tiff,*.gif"
    
    # 如果已经是枚举类型，直接使用；否则转换为枚举
    if isinstance(compression_level, CompressionLevel):
        level_enum = compression_level
    else:
        # 压缩级别字符串到枚举值的映射
        level_mapping = {
            "store": CompressionLevel.STORE,
            "fast": CompressionLevel.FAST,
            "default": CompressionLevel.DEFAULT,
            "maximum": CompressionLevel.MAXIMUM
        }
        level_enum = level_mapping.get(compression_level.lower(), CompressionLevel.DEFAULT)
    
    return upload_directory_compressed(
        local_dir=local_dir,
        minio_base_path=minio_base_path,
        file_pattern=file_pattern,
        compression_format=compression_format,
        compression_level=level_enum,  # 传递转换后的枚举值
        delete_local=delete_local,
        progress_callback=progress_callback,
        workflow_id=workflow_id  # 传递 workflow_id 确保临时目录基于任务ID
    )

def download_and_extract_archive(minio_url: str,
                                local_dir: str,
                                auto_extract: bool = True,
                                overwrite: bool = False,
                                progress_callback: Optional[Callable[[CompressionProgress], None]] = None) -> Dict[str, Union[str, bool]]:
    """
    便捷函数：下载压缩包并自动解压
    
    Args:
        minio_url: MinIO压缩包URL
        local_dir: 本地目标目录
        auto_extract: 是否自动解压
        overwrite: 是否覆盖已存在的文件
        progress_callback: 解压进度回调函数
        
    Returns:
        Dict: 下载和解压结果
    """
    uploader = MinioDirectoryUploader()
    return uploader.download_and_extract(
        minio_url=minio_url,
        local_dir=local_dir,
        auto_extract=auto_extract,
        overwrite=overwrite,
        progress_callback=progress_callback
    )
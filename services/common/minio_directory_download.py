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
import shutil
from pathlib import Path
from typing import List, Dict, Optional, Union
from services.common.logger import get_logger
from services.common.file_service import get_file_service
from services.common.minio_url_utils import normalize_minio_url, is_minio_url
from services.common.directory_compression import decompress_archive
from services.common.temp_path_utils import get_temp_path

logger = get_logger('minio_directory_download')

def is_archive_url(url: str) -> bool:
    """
    检查URL是否指向压缩包文件
    
    Args:
        url: 文件URL
        
    Returns:
        bool: 如果是支持的压缩包格式返回True
    """
    lower_url = url.lower()
    return lower_url.endswith(('.zip', '.tar.gz', '.tar'))

class MinioDirectoryDownloader:
    """MinIO目录下载器"""
    
    def __init__(self, file_service=None):
        """
        初始化目录下载器
        
        Args:
            file_service: 文件服务实例（可选，默认使用全局实例）
        """
        self.file_service = file_service or get_file_service()
        
    def download_and_extract_archive(self,
                                   minio_url: str,
                                   local_dir: str,
                                   workflow_id: Optional[str] = None) -> Dict[str, Union[str, List[str]]]:
        """
        从MinIO下载压缩包并解压到本地目录
        
        Args:
            minio_url: MinIO压缩包URL
            local_dir: 本地目标目录（解压目标）
            
        Returns:
            Dict: 结果字典
        """
        # 参数验证
        if not minio_url or not is_minio_url(minio_url):
            raise ValueError(f"无效的MinIO URL格式: {minio_url}")

        minio_url = normalize_minio_url(minio_url)
        
        if not local_dir:
            raise ValueError("local_dir 不能为空")

        result = {
            "success": False,
            "local_dir": local_dir,
            "downloaded_files": [], # 解压后的文件列表
            "total_files": 0,
            "error": None,
            "is_archive": True
        }

        temp_archive_path = None
        try:
            logger.info(f"开始下载并解压MinIO压缩包: {minio_url}")
            
            # 确保本地目录存在
            os.makedirs(local_dir, exist_ok=True)
            
            # 生成基于工作流ID的临时文件路径
            suffix = ".zip" if minio_url.lower().endswith(".zip") else ".tar.gz"
            temp_archive_path = get_temp_path(
                workflow_id or "download", 
                suffix
            )
            
            # 下载压缩包
            try:
                logger.info(f"正在下载压缩包到临时文件: {temp_archive_path}")
                self.file_service.download_file(minio_url, temp_archive_path)
            except Exception as e:
                raise RuntimeError(f"压缩包下载失败: {e}")
                
            # 解压
            logger.info(f"正在解压到目录: {local_dir}")
            decompress_result = decompress_archive(
                archive_path=temp_archive_path,
                output_dir=local_dir,
                overwrite=True
            )
            
            if not decompress_result.success:
                raise RuntimeError(f"解压失败: {decompress_result.error_message}")
            
            # 获取解压后的文件列表
            extracted_files = []
            for root, _, files in os.walk(local_dir):
                for file in files:
                    rel_path = os.path.relpath(os.path.join(root, file), local_dir)
                    extracted_files.append(rel_path)
            
            result["success"] = True
            result["downloaded_files"] = extracted_files
            result["total_files"] = len(extracted_files)
            logger.info(f"压缩包处理完成，共解压 {len(extracted_files)} 个文件")
            
        except Exception as e:
            logger.error(f"压缩包处理过程中发生错误: {e}", exc_info=True)
            result["error"] = str(e)
        finally:
            # 清理临时压缩包
            if temp_archive_path and os.path.exists(temp_archive_path):
                try:
                    os.remove(temp_archive_path)
                    logger.debug(f"清理临时压缩包: {temp_archive_path}")
                except Exception as e:
                    logger.warning(f"清理临时压缩包失败: {e}")
                    
        return result

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
        # 参数验证 - 支持HTTP和minio://两种格式
        if not minio_url or not is_minio_url(minio_url):
            raise ValueError(
                f"无效的MinIO URL格式: {minio_url}. "
                f"支持格式: minio://bucket/path 或 http://host:port/bucket/path"
            )

        # 统一转换为minio://格式
        minio_url = normalize_minio_url(minio_url)
            
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
                                 create_structure: bool = True,
                                 auto_decompress: bool = True,
                                 workflow_id: Optional[str] = None) -> Dict[str, Union[str, List[str]]]:
    """
    便捷函数：从MinIO智能下载（准确区分文件和目录）
    
    Args:
        minio_url: MinIO文件或目录URL
        local_dir: 本地目标目录
        file_pattern: 文件匹配模式
        create_structure: 是否保留目录结构
        auto_decompress: 如果URL指向压缩包文件，是否自动解压（默认True）
        
    Returns:
        Dict: 下载结果字典，包含处理后的本地路径
    """
    downloader = MinioDirectoryDownloader()
    
    try:
        # 先规范化URL
        normalized_url = normalize_minio_url(minio_url)
        logger.info(f"[下载函数] 规范化URL: {minio_url} -> {normalized_url}")
        
        # [核心改进] 准确判断URL是文件还是目录
        url_type = classify_minio_url_type(normalized_url)
        logger.info(f"[下载函数] URL类型: {url_type}")
        
        if url_type == "file":
            # 文件：直接下载
            logger.info(f"[下载函数] 检测为文件，直接下载: {normalized_url}")
            return download_single_file(normalized_url, local_dir, auto_decompress, workflow_id)
        elif url_type == "directory":
            # 目录：下载目录内容
            logger.info(f"[下载函数] 检测为目录，下载目录内容: {normalized_url}")
            result = downloader.download_directory(
                minio_url=normalized_url,
                local_dir=local_dir,
                file_pattern=file_pattern,
                create_structure=create_structure
            )
            result["processed_path"] = local_dir
            result["is_archive_file"] = False
            return result
        else:
            # 无法确定，按目录处理（回退逻辑）
            logger.warning(f"[下载函数] 无法确定URL类型，按目录处理: {normalized_url}")
            result = downloader.download_directory(
                minio_url=normalized_url,
                local_dir=local_dir,
                file_pattern=file_pattern,
                create_structure=create_structure
            )
            result["processed_path"] = local_dir
            result["is_archive_file"] = False
            return result
            
    except Exception as e:
        logger.warning(f"[下载函数] 处理失败，回退到目录下载: {e}")
        # 回退到原有的目录下载逻辑
        return downloader.download_directory(
            minio_url=minio_url,
            local_dir=local_dir,
            file_pattern=file_pattern,
            create_structure=create_structure
        )


def classify_minio_url_type(minio_url: str) -> str:
    """
    准确分类MinIO URL类型：文件、目录或未知
    
    Args:
        minio_url: 规范化的MinIO URL (minio://bucket/path)
        
    Returns:
        str: "file", "directory", 或 "unknown"
    """
    try:
        from urllib.parse import urlparse
        
        # 解析URL
        parsed = urlparse(minio_url.replace('minio://', 'http://'))
        bucket_name = parsed.netloc
        object_path = parsed.path.lstrip('/')
        
        if not bucket_name or not object_path:
            logger.warning(f"[分类] URL解析失败: bucket={bucket_name}, path={object_path}")
            return "unknown"
        
        # [改进] 首先基于URL模式进行初步判断
        if is_archive_url(object_path):
            logger.info(f"[分类] URL包含压缩包扩展名，优先判断为文件: {object_path}")
            return "file"
        
        # 路径以/结尾通常是目录
        if object_path.endswith('/'):
            logger.info(f"[分类] URL以/结尾，判断为目录: {object_path}")
            return "directory"
        
        # 尝试通过MinIO API验证
        try:
            from services.common.file_service import get_file_service
            file_service = get_file_service()
            
            # [改进] 更简单的API调用方式
            try:
                # 首先检查是否为文件（直接获取对象信息）
                stat = file_service.minio_client.stat_object(bucket_name, object_path)
                if stat:
                    logger.info(f"[分类] MinIO API确认URL指向文件: {object_path} (大小: {stat.size} bytes)")
                    return "file"
            except Exception as stat_error:
                # 如果获取文件信息失败，继续检查是否为目录
                logger.debug(f"[分类] 获取文件信息失败: {stat_error}")
            
            # 检查是否为目录（查找前缀匹配的对象）
            objects = list(file_service.minio_client.list_objects(
                bucket_name,
                prefix=object_path.rstrip('/') + '/',
                recursive=False
            ))
            
            if objects:
                logger.info(f"[分类] MinIO API确认URL指向目录: {object_path} (包含 {len(objects)} 个对象)")
                return "directory"
            
            # 如果没有任何匹配，可能是无效路径
            logger.warning(f"[分类] MinIO中没有找到匹配的路径: {object_path}")
            return "unknown"
            
        except Exception as api_error:
            logger.warning(f"[分类] MinIO API调用失败: {api_error}")
            # API失败时，基于URL模式回退判断
            # 如果URL包含多个路径段且不包含压缩包扩展名，可能是目录
            path_parts = object_path.split('/')
            if len(path_parts) > 2 and not is_archive_url(object_path):
                logger.info(f"[分类] API失败回退，基于路径结构判断为目录: {object_path}")
                return "directory"
            else:
                logger.info(f"[分类] API失败回退，基于路径结构判断为文件: {object_path}")
                return "file"
            
    except Exception as e:
        logger.error(f"[分类] URL分类过程出错: {e}")
        return "unknown"


def download_single_file(minio_url: str, local_dir: str, auto_decompress: bool = True, workflow_id: Optional[str] = None) -> Dict[str, Union[str, List[str]]]:
    """
    下载单个文件，如果启用自动解压且文件是压缩包，则解压
    
    Args:
        minio_url: MinIO文件URL
        local_dir: 本地目录
        auto_decompress: 是否自动解压压缩包
        
    Returns:
        Dict: 下载结果字典
    """
    try:
        from services.common.file_service import get_file_service
        file_service = get_file_service()
        os.makedirs(local_dir, exist_ok=True)
        
        # 检查是否为压缩包文件
        is_archive = is_archive_url(minio_url)
        logger.info(f"[单文件下载] 文件是否为压缩包: {is_archive}")
        
        if is_archive and auto_decompress:
            # 压缩包：下载并解压
            logger.info(f"[单文件下载] 下载压缩包并解压: {minio_url}")
            downloader = MinioDirectoryDownloader()
            result = downloader.download_and_extract_archive(
                minio_url=minio_url,
                local_dir=local_dir,
                workflow_id=workflow_id
            )
            result["processed_path"] = local_dir
            result["is_archive_file"] = True
            return result
        else:
            # 普通文件：直接下载
            logger.info(f"[单文件下载] 下载普通文件: {minio_url}")
            local_file_path = file_service.download_file(minio_url, local_dir)
            
            return {
                "success": True,
                "local_dir": local_dir,
                "downloaded_files": [os.path.basename(local_file_path)],
                "total_files": 1,
                "failed_files": [],
                "error": None,
                "processed_path": local_dir,
                "is_archive_file": False
            }
        
    except Exception as e:
        logger.error(f"[单文件下载] 下载失败: {e}")
        return {
            "success": False,
            "local_dir": local_dir,
            "downloaded_files": [],
            "total_files": 0,
            "failed_files": [],
            "error": str(e),
            "processed_path": None,
            "is_archive_file": False
        }




def download_keyframes_directory(minio_url: str,
                                workflow_id: str,
                                local_dir: str,
                                auto_decompress: bool = True) -> Dict[str, Union[str, List[str]]]:
    """
    专门用于下载关键帧目录的便捷函数
    
    Args:
        minio_url: 关键帧目录的MinIO URL
        workflow_id: 工作流ID，用于验证路径（可选）
        local_dir: 本地目标目录
        auto_decompress: 是否自动解压压缩包（默认True）
        
    Returns:
        Dict: 下载结果字典
    """
    # 只下载JPEG图片文件
    file_pattern = "*.jpg"
    
    return download_directory_from_minio(
        minio_url=minio_url,
        local_dir=local_dir,
        file_pattern=file_pattern,
        create_structure=True,
        auto_decompress=auto_decompress,
        workflow_id=workflow_id
    )
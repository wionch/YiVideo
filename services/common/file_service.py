# -*- coding: utf-8 -*-
import os
import requests
import time
from minio import Minio
from urllib.parse import urlparse
from services.common.logger import get_logger

logger = get_logger('file_service')

class UnifiedFileService:
    """统一文件服务，包含MinIO客户端和文件下载功能"""

    def __init__(self, minio_host, minio_port, minio_access_key, minio_secret_key, default_bucket="yivideo", max_retries=3):
        # 从环境变量读取secure配置，默认为False
        minio_secure = os.getenv('MINIO_SECURE', 'false').lower() in ('true', '1', 'yes', 'on')
        self.minio_client = Minio(
            f"{minio_host}:{minio_port}",
            access_key=minio_access_key,
            secret_key=minio_secret_key,
            secure=minio_secure
        )
        # 保存主机和端口信息，避免使用 _base_url 属性
        self.minio_host = minio_host
        self.minio_port = minio_port
        self.default_bucket = default_bucket
        self.max_retries = max_retries

    def resolve_and_download(self, file_path: str, local_dir: str, retries: int = None) -> str:
        """
        解析文件路径并下载到本地（带重试机制）。
        如果文件是本地文件且存在，则直接返回路径。
        
        Args:
            file_path: 文件路径（HTTP URL、MinIO URL、本地路径或相对路径）
            local_dir: 本地下载目录
            retries: 重试次数（默认使用max_retries）
            
        Returns:
            str: 本地文件路径
            
        Raises:
            FileNotFoundError: 文件下载失败或不存在
        """
        if retries is None:
            retries = self.max_retries
            
        # 检查是否是已存在的本地文件路径
        if os.path.exists(file_path):
            logger.info(f"文件已存在本地: {file_path}")
            return file_path
        
        # 尝试下载文件，带重试机制
        last_error = None
        for attempt in range(retries):
            try:
                if file_path.startswith(('http://', 'https://')):
                    return self._download_http_file(file_path, local_dir)
                elif file_path.startswith('minio://'):
                    return self._download_minio_file(file_path, local_dir)
                else:
                    # 默认为相对路径，相对于默认bucket
                    minio_url = f"minio://{self.default_bucket}/{file_path}"
                    return self._download_minio_file(minio_url, local_dir)
            except Exception as e:
                last_error = e
                if attempt < retries - 1:
                    wait_time = 2 ** attempt  # 指数退避
                    logger.warning(f"文件下载失败 (尝试 {attempt + 1}/{retries}): {file_path}, 错误: {e}, {wait_time}秒后重试...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"文件下载失败，已达最大重试次数 ({retries}): {file_path}, 错误: {e}")
        
        # 所有重试都失败
        raise FileNotFoundError(f"文件下载失败: {file_path}, 最后错误: {last_error}")

    def _download_http_file(self, url: str, local_dir: str) -> str:
        """下载HTTP文件"""
        os.makedirs(local_dir, exist_ok=True)
        file_name = os.path.basename(urlparse(url).path)
        local_file_path = os.path.join(local_dir, file_name)
        
        logger.info(f"开始下载HTTP文件: {url}")
        with requests.get(url, stream=True, timeout=300) as r:
            r.raise_for_status()
            with open(local_file_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        
        logger.info(f"HTTP文件下载成功: {url} -> {local_file_path}")
        return local_file_path

    def _download_minio_file(self, minio_url: str, local_dir: str) -> str:
        """
        下载MinIO文件.
        minio_url格式: minio://bucket_name/object_name
        """
        os.makedirs(local_dir, exist_ok=True)
        parsed_url = urlparse(minio_url)
        bucket_name = parsed_url.netloc
        object_name = parsed_url.path.lstrip('/')
        
        file_name = os.path.basename(object_name)
        local_file_path = os.path.join(local_dir, file_name)

        logger.info(f"开始下载MinIO文件: {minio_url}")
        self.minio_client.fget_object(bucket_name, object_name, local_file_path)
        logger.info(f"MinIO文件下载成功: {minio_url} -> {local_file_path}")
        return local_file_path

    def upload_to_minio(self, local_file_path: str, object_name: str, bucket_name: str = None) -> str:
        """
        上传文件到MinIO
        
        Args:
            local_file_path: 本地文件路径
            object_name: MinIO对象名称（路径）
            bucket_name: 存储桶名称（默认使用default_bucket）
            
        Returns:
            str: MinIO文件URL
            
        Raises:
            FileNotFoundError: 本地文件不存在
        """
        if not os.path.exists(local_file_path):
            raise FileNotFoundError(f"本地文件不存在: {local_file_path}")
        
        if bucket_name is None:
            bucket_name = self.default_bucket
        
        # logger.info(f"开始上传文件到MinIO: {local_file_path} -> {bucket_name}/{object_name}")
        
        self.minio_client.fput_object(bucket_name, object_name, local_file_path)
        
        # 构建MinIO URL - 使用保存的主机和端口信息
        minio_endpoint = f"{self.minio_host}:{self.minio_port}"
        minio_url = f"http://{minio_endpoint}/{bucket_name}/{object_name}"
        
        logger.info(f"文件上传成功: {minio_url}")
        return minio_url


# 全局文件服务实例缓存
_file_service_instance = None

def get_file_service() -> UnifiedFileService:
    """
    获取文件服务单例实例（工厂函数）
    
    从环境变量读取MinIO配置，创建或返回已有的UnifiedFileService实例。
    
    Returns:
        UnifiedFileService: 文件服务实例
    """
    global _file_service_instance
    
    if _file_service_instance is None:
        minio_host = os.getenv('MINIO_HOST', 'minio')
        minio_port = os.getenv('MINIO_PORT', '9000')
        minio_access_key = os.getenv('MINIO_ACCESS_KEY', 'minioadmin')
        minio_secret_key = os.getenv('MINIO_SECRET_KEY', 'minioadmin')
        default_bucket = os.getenv('MINIO_DEFAULT_BUCKET', 'yivideo')
        max_retries = int(os.getenv('FILE_DOWNLOAD_MAX_RETRIES', '3'))
        
        logger.info(f"初始化文件服务: {minio_host}:{minio_port}, bucket: {default_bucket}, 重试次数: {max_retries}")
        _file_service_instance = UnifiedFileService(
            minio_host=minio_host,
            minio_port=minio_port,
            minio_access_key=minio_access_key,
            minio_secret_key=minio_secret_key,
            default_bucket=default_bucket,
            max_retries=max_retries
        )
    
    return _file_service_instance

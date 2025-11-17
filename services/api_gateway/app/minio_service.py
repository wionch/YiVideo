# services/api_gateway/app/minio_service.py
# -*- coding: utf-8 -*-

"""
MinIO文件服务模块。

提供统一的MinIO文件操作接口，包括上传、下载、删除、列出等功能。
"""

import os
import tempfile
import mimetypes
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from minio import Minio
from minio.error import S3Error

from services.common.logger import get_logger

logger = get_logger('minio_service')


class MinIOFileService:
    """MinIO文件服务类"""
    
    def __init__(self):
        """初始化MinIO客户端"""
        # 从环境变量读取配置
        self.host = os.environ.get('MINIO_HOST')
        self.port = os.environ.get('MINIO_PORT')
        self.access_key = os.environ.get('MINIO_ACCESS_KEY')
        self.secret_key = os.environ.get('MINIO_SECRET_KEY')
        
        # 验证配置
        if not all([self.host, self.port, self.access_key, self.secret_key]):
            raise ValueError("MinIO配置不完整，请检查环境变量："
                           "MINIO_HOST, MINIO_PORT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY")
        
        # 初始化MinIO客户端
        self.client = Minio(
            f"{self.host}:{self.port}",
            access_key=self.access_key,
            secret_key=self.secret_key,
            secure=False  # HTTP模式
        )
        
        self.default_bucket = "yivideo"
        logger.info(f"MinIO服务初始化完成: {self.host}:{self.port}, 默认桶: {self.default_bucket}")
    
    def upload_file(self, file_data: bytes, file_path: str, bucket: Optional[str] = None) -> Dict:
        """
        上传文件到MinIO（传统方式，使用临时文件）
        
        Args:
            file_data: 文件二进制数据
            file_path: 文件在MinIO中的路径
            bucket: 文件桶，默认使用yivideo
            
        Returns:
            Dict: 包含文件信息的字典
        """
        bucket = bucket or self.default_bucket
        
        try:
            # 创建临时文件
            temp_file = tempfile.NamedTemporaryFile(delete=False)
            temp_file.write(file_data)
            temp_file.close()
            
            # 确保桶存在
            if not self._bucket_exists(bucket):
                self.client.make_bucket(bucket)
                logger.info(f"创建新桶: {bucket}")
            
            # 上传文件
            self.client.fput_object(bucket, file_path, temp_file.name)
            
            # 获取下载链接（24小时有效期）
            download_url = self.client.presigned_get_object(
                bucket, file_path, expires=timedelta(hours=24)
            )
            
            result = {
                "file_path": file_path,
                "bucket": bucket,
                "download_url": download_url,
                "size": len(file_data),
                "uploaded_at": datetime.utcnow().isoformat() + 'Z',
                "content_type": mimetypes.guess_type(file_path)[0] or 'application/octet-stream'
            }
            
            logger.info(f"文件上传成功: {bucket}/{file_path}, 大小: {len(file_data)} bytes")
            return result
            
        except Exception as e:
            logger.error(f"文件上传失败: {bucket}/{file_path}, 错误: {e}")
            raise
        finally:
            # 清理临时文件
            if 'temp_file' in locals():
                try:
                    os.unlink(temp_file.name)
                except:
                    pass
    
    def upload_file_stream(self, file_obj, file_path: str, bucket: Optional[str] = None) -> Dict:
        """
        流式上传文件到MinIO（优化版本，避免临时文件）
        
        Args:
            file_obj: 文件对象（UploadFile或类似对象）
            file_path: 文件在MinIO中的路径
            bucket: 文件桶，默认使用yivideo
            
        Returns:
            Dict: 包含文件信息的字典
        """
        bucket = bucket or self.default_bucket
        
        try:
            # 确保桶存在
            if not self._bucket_exists(bucket):
                self.client.make_bucket(bucket)
                logger.info(f"创建新桶: {bucket}")
            
            # 获取文件信息
            content_type = getattr(file_obj, 'content_type', None) or mimetypes.guess_type(file_path)[0] or 'application/octet-stream'
            
            # 使用流式上传，避免临时文件
            file_size = getattr(file_obj, 'size', None)
            if file_size is None:
                # 如果文件对象没有size属性，尝试获取
                file_obj.file.seek(0, 2)  # 移动到文件末尾
                file_size = file_obj.file.tell()  # 获取文件大小
                file_obj.file.seek(0)  # 重置到文件开头
            
            # 流式上传到MinIO
            result = self.client.put_object(
                bucket_name=bucket,
                object_name=file_path,
                data=file_obj.file,  # 直接传递文件对象
                length=file_size,
                content_type=content_type,
                part_size=10*1024*1024  # 10MB分块大小
            )
            
            # 获取下载链接（24小时有效期）
            download_url = self.client.presigned_get_object(
                bucket, file_path, expires=timedelta(hours=24)
            )
            
            response = {
                "file_path": file_path,
                "bucket": bucket,
                "download_url": download_url,
                "size": file_size,
                "uploaded_at": datetime.utcnow().isoformat() + 'Z',
                "content_type": content_type
            }
            
            logger.info(f"文件流式上传成功: {bucket}/{file_path}, 大小: {file_size} bytes")
            return response
            
        except Exception as e:
            logger.error(f"文件流式上传失败: {bucket}/{file_path}, 错误: {e}")
            raise
    
    def download_file(self, file_path: str, bucket: Optional[str] = None) -> bytes:
        """
        从MinIO下载文件
        
        Args:
            file_path: 文件在MinIO中的路径
            bucket: 文件桶
            
        Returns:
            bytes: 文件二进制数据
        """
        bucket = bucket or self.default_bucket
        
        try:
            # 创建临时文件
            temp_file = tempfile.NamedTemporaryFile(delete=False)
            temp_file.close()
            
            # 下载文件
            self.client.fget_object(bucket, file_path, temp_file.name)
            
            # 读取文件数据
            with open(temp_file.name, 'rb') as f:
                file_data = f.read()
            
            logger.info(f"文件下载成功: {bucket}/{file_path}, 大小: {len(file_data)} bytes")
            return file_data
            
        except S3Error as e:
            logger.error(f"文件下载失败 (S3Error): {bucket}/{file_path}, 错误: {e}")
            raise
        except Exception as e:
            logger.error(f"文件下载失败: {bucket}/{file_path}, 错误: {e}")
            raise
        finally:
            # 清理临时文件
            if 'temp_file' in locals():
                try:
                    os.unlink(temp_file.name)
                except:
                    pass
    
    def delete_file(self, file_path: str, bucket: Optional[str] = None) -> bool:
        """
        删除MinIO中的文件
        
        Args:
            file_path: 文件在MinIO中的路径
            bucket: 文件桶
            
        Returns:
            bool: 删除是否成功
        """
        bucket = bucket or self.default_bucket
        
        try:
            self.client.remove_object(bucket, file_path)
            logger.info(f"文件删除成功: {bucket}/{file_path}")
            return True
        except S3Error as e:
            logger.error(f"文件删除失败 (S3Error): {bucket}/{file_path}, 错误: {e}")
            return False
        except Exception as e:
            logger.error(f"文件删除失败: {bucket}/{file_path}, 错误: {e}")
            return False
    
    def list_files(self, prefix: str = "", bucket: Optional[str] = None, recursive: bool = True) -> List[Dict]:
        """
        列出MinIO中的文件
        
        Args:
            prefix: 文件路径前缀
            bucket: 文件桶
            recursive: 是否递归列出子目录
            
        Returns:
            List[Dict]: 文件信息列表
        """
        bucket = bucket or self.default_bucket
        
        files = []
        try:
            objects = self.client.list_objects(
                bucket, 
                prefix=prefix, 
                recursive=recursive
            )
            
            for obj in objects:
                file_info = {
                    "file_path": obj.object_name,
                    "size": obj.size,
                    "last_modified": obj.last_modified.isoformat() if obj.last_modified else None,
                    "etag": obj.etag,
                    "content_type": obj.content_type
                }
                files.append(file_info)
            
            logger.info(f"文件列表获取成功: {bucket}/{prefix}, 找到 {len(files)} 个文件")
            return files
            
        except S3Error as e:
            logger.error(f"文件列表获取失败 (S3Error): {bucket}/{prefix}, 错误: {e}")
            return []
        except Exception as e:
            logger.error(f"文件列表获取失败: {bucket}/{prefix}, 错误: {e}")
            return []
    
    def get_presigned_url(self, file_path: str, bucket: Optional[str] = None, 
                         expires: timedelta = timedelta(hours=24)) -> str:
        """
        获取文件的预签名URL（用于直接访问）
        
        Args:
            file_path: 文件在MinIO中的路径
            bucket: 文件桶
            expires: 链接有效期
            
        Returns:
            str: 预签名URL
        """
        bucket = bucket or self.default_bucket
        
        try:
            url = self.client.presigned_get_object(bucket, file_path, expires=expires)
            logger.info(f"获取预签名URL成功: {bucket}/{file_path}")
            return url
        except Exception as e:
            logger.error(f"获取预签名URL失败: {bucket}/{file_path}, 错误: {e}")
            raise
    
    def file_exists(self, file_path: str, bucket: Optional[str] = None) -> bool:
        """
        检查文件是否存在
        
        Args:
            file_path: 文件在MinIO中的路径
            bucket: 文件桶
            
        Returns:
            bool: 文件是否存在
        """
        bucket = bucket or self.default_bucket
        
        try:
            self.client.stat_object(bucket, file_path)
            return True
        except S3Error:
            return False
        except Exception as e:
            logger.error(f"检查文件存在性失败: {bucket}/{file_path}, 错误: {e}")
            return False
    
    def _bucket_exists(self, bucket: str) -> bool:
        """检查桶是否存在"""
        try:
            return self.client.bucket_exists(bucket)
        except Exception as e:
            logger.error(f"检查桶存在性失败: {bucket}, 错误: {e}")
            return False
    
    def create_directory_structure(self, base_path: str, bucket: Optional[str] = None) -> bool:
        """
        创建目录结构（在MinIO中，目录是通过文件路径模拟的）
        
        Args:
            base_path: 基础路径
            bucket: 文件桶
            
        Returns:
            bool: 是否成功
        """
        bucket = bucket or self.default_bucket
        
        try:
            # 在MinIO中，创建目录实际上是通过创建一个0字节的标记文件
            # 这里我们不需要显式创建目录，因为文件上传时会自动创建
            logger.info(f"目录结构创建（通过路径模拟）: {bucket}/{base_path}")
            return True
        except Exception as e:
            logger.error(f"创建目录结构失败: {bucket}/{base_path}, 错误: {e}")
            return False
    
    def cleanup_temp_files(self, temp_files: List[str]):
        """清理临时文件"""
        for temp_file in temp_files:
            try:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)
            except Exception as e:
                logger.warning(f"清理临时文件失败: {temp_file}, 错误: {e}")


# 单例模式，确保整个应用中只有一个MinIO客户端实例
_minio_service_instance = None

def get_minio_service() -> MinIOFileService:
    """获取MinIO服务实例"""
    global _minio_service_instance
    if _minio_service_instance is None:
        try:
            _minio_service_instance = MinIOFileService()
        except Exception as e:
            logger.error(f"MinIO服务初始化失败: {e}")
            raise
    return _minio_service_instance
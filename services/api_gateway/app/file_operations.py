# services/api_gateway/app/file_operations.py
# -*- coding: utf-8 -*-

"""
文件操作API端点。

提供MinIO文件上传、下载、删除、列出等操作的API接口。
"""

import mimetypes
import os
import shutil
from typing import Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from fastapi.responses import Response
from pydantic import ValidationError

from services.common.logger import get_logger
from .minio_service import get_minio_service
from .single_task_models import (
    FileUploadRequest, FileUploadResponse, FileOperationResponse,
    FileListResponse, FileListItem, ErrorResponse
)

logger = get_logger('file_operations')

# 创建路由器
router = APIRouter(prefix="/v1/files", tags=["File Operations"])


@router.delete("/directories", response_model=FileOperationResponse)
async def delete_directory(
    directory_path: str = Query(..., description="要删除的本地目录路径")
):
    """
    删除本地文件系统中的目录及其所有内容

    Args:
        directory_path: 要删除的本地目录路径

    Returns:
        FileOperationResponse: 删除结果
    """
    logger.info(f"开始删除本地目录: {directory_path}")

    try:
        # 验证目录路径参数
        if not directory_path:
            raise HTTPException(status_code=400, detail="directory_path不能为空")

        # 安全检查：防止路径遍历攻击（限制在 /share/ 目录下）
        if ".." in directory_path:
            logger.warning(f"检测到不安全的目录路径（路径遍历攻击）: {directory_path}")
            raise HTTPException(status_code=400, detail="无效的目录路径：禁止路径遍历攻击")

        # 限制只能删除 /share/ 目录下的路径
        if not (directory_path.startswith("/share/") or directory_path.startswith("share/")):
            logger.warning(f"检测到越权路径访问: {directory_path}")
            raise HTTPException(status_code=400, detail="无效的目录路径：只能删除 /share/ 目录下的文件")

        # 检查目录是否存在
        if not os.path.exists(directory_path):
            logger.info(f"目录不存在，视为删除成功: {directory_path}")
            return FileOperationResponse(
                success=True,
                message=f"目录不存在，删除操作已幂等完成: {directory_path}",
                file_path=directory_path
            )

        # 检查是否为目录
        if not os.path.isdir(directory_path):
            logger.warning(f"路径不是目录: {directory_path}")
            raise HTTPException(status_code=400, detail=f"路径不是目录: {directory_path}")

        # 尝试删除目录及其内容
        try:
            shutil.rmtree(directory_path)
            logger.info(f"目录删除成功: {directory_path}")

            return FileOperationResponse(
                success=True,
                message=f"目录删除成功: {directory_path}",
                file_path=directory_path
            )
        except PermissionError as e:
            logger.error(f"权限不足，无法删除目录: {directory_path}, 错误: {e}")
            raise HTTPException(status_code=403, detail=f"权限不足，无法删除目录: {directory_path}")
        except Exception as e:
            logger.error(f"删除目录时发生错误: {directory_path}, 错误: {e}")
            raise HTTPException(status_code=500, detail=f"删除目录失败: {str(e)}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"处理删除目录请求时发生未知错误: {e}")
        raise HTTPException(status_code=500, detail=f"处理请求时发生错误: {str(e)}")


@router.delete("/{file_path:path}", response_model=FileOperationResponse)
async def delete_file(
    file_path: str,
    bucket: Optional[str] = Query("yivideo", description="文件桶名称")
):
    """
    删除MinIO中的文件

    Args:
        file_path: 文件在MinIO中的路径
        bucket: 文件桶名称（默认yivideo）

    Returns:
        FileOperationResponse: 删除结果
    """
    logger.info(f"开始删除文件: {file_path}, 桶: {bucket}")

    try:
        # 验证文件路径
        if ".." in file_path or file_path.startswith("/"):
            raise HTTPException(status_code=400, detail="无效的文件路径")

        # 获取MinIO服务
        minio_service = get_minio_service()

        # 删除文件
        success = minio_service.delete_file(file_path, bucket)

        if success:
            message = f"文件删除成功: {file_path}"
            logger.info(message)
            return FileOperationResponse(
                success=True,
                message=message,
                file_path=file_path
            )
        else:
            message = f"文件删除失败: {file_path}"
            logger.warning(message)
            return FileOperationResponse(
                success=False,
                message=message,
                file_path=file_path
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"文件删除失败: {e}")
        raise HTTPException(status_code=500, detail=f"文件删除失败: {str(e)}")


@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    file_path: str = Query(..., description="文件在MinIO中的路径"),
    bucket: Optional[str] = Query("yivideo", description="文件桶名称")
):
    """
    上传文件到MinIO（流式上传优化版本）
    
    Args:
        file: 要上传的文件
        file_path: 文件在MinIO中的路径
        bucket: 文件桶名称（默认yivideo）
        
    Returns:
        FileUploadResponse: 上传结果
    """
    logger.info(f"开始流式上传文件: {file_path}, 桶: {bucket}, 文件大小: {file.size} bytes")
    
    try:
        # 验证请求参数
        if not file_path:
            raise HTTPException(status_code=400, detail="file_path不能为空")
        
        # 验证文件名安全性（防止路径遍历攻击）
        if ".." in file_path or file_path.startswith("/"):
            raise HTTPException(status_code=400, detail="无效的文件路径")
        
        # 验证文件对象
        if not file.filename:
            raise HTTPException(status_code=400, detail="文件名为空")
        
        if not file.size or file.size == 0:
            raise HTTPException(status_code=400, detail="文件大小为0")
        
        # 获取MinIO服务
        minio_service = get_minio_service()
        
        # 使用流式上传（优化版本）
        result = minio_service.upload_file_stream(file, file_path, bucket)
        
        logger.info(f"文件流式上传成功: {file_path}, 实际大小: {result['size']} bytes")
        return FileUploadResponse(**result)
        
    except ValidationError as e:
        logger.error(f"参数验证失败: {e}")
        raise HTTPException(status_code=400, detail=f"参数验证失败: {str(e)}")
    except Exception as e:
        logger.error(f"文件上传失败: {e}")
        raise HTTPException(status_code=500, detail=f"文件上传失败: {str(e)}")


@router.get("/download/{file_path:path}")
async def download_file(
    file_path: str,
    bucket: Optional[str] = Query("yivideo", description="文件桶名称")
):
    """
    从MinIO下载文件
    
    Args:
        file_path: 文件在MinIO中的路径
        bucket: 文件桶名称（默认yivideo）
        
    Returns:
        文件二进制数据
    """
    logger.info(f"开始下载文件: {file_path}, 桶: {bucket}")
    
    try:
        # 验证文件路径
        if ".." in file_path or file_path.startswith("/"):
            raise HTTPException(status_code=400, detail="无效的文件路径")
        
        # 获取MinIO服务
        minio_service = get_minio_service()
        
        # 下载文件
        file_data = minio_service.download_file(file_path, bucket)
        
        # 推断MIME类型
        content_type = mimetypes.guess_type(file_path)[0] or 'application/octet-stream'
        
        logger.info(f"文件下载成功: {file_path}, 大小: {len(file_data)} bytes")
        
        # 返回文件数据
        return Response(
            content=file_data,
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{file_path.split("/")[-1]}"'
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"文件下载失败: {e}")
        raise HTTPException(status_code=500, detail=f"文件下载失败: {str(e)}")


def get_file_operations_router():
    """获取文件操作路由器"""
    return router
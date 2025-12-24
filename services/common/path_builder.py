"""
统一路径构建工具模块

提供标准化的文件路径生成和解析功能,支持本地存储和 MinIO 对象存储。

路径规范:
- 节点输出: /share/workflows/{task_id}/nodes/{node_name}/{file_type}/{filename}
- 临时文件: /share/workflows/{task_id}/temp/{node_name}/{filename}
- MinIO 路径: {task_id}/nodes/{node_name}/{file_type}/{filename}
"""

import os
import re
from pathlib import Path
from typing import Optional


# 标准文件类型目录映射
FILE_TYPE_DIRS = {
    "audio": "audio",
    "video": "video",
    "image": "images",
    "images": "images",
    "subtitle": "subtitles",
    "subtitles": "subtitles",
    "data": "data",
    "json": "data",
    "archive": "archives",
    "archives": "archives",
}

# 本地存储根路径
LOCAL_STORAGE_ROOT = "/share/workflows"


def build_node_output_path(
    task_id: str,
    node_name: str,
    file_type: str,
    filename: str,
    base_path: Optional[str] = None,
) -> str:
    """
    构建节点输出文件的标准路径

    Args:
        task_id: 任务 ID
        node_name: 节点名称 (如 'ffmpeg.extract_audio')
        file_type: 文件类型 (audio/video/images/subtitles/data/archives)
        filename: 文件名
        base_path: 可选的基础路径,默认为 /share/workflows

    Returns:
        完整的本地文件路径

    Example:
        >>> build_node_output_path("task-001", "ffmpeg.extract_audio", "audio", "demo.wav")
        '/share/workflows/task-001/nodes/ffmpeg.extract_audio/audio/demo.wav'
    """
    if base_path is None:
        base_path = LOCAL_STORAGE_ROOT

    # 标准化文件类型目录名
    type_dir = FILE_TYPE_DIRS.get(file_type.lower(), file_type)

    path = os.path.join(
        base_path,
        task_id,
        "nodes",
        node_name,
        type_dir,
        filename,
    )

    return path


def build_temp_path(
    task_id: str,
    node_name: str,
    filename: str,
    base_path: Optional[str] = None,
) -> str:
    """
    构建临时文件路径

    Args:
        task_id: 任务 ID
        node_name: 节点名称
        filename: 文件名
        base_path: 可选的基础路径,默认为 /share/workflows

    Returns:
        临时文件路径

    Example:
        >>> build_temp_path("task-001", "ffmpeg.extract_audio", "temp_audio.wav")
        '/share/workflows/task-001/temp/ffmpeg.extract_audio/temp_audio.wav'
    """
    if base_path is None:
        base_path = LOCAL_STORAGE_ROOT

    path = os.path.join(
        base_path,
        task_id,
        "temp",
        node_name,
        filename,
    )

    return path


def build_minio_path(
    task_id: str,
    node_name: str,
    file_type: str,
    filename: str,
) -> str:
    """
    构建 MinIO 对象存储路径 (不包含 bucket 名称)

    Args:
        task_id: 任务 ID
        node_name: 节点名称
        file_type: 文件类型
        filename: 文件名

    Returns:
        MinIO 对象路径

    Example:
        >>> build_minio_path("task-001", "ffmpeg.extract_audio", "audio", "demo.wav")
        'task-001/nodes/ffmpeg.extract_audio/audio/demo.wav'
    """
    # 标准化文件类型目录名
    type_dir = FILE_TYPE_DIRS.get(file_type.lower(), file_type)

    # MinIO 路径使用正斜杠,不包含根路径
    path = f"{task_id}/nodes/{node_name}/{type_dir}/{filename}"

    return path


def build_minio_temp_path(
    task_id: str,
    node_name: str,
    filename: str,
) -> str:
    """
    构建 MinIO 临时文件路径

    Args:
        task_id: 任务 ID
        node_name: 节点名称
        filename: 文件名

    Returns:
        MinIO 临时文件路径

    Example:
        >>> build_minio_temp_path("task-001", "ffmpeg.extract_audio", "temp.wav")
        'task-001/temp/ffmpeg.extract_audio/temp.wav'
    """
    path = f"{task_id}/temp/{node_name}/{filename}"
    return path


def parse_node_path(path: str) -> dict[str, Optional[str]]:
    """
    解析路径,提取节点名称、文件类型等信息

    支持新旧两种路径格式:
    - 新格式: /share/workflows/{task_id}/nodes/{node_name}/{file_type}/{filename}
    - 旧格式: /share/workflows/{task_id}/{file_type}/{filename}

    Args:
        path: 文件路径

    Returns:
        包含以下键的字典:
        - task_id: 任务 ID
        - node_name: 节点名称 (旧格式为 None)
        - file_type: 文件类型
        - filename: 文件名
        - is_temp: 是否为临时文件
        - is_legacy: 是否为旧格式路径

    Example:
        >>> parse_node_path("/share/workflows/task-001/nodes/ffmpeg.extract_audio/audio/demo.wav")
        {
            'task_id': 'task-001',
            'node_name': 'ffmpeg.extract_audio',
            'file_type': 'audio',
            'filename': 'demo.wav',
            'is_temp': False,
            'is_legacy': False
        }
    """
    # 标准化路径分隔符
    path = path.replace("\\", "/")

    # 新格式: /share/workflows/{task_id}/nodes/{node_name}/{file_type}/{filename}
    new_pattern = r"/share/workflows/([^/]+)/nodes/([^/]+)/([^/]+)/(.+)"
    match = re.match(new_pattern, path)

    if match:
        return {
            "task_id": match.group(1),
            "node_name": match.group(2),
            "file_type": match.group(3),
            "filename": match.group(4),
            "is_temp": False,
            "is_legacy": False,
        }

    # 临时文件格式: /share/workflows/{task_id}/temp/{node_name}/{filename}
    temp_pattern = r"/share/workflows/([^/]+)/temp/([^/]+)/(.+)"
    match = re.match(temp_pattern, path)

    if match:
        return {
            "task_id": match.group(1),
            "node_name": match.group(2),
            "file_type": "temp",
            "filename": match.group(3),
            "is_temp": True,
            "is_legacy": False,
        }

    # 旧格式: /share/workflows/{task_id}/{file_type}/{filename}
    legacy_pattern = r"/share/workflows/([^/]+)/([^/]+)/(.+)"
    match = re.match(legacy_pattern, path)

    if match:
        return {
            "task_id": match.group(1),
            "node_name": None,
            "file_type": match.group(2),
            "filename": match.group(3),
            "is_temp": False,
            "is_legacy": True,
        }

    # 无法解析的路径
    return {
        "task_id": None,
        "node_name": None,
        "file_type": None,
        "filename": os.path.basename(path),
        "is_temp": False,
        "is_legacy": False,
    }


def ensure_directory(path: str) -> None:
    """
    确保目录存在,如不存在则创建

    Args:
        path: 文件路径或目录路径
    """
    directory = os.path.dirname(path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)


def get_relative_path(full_path: str, base_path: Optional[str] = None) -> str:
    """
    获取相对于基础路径的相对路径

    Args:
        full_path: 完整路径
        base_path: 基础路径,默认为 /share/workflows

    Returns:
        相对路径

    Example:
        >>> get_relative_path("/share/workflows/task-001/nodes/ffmpeg/audio/demo.wav")
        'task-001/nodes/ffmpeg/audio/demo.wav'
    """
    if base_path is None:
        base_path = LOCAL_STORAGE_ROOT

    # 标准化路径
    full_path = os.path.normpath(full_path)
    base_path = os.path.normpath(base_path)

    # 计算相对路径
    try:
        rel_path = os.path.relpath(full_path, base_path)
        return rel_path
    except ValueError:
        # 不同驱动器或无法计算相对路径
        return full_path


def convert_local_to_minio_path(local_path: str) -> str:
    """
    将本地路径转换为 MinIO 路径

    Args:
        local_path: 本地文件路径

    Returns:
        MinIO 对象路径

    Example:
        >>> convert_local_to_minio_path("/share/workflows/task-001/nodes/ffmpeg/audio/demo.wav")
        'task-001/nodes/ffmpeg/audio/demo.wav'
    """
    # 解析路径信息
    info = parse_node_path(local_path)

    if info["is_legacy"]:
        # 旧格式路径: 直接使用相对路径
        return get_relative_path(local_path)

    if info["is_temp"]:
        # 临时文件路径
        return build_minio_temp_path(
            info["task_id"],
            info["node_name"],
            info["filename"],
        )

    # 新格式路径
    return build_minio_path(
        info["task_id"],
        info["node_name"],
        info["file_type"],
        info["filename"],
    )

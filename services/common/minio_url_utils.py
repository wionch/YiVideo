"""
MinIO URL格式处理工具模块

提供HTTP和minio://格式之间的转换功能，支持智能URL规范化。

作者: Claude Code
创建时间: 2025-11-25
"""

import re
from typing import Tuple
from urllib.parse import urlparse, urlunparse
from services.common.config_loader import get_config


def _get_minio_config() -> Tuple[str, int]:
    """
    从配置文件读取MinIO服务器信息

    Returns:
        (host, port) 元组
    """
    config = get_config()
    minio_config = config.get('minio', {})
    host = minio_config.get('host', 'minio')
    port = minio_config.get('port', 9000)
    return host, port


def http_to_minio_url(http_url: str) -> str:
    """
    将HTTP格式的MinIO URL转换为minio://格式

    Args:
        http_url: HTTP格式的URL，例如 "http://minio:9000/bucket/path/file.txt"

    Returns:
        minio://格式的URL，例如 "minio://bucket/path/file.txt"

    Raises:
        ValueError: URL格式不正确或缺少必要部分

    Examples:
        >>> http_to_minio_url("http://minio:9000/yivideo/task/file.mp4")
        'minio://yivideo/task/file.mp4'
    """
    if not http_url:
        raise ValueError("HTTP URL不能为空")

    # 解析URL
    parsed = urlparse(http_url)

    # 验证协议
    if parsed.scheme not in ('http', 'https'):
        raise ValueError(f"不支持的协议: {parsed.scheme}. 期望 http 或 https")

    # 提取路径部分
    path = parsed.path.strip('/')
    if not path:
        raise ValueError(f"HTTP URL中缺少路径部分: {http_url}")

    # 分割路径: bucket/object_path
    path_parts = path.split('/', 1)
    if len(path_parts) < 1:
        raise ValueError(f"无法从HTTP URL中提取bucket: {http_url}")

    bucket_name = path_parts[0]
    object_path = path_parts[1] if len(path_parts) > 1 else ''

    # 构造minio URL
    minio_url = f"minio://{bucket_name}/{object_path}" if object_path else f"minio://{bucket_name}"
    return minio_url


def minio_to_http_url(minio_url: str, host: str = None, port: int = None) -> str:
    """
    将minio://格式的URL转换为HTTP格式

    Args:
        minio_url: minio://格式的URL
        host: MinIO服务器主机名（默认从配置读取）
        port: MinIO服务器端口（默认从配置读取）

    Returns:
        HTTP格式的URL

    Raises:
        ValueError: URL格式不正确

    Examples:
        >>> minio_to_http_url("minio://yivideo/task/file.mp4")
        'http://minio:9000/yivideo/task/file.mp4'
    """
    if not minio_url:
        raise ValueError("MinIO URL不能为空")

    # 验证格式
    if not minio_url.startswith('minio://'):
        raise ValueError(f"不是有效的minio://格式: {minio_url}")

    # 提取bucket和路径
    path = minio_url[len('minio://'):]
    if not path:
        raise ValueError(f"MinIO URL中缺少bucket: {minio_url}")

    # 获取MinIO配置
    if host is None or port is None:
        config_host, config_port = _get_minio_config()
        host = host or config_host
        port = port or config_port

    # 构造HTTP URL
    http_url = f"http://{host}:{port}/{path}"
    return http_url


def normalize_minio_url(url: str) -> str:
    """
    智能规范化MinIO URL为minio://格式

    支持的输入格式:
    - HTTP/HTTPS URL: http://minio:9000/bucket/path
    - minio URL: minio://bucket/path
    - 相对路径: bucket/path (自动添加minio://前缀)

    Args:
        url: 任意格式的MinIO URL或路径

    Returns:
        规范化的minio://格式URL

    Raises:
        ValueError: URL格式无法识别或不正确

    Examples:
        >>> normalize_minio_url("http://minio:9000/yivideo/task/file.mp4")
        'minio://yivideo/task/file.mp4'

        >>> normalize_minio_url("minio://yivideo/task/file.mp4")
        'minio://yivideo/task/file.mp4'

        >>> normalize_minio_url("yivideo/task/file.mp4")
        'minio://yivideo/task/file.mp4'
    """
    if not url:
        raise ValueError("URL不能为空")

    url = url.strip()

    # 已经是minio://格式，直接返回
    if url.startswith('minio://'):
        return url

    # HTTP/HTTPS格式，转换
    if url.startswith('http://') or url.startswith('https://'):
        return http_to_minio_url(url)

    # 相对路径，添加minio://前缀
    # 移除开头的斜杠
    url = url.lstrip('/')
    if not url:
        raise ValueError("URL路径为空")
    
    # 规范化路径分隔符，替换多个斜杠为单个
    while '//' in url:
        url = url.replace('//', '/')

    return f"minio://{url}"


def is_minio_url(url: str) -> bool:
    """
    判断是否为有效的MinIO URL（支持http和minio://两种格式）

    检查逻辑:
    1. minio://格式: 直接判定为MinIO URL
    2. http/https格式: 检查主机名是否为MinIO服务器

    Args:
        url: 待检查的URL字符串

    Returns:
        True表示是有效的MinIO URL

    Examples:
        >>> is_minio_url("http://minio:9000/yivideo/file.mp4")
        True

        >>> is_minio_url("minio://yivideo/file.mp4")
        True

        >>> is_minio_url("https://example.com/file.mp4")
        False
    """
    if not url or not isinstance(url, str):
        return False

    url = url.strip()

    # minio://格式
    if url.startswith('minio://'):
        return True

    # http/https格式，检查是否为MinIO服务器
    if url.startswith('http://') or url.startswith('https://'):
        parsed = urlparse(url)
        minio_host, minio_port = _get_minio_config()

        # 检查主机名
        if parsed.hostname == minio_host:
            # 如果指定了端口，也需要匹配
            if parsed.port is not None:
                return parsed.port == minio_port
            return True

        # 也支持通过IP地址访问
        # 这里可以扩展更多的判断逻辑

    return False


def parse_minio_url(url: str) -> Tuple[str, str]:
    """
    解析MinIO URL，提取bucket和对象路径

    Args:
        url: MinIO URL（支持http和minio://格式）

    Returns:
        (bucket_name, object_path) 元组

    Raises:
        ValueError: URL格式不正确

    Examples:
        >>> parse_minio_url("minio://yivideo/task/file.mp4")
        ('yivideo', 'task/file.mp4')

        >>> parse_minio_url("http://minio:9000/yivideo/task/file.mp4")
        ('yivideo', 'task/file.mp4')
    """
    # 先规范化为minio://格式
    minio_url = normalize_minio_url(url)

    # 提取路径部分
    path = minio_url[len('minio://'):]
    if not path:
        raise ValueError(f"MinIO URL中缺少bucket: {url}")

    # 分割bucket和对象路径
    parts = path.split('/', 1)
    bucket_name = parts[0]
    object_path = parts[1] if len(parts) > 1 else ''

    return bucket_name, object_path
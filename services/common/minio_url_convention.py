# services/common/minio_url_convention.py
# -*- coding: utf-8 -*-

"""
MinIO URL 字段命名约定模块。

本模块提供统一的 MinIO URL 字段命名规范，确保所有节点遵循一致的命名约定：
- 规则：{field_name}_minio_url（保留完整的本地字段名作为前缀）
- 数组字段：{field_name}_minio_urls（复数形式）

示例：
    audio_path → audio_path_minio_url
    keyframe_dir → keyframe_dir_minio_url（保留 _dir）
    all_audio_files → all_audio_files_minio_urls（复数）
"""

from typing import Dict, Any, List


class MinioUrlNamingConvention:
    """MinIO URL 字段命名约定"""

    # 需要生成 MinIO URL 的字段后缀模式
    PATH_SUFFIXES = ["_path", "_file", "_dir", "_audio", "_video", "_image", "_data"]

    # 数组字段的特殊处理（需要复数形式）
    ARRAY_FIELDS = ["all_audio_files", "keyframe_files", "cropped_images_files", "subtitle_files"]

    @staticmethod
    def get_minio_url_field_name(local_field_name: str) -> str:
        """
        根据本地字段名生成 MinIO URL 字段名。

        规则:
        1. 保留完整的本地字段名作为前缀
        2. 添加 _minio_url 后缀
        3. 数组字段添加 _minio_urls（复数）

        Args:
            local_field_name: 本地字段名

        Returns:
            MinIO URL 字段名

        Examples:
            >>> MinioUrlNamingConvention.get_minio_url_field_name("audio_path")
            'audio_path_minio_url'
            >>> MinioUrlNamingConvention.get_minio_url_field_name("keyframe_dir")
            'keyframe_dir_minio_url'
            >>> MinioUrlNamingConvention.get_minio_url_field_name("all_audio_files")
            'all_audio_files_minio_urls'
        """
        if local_field_name in MinioUrlNamingConvention.ARRAY_FIELDS:
            return f"{local_field_name}_minio_urls"
        else:
            return f"{local_field_name}_minio_url"

    @staticmethod
    def is_path_field(field_name: str) -> bool:
        """
        判断字段是否为路径字段（需要生成 MinIO URL）。

        Args:
            field_name: 字段名

        Returns:
            True 如果是路径字段，False 否则

        Examples:
            >>> MinioUrlNamingConvention.is_path_field("audio_path")
            True
            >>> MinioUrlNamingConvention.is_path_field("model_name")
            False
        """
        return any(
            field_name.endswith(suffix)
            for suffix in MinioUrlNamingConvention.PATH_SUFFIXES
        ) or field_name in MinioUrlNamingConvention.ARRAY_FIELDS


def apply_minio_url_convention(
    output: Dict[str, Any],
    auto_upload_enabled: bool = False,
    custom_path_fields: List[str] = None
) -> Dict[str, Any]:
    """
    应用 MinIO URL 命名约定到输出字典。

    Args:
        output: 原始输出字典（包含本地路径）
        auto_upload_enabled: 全局上传开关是否启用
        custom_path_fields: 自定义路径字段列表（可选）

    Returns:
        增强后的输出字典（包含 MinIO URL 字段）

    Note:
        - 仅在 auto_upload_enabled=True 时生成 MinIO URL
        - 原始本地路径字段不被覆盖或删除
        - 实际的 MinIO URL 生成由 StateManager 处理，此函数仅添加字段占位符
    """
    if not auto_upload_enabled:
        return output

    enhanced_output = output.copy()
    convention = MinioUrlNamingConvention()

    # 合并自定义路径字段
    all_path_fields = set()
    if custom_path_fields:
        all_path_fields.update(custom_path_fields)

    # 遍历所有字段
    for field_name, field_value in output.items():
        # 检查是否为路径字段
        if not (convention.is_path_field(field_name) or field_name in all_path_fields):
            continue

        # 跳过已经是 MinIO URL 字段的
        if "_minio_url" in field_name:
            continue

        minio_field_name = convention.get_minio_url_field_name(field_name)

        # 处理数组字段
        if isinstance(field_value, list):
            # 占位符，实际 URL 由 StateManager 生成
            enhanced_output[minio_field_name] = []

        # 处理单个路径字段
        elif isinstance(field_value, str) and field_value:
            # 占位符，实际 URL 由 StateManager 生成
            enhanced_output[minio_field_name] = ""

    return enhanced_output


def validate_minio_url_naming(output: Dict[str, Any]) -> List[str]:
    """
    验证输出字典中的 MinIO URL 字段命名是否符合约定。

    Args:
        output: 输出字典

    Returns:
        验证错误列表（空列表表示验证通过）

    Examples:
        >>> output = {"keyframe_dir": "/share/kf", "keyframe_minio_url": "http://..."}
        >>> errors = validate_minio_url_naming(output)
        >>> errors
        ['MinIO URL field "keyframe_minio_url" does not follow naming convention. Expected: "keyframe_dir_minio_url"']
    """
    errors = []
    convention = MinioUrlNamingConvention()

    for field_name in output.keys():
        # 检查是否为 MinIO URL 字段
        if "_minio_url" not in field_name:
            continue

        # 提取本地字段名
        local_field_name = field_name.replace("_minio_urls", "").replace("_minio_url", "")

        # 验证命名是否符合约定
        expected_name = convention.get_minio_url_field_name(local_field_name)
        if field_name != expected_name:
            errors.append(
                f'MinIO URL field "{field_name}" does not follow naming convention. '
                f'Expected: "{expected_name}"'
            )

        # 验证对应的本地字段是否存在
        if local_field_name not in output:
            errors.append(
                f'MinIO URL field "{field_name}" exists but '
                f'corresponding local field "{local_field_name}" is missing'
            )

    return errors

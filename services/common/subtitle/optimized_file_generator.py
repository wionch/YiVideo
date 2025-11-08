"""
优化文件生成器

生成优化后的转录JSON文件，保持原数据结构并添加优化元数据。

作者: Claude Code
日期: 2025-11-06
版本: v1.0.0
"""

import json
import logging
import time
from typing import List, Dict, Any, Optional
from pathlib import Path
from copy import deepcopy

logger = logging.getLogger(__name__)


class OptimizedFileGenerator:
    """优化文件生成器

    生成优化后的转录JSON文件，保持与原文件相同的数据结构。
    """

    def __init__(self):
        """初始化文件生成器"""
        pass

    def _validate_output_path(self, file_path: str) -> None:
        """验证输出文件路径安全性

        Args:
            file_path: 输出文件路径

        Raises:
            ValueError: 文件路径不安全
        """
        import os

        # 规范化路径
        normalized_path = os.path.normpath(file_path)

        # 检查是否包含父目录引用
        if normalized_path.startswith('..') or '/..' in normalized_path or '\\..' in normalized_path:
            raise ValueError(f"不安全的文件路径: {file_path}")

        logger.debug(f"文件路径验证通过: {file_path}")

    def generate_optimized_file(self,
                              original_file_path: str,
                              optimized_subtitles: List[Dict[str, Any]],
                              output_file_path: str,
                              optimization_info: Dict[str, Any]) -> str:
        """生成优化后的转录文件

        Args:
            original_file_path: 原始转录文件路径
            optimized_subtitles: 优化后的字幕列表
            output_file_path: 输出文件路径
            optimization_info: 优化信息

        Returns:
            实际输出的文件路径

        Raises:
            FileNotFoundError: 原始文件不存在
            json.JSONDecodeError: JSON格式错误
        """
        logger.info(f"开始生成优化文件: {output_file_path}")

        # 读取原始文件
        try:
            with open(original_file_path, 'r', encoding='utf-8') as f:
                original_data = json.load(f)
        except FileNotFoundError:
            logger.error(f"原始文件不存在: {original_file_path}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"原始文件JSON格式错误: {e}")
            raise

        # 创建优化后的数据
        optimized_data = self._create_optimized_data(
            original_data,
            optimized_subtitles,
            optimization_info
        )

        # 验证输出文件路径安全性
        self._validate_output_path(output_file_path)

        # 确保输出目录存在
        output_path = Path(output_file_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 写入优化文件
        with open(output_file_path, 'w', encoding='utf-8') as f:
            json.dump(optimized_data, f, ensure_ascii=False, indent=2)

        logger.info(f"优化文件生成成功: {output_file_path}")
        return output_file_path

    def _create_optimized_data(self,
                             original_data: Dict[str, Any],
                             optimized_subtitles: List[Dict[str, Any]],
                             optimization_info: Dict[str, Any]) -> Dict[str, Any]:
        """创建优化后的数据结构

        Args:
            original_data: 原始数据
            optimized_subtitles: 优化后字幕
            optimization_info: 优化信息

        Returns:
            优化后的数据结构
        """
        # 深拷贝原始数据
        optimized_data = deepcopy(original_data)

        # 更新metadata
        if 'metadata' not in optimized_data:
            optimized_data['metadata'] = {}

        # 添加优化信息到metadata
        optimized_data['metadata']['optimization_info'] = {
            'optimized_by': 'wservice.ai_optimize_subtitles',
            'optimization_provider': optimization_info.get('provider', 'unknown'),
            'optimization_timestamp': time.time(),
            'segments_count': len(optimized_subtitles),
            'commands_applied': optimization_info.get('commands_count', 0)
        }

        # 更新segments
        if 'segments' in optimized_data:
            # 创建ID到片段的映射
            subtitle_map = {sub['id']: sub for sub in optimized_subtitles}

            # 更新每个片段的文本
            for segment in optimized_data['segments']:
                segment_id = segment.get('id')
                if segment_id in subtitle_map:
                    segment['text'] = subtitle_map[segment_id]['text']
                    # 词级时间戳设为空数组
                    segment['words'] = []
                else:
                    logger.warning(f"片段ID {segment_id} 在优化结果中未找到")
                    # 保持原片段不变
                    segment['words'] = []

        # 添加优化元数据
        optimized_data['optimization_metadata'] = {
            'processing_time': optimization_info.get('processing_time', 0.0),
            'commands_count': optimization_info.get('commands_count', 0),
            'moved_segments': optimization_info.get('moved_segments', 0),
            'updated_segments': optimization_info.get('updated_segments', 0),
            'deleted_words': optimization_info.get('deleted_words', 0),
            'punctuated_segments': optimization_info.get('punctuated_segments', 0)
        }

        return optimized_data

    def generate_output_path(self,
                           workflow_id: str,
                           original_file_path: str,
                           suffix: str = 'optimized') -> str:
        """生成优化文件输出路径

        Args:
            workflow_id: 工作流ID
            original_file_path: 原始文件路径
            suffix: 文件名后缀

        Returns:
            输出文件路径
        """
        original_path = Path(original_file_path)
        stem = original_path.stem
        extension = original_path.suffix
        parent = original_path.parent

        # 生成新的文件名
        new_filename = f"{stem}_{suffix}{extension}"
        output_path = parent / new_filename

        return str(output_path)

    def validate_output_file(self, output_file_path: str) -> Dict[str, Any]:
        """验证输出文件

        Args:
            output_file_path: 输出文件路径

        Returns:
            验证结果
        """
        try:
            with open(output_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 验证必要字段
            required_fields = ['metadata', 'segments']
            for field in required_fields:
                if field not in data:
                    return {
                        'valid': False,
                        'error': f'缺少必要字段: {field}'
                    }

            # 验证metadata
            if 'optimization_info' not in data['metadata']:
                return {
                    'valid': False,
                    'error': '缺少optimization_info字段'
                }

            # 验证segments
            if not isinstance(data['segments'], list):
                return {
                    'valid': False,
                    'error': 'segments字段必须是数组'
                }

            # 验证每个segment
            for i, segment in enumerate(data['segments']):
                if 'id' not in segment or 'text' not in segment:
                    return {
                        'valid': False,
                        'error': f'segment {i} 缺少必要字段'
                    }

            return {
                'valid': True,
                'segments_count': len(data['segments']),
                'has_optimization_info': True
            }

        except json.JSONDecodeError as e:
            return {
                'valid': False,
                'error': f'JSON格式错误: {e}'
            }
        except Exception as e:
            return {
                'valid': False,
                'error': f'验证失败: {e}'
            }

    def get_file_info(self, file_path: str) -> Dict[str, Any]:
        """获取文件信息

        Args:
            file_path: 文件路径

        Returns:
            文件信息
        """
        try:
            path = Path(file_path)
            if not path.exists():
                return {'exists': False}

            stat = path.stat()
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            return {
                'exists': True,
                'size': stat.st_size,
                'modified': stat.st_mtime,
                'segments_count': len(data.get('segments', [])),
                'has_optimization': 'optimization_info' in data.get('metadata', {})
            }
        except Exception as e:
            return {
                'exists': True,
                'error': str(e)
            }
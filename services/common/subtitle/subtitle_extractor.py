"""
字幕数据提取器

从faster_whisper转录JSON文件中提取字幕内容，组成精简的JSON数组。

作者: Claude Code
日期: 2025-11-06
版本: v1.0.0
"""

import json
import logging
from typing import List, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class SubtitleExtractor:
    """字幕数据提取器

    从转录JSON文件中提取字幕文本，用于发送给AI模型进行优化。
    """

    def __init__(self):
        """初始化提取器"""
        pass

    def extract_subtitles(self, transcribe_file_path: str) -> List[Dict[str, Any]]:
        """从转录文件中提取字幕数据

        Args:
            transcribe_file_path: 转录JSON文件路径

        Returns:
            精简的字幕数组，每个元素包含id和text

        Raises:
            FileNotFoundError: 文件不存在
            json.JSONDecodeError: JSON格式错误
            KeyError: 缺少必要字段
        """
        logger.info(f"开始提取字幕数据: {transcribe_file_path}")

        try:
            with open(transcribe_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            logger.error(f"转录文件不存在: {transcribe_file_path}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"JSON格式错误: {e}")
            raise

        # 验证必要字段
        if 'segments' not in data:
            logger.error("转录文件缺少segments字段")
            raise KeyError("转录文件缺少segments字段")

        segments = data['segments']

        # 提取字幕文本
        subtitles = []
        for segment in segments:
            if 'id' not in segment or 'text' not in segment:
                logger.warning(f"跳过无效片段: {segment}")
                continue

            subtitles.append({
                'id': segment['id'],
                'text': segment['text']
            })

        logger.info(f"提取完成: {len(subtitles)}条字幕")
        return subtitles

    def validate_transcribe_file(self, transcribe_file_path: str) -> bool:
        """验证转录文件格式

        Args:
            transcribe_file_path: 文件路径

        Returns:
            是否为有效格式
        """
        try:
            with open(transcribe_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if 'segments' not in data or not isinstance(data['segments'], list):
                return False

            for segment in data['segments']:
                if 'id' not in segment or 'text' not in segment:
                    return False

            return True
        except Exception as e:
            logger.error(f"验证文件失败: {e}")
            return False
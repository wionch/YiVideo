"""
System Prompt加载器

从config/system_prompt/subtitle_optimization.md加载AI优化的系统提示词。

作者: Claude Code
日期: 2025-11-06
版本: v1.0.0
"""

import logging
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class PromptLoader:
    """System Prompt加载器

    加载和管理AI字幕优化的系统提示词。
    """

    def __init__(self):
        """初始化提示词加载器"""
        self._default_prompt = self._get_default_prompt()
        self._prompt_cache: Optional[str] = None

    def load_prompt(self, prompt_file_path: Optional[str] = None) -> str:
        """加载系统提示词

        Args:
            prompt_file_path: 提示词文件路径，如果为None则使用默认路径

        Returns:
            系统提示词内容

        Raises:
            FileNotFoundError: 文件不存在
        """
        # 如果没有指定路径，使用默认路径
        if prompt_file_path is None:
            prompt_file_path = self._get_default_prompt_path()

        logger.info(f"加载系统提示词: {prompt_file_path}")

        try:
            with open(prompt_file_path, 'r', encoding='utf-8') as f:
                prompt = f.read().strip()

            if not prompt:
                logger.warning(f"提示词文件为空: {prompt_file_path}，使用默认提示词")
                return self._default_prompt

            logger.info(f"系统提示词加载成功，长度: {len(prompt)}字符")
            return prompt

        except FileNotFoundError:
            logger.warning(f"提示词文件不存在: {prompt_file_path}，使用默认提示词")
            return self._default_prompt
        except Exception as e:
            logger.error(f"加载提示词失败: {e}，使用默认提示词")
            return self._default_prompt

    def _get_default_prompt_path(self) -> str:
        """获取默认提示词文件路径

        Returns:
            文件路径
        """
        # 尝试多个可能的路径
        possible_paths = [
            "/config/system_prompt/subtitle_optimization.md",
            "config/system_prompt/subtitle_optimization.md",
            "/app/config/system_prompt/subtitle_optimization.md",
            "./config/system_prompt/subtitle_optimization.md"
        ]

        for path in possible_paths:
            if Path(path).exists():
                return path

        # 如果都不存在，返回第一个路径
        return possible_paths[0]

    def _get_default_prompt(self) -> str:
        """获取默认系统提示词

        Returns:
            默认提示词内容
        """
        return """你是一个专业的字幕纠错助手。你的输入是完整正文文本。

只允许：
1. 修正错别字
2. 修正标点
3. 大小写与格式规范化

禁止：
1. 增删内容
2. 合并或拆分句子
3. 调整语序或改写

输出要求：
- 只输出纠错后的完整正文文本
- 不要输出 JSON、列表、解释或任何额外说明
"""

    def is_prompt_file_exists(self, prompt_file_path: Optional[str] = None) -> bool:
        """检查提示词文件是否存在

        Args:
            prompt_file_path: 文件路径

        Returns:
            是否存在
        """
        if prompt_file_path is None:
            prompt_file_path = self._get_default_prompt_path()

        return Path(prompt_file_path).exists()

    def get_prompt_info(self, prompt_file_path: Optional[str] = None) -> dict:
        """获取提示词文件信息

        Args:
            prompt_file_path: 文件路径

        Returns:
            提示词信息
        """
        if prompt_file_path is None:
            prompt_file_path = self._get_default_prompt_path()

        try:
            prompt = self.load_prompt(prompt_file_path)
            return {
                "exists": Path(prompt_file_path).exists(),
                "path": prompt_file_path,
                "length": len(prompt),
                "lines": len(prompt.splitlines())
            }
        except Exception as e:
            return {
                "exists": False,
                "path": prompt_file_path,
                "error": str(e)
            }

"""
Token估算工具

用于估算中文文本在AI模型中的token数量，特别是针对DeepSeek等模型的优化。
由于中文字符的token计算比较复杂，这里提供实用的估算方法。
"""

import re
import math
from typing import Dict, List, Tuple


class TokenEstimator:
    """Token估算器"""

    def __init__(self):
        # 中文字符token估算因子（基于GPT/DeepSeek等模型的平均表现）
        self.chinese_char_token_ratio = 1.5  # 1个中文字符 ≈ 1.5个token
        self.english_char_token_ratio = 0.25  # 1个英文字符 ≈ 0.25个token
        self.number_token_ratio = 0.5  # 数字和标点 ≈ 0.5个token
        self.overhead_tokens_per_message = 10  # 每条消息的开销

        # DeepSeek API的具体限制
        self.deepseek_max_context = 128000  # 总上下文限制
        self.deepseek_safe_input = 60000   # 安全输入限制（留出输出空间）
        self.deepseek_max_output = 8000    # 最大输出

    def estimate_text_tokens(self, text: str) -> int:
        """
        估算文本的token数量

        Args:
            text: 要估算的文本

        Returns:
            int: 估算的token数量
        """
        if not text:
            return 0

        # 统计不同类型的字符
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        english_chars = len(re.findall(r'[a-zA-Z]', text))
        # 修正正则表达式，移除不支持的Unicode属性类
        numbers_and_punctuation = len(re.findall(r'[0-9\s\.,;:!?\"\'\(\)\[\]\{\}<>\-\+\*\/\=\&\%\$\@\#]', text))

        # 计算估算token数
        chinese_tokens = chinese_chars * self.chinese_char_token_ratio
        english_tokens = english_chars * self.english_char_token_ratio
        number_tokens = numbers_and_punctuation * self.number_token_ratio

        total_tokens = int(chinese_tokens + english_tokens + number_tokens)

        # 添加一些缓冲
        return int(total_tokens * 1.1)

    def estimate_subtitle_tokens(self, subtitle_text: str, include_system_prompt: bool = True) -> Dict[str, int]:
        """
        估算字幕校正请求的token使用情况

        Args:
            subtitle_text: 字幕文本
            include_system_prompt: 是否包含系统提示词

        Returns:
            Dict: 包含各种token使用情况的字典
        """
        # 估算字幕文本token
        subtitle_tokens = self.estimate_text_tokens(subtitle_text)

        # 估算系统提示词token（假设系统提示词约2000-3000字符）
        system_prompt_tokens = 3000 if include_system_prompt else 0

        # 估算其他开销（角色标记、格式等）
        format_overhead = self.overhead_tokens_per_message * 2  # system + user消息

        total_input_tokens = subtitle_tokens + system_prompt_tokens + format_overhead

        return {
            'subtitle_tokens': subtitle_tokens,
            'system_prompt_tokens': system_prompt_tokens,
            'format_overhead': format_overhead,
            'total_input_tokens': total_input_tokens,
            'safe_for_deepseek': total_input_tokens <= self.deepseek_safe_input,
            'within_context_limit': total_input_tokens <= self.deepseek_max_context
        }

    def calculate_optimal_batch_size(self, text: str, target_tokens: int = None) -> int:
        """
        计算最优的分批大小（字符数）

        Args:
            text: 原始文本
            target_tokens: 目标token数，默认使用DeepSeek安全限制

        Returns:
            int: 推荐的批次大小（字符数）
        """
        if target_tokens is None:
            target_tokens = self.deepseek_safe_input // 4  # 留出足够的安全边距

        # 估算当前文本的token密度
        if not text:
            return 0

        estimated_tokens = self.estimate_text_tokens(text)
        token_density = estimated_tokens / len(text) if len(text) > 0 else 1

        # 计算目标字符数
        target_chars = int(target_tokens / token_density)

        # 设置合理的最小和最大批次大小
        min_batch_size = 500
        max_batch_size = 5000

        return max(min_batch_size, min(max_batch_size, target_chars))

    def should_batch_process(self, text: str, max_length: int = None) -> Tuple[bool, int, Dict]:
        """
        判断是否应该进行分批处理

        Args:
            text: 要处理的文本
            max_length: 配置的最大长度限制

        Returns:
            Tuple: (是否分批, 推荐批次大小, 详细信息)
        """
        if not text:
            return False, 0, {'reason': 'empty_text'}

        text_length = len(text)
        token_info = self.estimate_subtitle_tokens(text)

        # 多重判断标准
        reasons = []
        should_batch = False

        # 标准1：基于配置的字符长度
        if max_length and text_length > max_length:
            should_batch = True
            reasons.append(f'exceeds_config_limit: {text_length} > {max_length}')

        # 标准2：基于token安全限制
        if not token_info['safe_for_deepseek']:
            should_batch = True
            reasons.append(f'exceeds_safe_token_limit: {token_info["total_input_tokens"]} > {self.deepseek_safe_input}')

        # 标准3：基于合理的处理大小（建议超过3000字符就分批）
        if text_length > 3000:
            should_batch = True
            reasons.append(f'exceeds_recommended_size: {text_length} > 3000')

        # 计算推荐的批次大小
        if should_batch:
            batch_size = self.calculate_optimal_batch_size(text)
        else:
            batch_size = text_length

        detail_info = {
            'text_length': text_length,
            'token_estimate': token_info,
            'reasons': reasons,
            'recommended_batch_size': batch_size
        }

        return should_batch, batch_size, detail_info


# 全局实例
token_estimator = TokenEstimator()


def estimate_tokens(text: str) -> int:
    """便捷函数：估算文本token数"""
    return token_estimator.estimate_text_tokens(text)


def should_batch_subtitle(text: str, max_length: int = None) -> Tuple[bool, int, Dict]:
    """便捷函数：判断字幕是否需要分批处理"""
    return token_estimator.should_batch_process(text, max_length)
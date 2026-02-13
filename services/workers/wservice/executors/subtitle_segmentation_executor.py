"""
WService 字幕分句执行器。

基于 PySBD + LangChain 实现语义分句和字符限制，支持词级时间戳映射。
"""

import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict

from services.common.base_node_executor import BaseNodeExecutor
from services.common.logger import get_logger
from services.common.parameter_resolver import get_param_with_fallback
from services.common.path_builder import build_node_output_path, ensure_directory
from services.common.file_service import get_file_service

logger = get_logger(__name__)


@dataclass
class SubtitleSegment:
    """字幕片段数据模型"""
    id: int  # 片段唯一标识（从 1 开始）
    text: str
    start: Optional[float] = None
    end: Optional[float] = None
    duration: Optional[float] = None
    word_count: Optional[int] = None
    char_count: Optional[int] = None
    words: Optional[List[Dict[str, Any]]] = None  # 词级时间戳列表


class ASRDataLoader:
    """ASR 数据处理辅助类"""

    @staticmethod
    def build_char_to_timestamp_map(text: str, timestamps: List[Dict]) -> Dict[int, Dict]:
        """
        构建字符位置到时间戳的映射。

        Args:
            text: 完整文本（包含标点和空格）
            timestamps: 词级时间戳列表 [{text, start, end}, ...]

        Returns:
            {char_index: {word, start, end, word_index}, ...}
        """
        char_map = {}
        text_idx = 0

        for word_idx, ts in enumerate(timestamps):
            word = ts["text"]
            start = ts["start"]
            end = ts["end"]

            # 跳过前导空格和标点（但不跳过撇号）
            while text_idx < len(text) and text[text_idx] in ' \t\n.,!?;:"':
                text_idx += 1

            if text_idx >= len(text):
                break

            word_len = len(word)

            # 尝试直接匹配
            if text_idx + word_len <= len(text) and \
               text[text_idx:text_idx+word_len].lower() == word.lower():
                for i in range(text_idx, text_idx + word_len):
                    char_map[i] = {
                        "word": word,
                        "start": start,
                        "end": end,
                        "word_index": word_idx
                    }
                text_idx += word_len
            else:
                # 匹配失败，尝试在附近范围内查找
                search_end = min(text_idx + 100, len(text))
                search_text = text[text_idx:search_end]
                found_offset = search_text.lower().find(word.lower())

                if found_offset != -1:
                    found_pos = text_idx + found_offset
                    for i in range(found_pos, found_pos + word_len):
                        char_map[i] = {
                            "word": word,
                            "start": start,
                            "end": end,
                            "word_index": word_idx
                        }
                    text_idx = found_pos + word_len

        return char_map


class PySBDLangChainSubtitleSegmenter:
    """PySBD + LangChain 字幕分句器"""

    def __init__(self, max_chars: int = 42, language: str = "en"):
        """
        初始化分句器。

        Args:
            max_chars: 单行字幕最大字符数
            language: 语言代码（支持 PySBD 的 23 种语言）
        """
        try:
            import pysbd
            self.pysbd_seg = pysbd.Segmenter(language=language, clean=False)
        except ImportError as e:
            raise ImportError(
                "请先安装 pysbd: pip install pysbd>=0.3.4"
            ) from e

        try:
            from langchain_text_splitters import RecursiveCharacterTextSplitter
            # 字幕专用配置：优先在标点处断开
            self.langchain_splitter = RecursiveCharacterTextSplitter(
                chunk_size=max_chars,
                chunk_overlap=0,
                keep_separator="end",  # 🔑 关键：分隔符保留在前一个块的结尾
                separators=[
                    ", ",   # 优先级1：逗号后断开（自然停顿）
                    "; ",   # 优先级2：分号后断开
                    ". ",   # 优先级3：句号后断开
                    "! ",   # 优先级4：感叹号后断开
                    "? ",   # 优先级5：问号后断开
                    " ",    # 优先级6：空格
                    ""      # 优先级7：强制按字符切（最后手段）
                ]
            )
        except ImportError as e:
            raise ImportError(
                "请先安装 langchain-text-splitters: pip install langchain-text-splitters>=0.3.2"
            ) from e

        self.max_chars = max_chars
        self.language = language
        self.pysbd_sentences = []  # 保存 PySBD 原始分句结果

    def segment(
        self,
        text: str,
        words: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        执行分句。

        Args:
            text: 待分句的文本
            words: 词级时间戳列表（可选）

        Returns:
            {
                segments: List[SubtitleSegment],
                total_segments: int,
                statistics: {...}
            }
        """
        start_time = time.time()

        # 阶段 1: PySBD 语义分句
        pysbd_sentences = self.pysbd_seg.segment(text)
        self.pysbd_sentences = pysbd_sentences  # 保存原始分句结果
        logger.debug(f"PySBD 分句完成，共 {len(pysbd_sentences)} 个句子")

        # 阶段 2: 处理字符限制和时间戳映射
        if words:
            # 构建字符映射
            char_map = ASRDataLoader.build_char_to_timestamp_map(text, words)
            logger.debug(f"字符映射完成，覆盖 {len(char_map)} 个字符")

            # 带时间戳处理
            segments = self._process_with_langchain(
                pysbd_sentences, text, char_map, words
            )
        else:
            # 仅文本处理（无时间戳）
            segments = self._process_text_only(pysbd_sentences)

        execution_time = time.time() - start_time

        # 计算统计数据
        stats = self._calculate_statistics(segments, pysbd_sentences, has_timestamps=bool(words))

        return {
            "segments": segments,
            "total_segments": len(segments),
            "execution_time": execution_time,
            "statistics": stats
        }

    def _process_text_only(self, sentences: List[str]) -> List[SubtitleSegment]:
        """
        处理仅文本分句（无时间戳）。

        Args:
            sentences: PySBD 分句结果

        Returns:
            List[SubtitleSegment]
        """
        segments = []
        segment_id = 1

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            # 检查是否超过字符限制
            if len(sentence) <= self.max_chars:
                segments.append(SubtitleSegment(
                    id=segment_id,
                    text=sentence,
                    char_count=len(sentence)
                ))
                segment_id += 1
            else:
                # 超限，使用 LangChain 分割
                lines = self.langchain_splitter.split_text(sentence)
                for line_text in lines:
                    line_text = line_text.strip()
                    if line_text:
                        segments.append(SubtitleSegment(
                            id=segment_id,
                            text=line_text,
                            char_count=len(line_text)
                        ))
                        segment_id += 1

        return segments

    def _process_with_langchain(
        self,
        sentences: List[str],
        full_text: str,
        char_map: Dict[int, Dict],
        timestamps: List[Dict]
    ) -> List[SubtitleSegment]:
        """
        使用 LangChain 处理字符限制并映射时间戳。

        Args:
            sentences: PySBD 分句结果
            full_text: 完整文本
            char_map: 字符到时间戳的映射
            timestamps: 原始词级时间戳列表

        Returns:
            List[SubtitleSegment]
        """
        segments = []
        char_offset = 0
        segment_id = 1

        for idx, sentence in enumerate(sentences, 1):
            sentence = sentence.strip()
            if not sentence:
                continue

            # 在原文中找到句子位置
            sent_start = full_text.find(sentence, char_offset)
            if sent_start == -1:
                logger.warning(f"句子 {idx} 无法在原文中定位，跳过")
                continue

            sent_end = sent_start + len(sentence) - 1

            # 检查是否超过字符限制
            if len(sentence) <= self.max_chars:
                # 不超限，直接创建片段
                seg = self._create_segment(
                    segment_id, sentence, sent_start, sent_end, char_map, timestamps
                )
                if seg:
                    segments.append(seg)
                    segment_id += 1
            else:
                # 超限，使用 LangChain 分割
                lines = self.langchain_splitter.split_text(sentence)

                # 为每行分配时间戳
                line_char_offset = sent_start
                for line_text in lines:
                    line_text = line_text.strip()
                    if not line_text:
                        continue

                    # 在原句中找到这一行的位置
                    line_start = full_text.find(line_text, line_char_offset)
                    if line_start == -1:
                        # 尝试模糊匹配（去除标点）
                        clean_line = line_text.strip('.,!?;: ')
                        line_start = full_text.find(clean_line, line_char_offset)

                    if line_start != -1:
                        line_end = line_start + len(line_text) - 1
                        seg = self._create_segment(
                            segment_id, line_text, line_start, line_end, char_map, timestamps
                        )
                        if seg:
                            segments.append(seg)
                            segment_id += 1
                        line_char_offset = line_end + 1

            char_offset = sent_end + 1

        return segments

    def _create_segment(
        self,
        segment_id: int,
        text: str,
        start_pos: int,
        end_pos: int,
        char_map: Dict[int, Dict],
        timestamps: List[Dict]
    ) -> Optional[SubtitleSegment]:
        """
        创建字幕片段。

        Args:
            segment_id: 片段唯一标识（从1开始）
            text: 片段文本
            start_pos: 在原文中的起始位置
            end_pos: 在原文中的结束位置
            char_map: 字符映射表
            timestamps: 原始时间戳列表

        Returns:
            SubtitleSegment or None
        """
        # 获取起始和结束时间戳
        start_ts = char_map.get(start_pos, {}).get("start")
        end_ts = char_map.get(end_pos, {}).get("end")

        # 如果直接找不到，向后/向前搜索
        if start_ts is None:
            for i in range(start_pos, min(end_pos + 1, start_pos + 100)):
                if i in char_map:
                    start_ts = char_map[i]["start"]
                    break

        if end_ts is None:
            for i in range(end_pos, max(start_pos - 1, end_pos - 100), -1):
                if i in char_map:
                    end_ts = char_map[i]["end"]
                    break

        if start_ts is None or end_ts is None:
            return None

        # 提取词级时间戳
        word_indices = set()
        for char_pos in range(start_pos, end_pos + 1):
            if char_pos in char_map:
                word_idx = char_map[char_pos].get("word_index")
                if word_idx is not None:
                    word_indices.add(word_idx)

        word_indices = sorted(word_indices)
        segment_words = []
        for word_idx in word_indices:
            ts = timestamps[word_idx]
            segment_words.append({
                "text": ts["text"],
                "start": ts["start"],
                "end": ts["end"]
            })

        return SubtitleSegment(
            id=segment_id,
            text=text,
            start=start_ts,
            end=end_ts,
            duration=end_ts - start_ts,
            word_count=len(segment_words),
            char_count=len(text),
            words=segment_words
        )

    def _calculate_statistics(
        self,
        segments: List[SubtitleSegment],
        pysbd_sentences: List[str],
        has_timestamps: bool
    ) -> Dict[str, Any]:
        """计算统计数据"""
        if not segments:
            return {}

        # 检查字符限制合规性
        over_limit = [s for s in segments if s.char_count > self.max_chars]
        compliance_rate = (len(segments) - len(over_limit)) / len(segments) * 100

        stats = {
            "pysbd_sentences": len(pysbd_sentences),
            "final_segments": len(segments),
            "expansion_ratio": round(len(segments) / len(pysbd_sentences), 2),
            "character_limit": {
                "max_allowed": self.max_chars,
                "compliance_rate": round(compliance_rate, 2),
                "over_limit_count": len(over_limit)
            },
            "has_timestamps": has_timestamps
        }

        return stats

    def get_pysbd_segments(self, text: str, words: Optional[List[Dict]] = None) -> List[SubtitleSegment]:
        """
        获取 PySBD 原始分句结果（不经过 LangChain 字符限制处理）。

        Args:
            text: 待分句的文本
            words: 词级时间戳列表（可选）

        Returns:
            List[SubtitleSegment]: PySBD 原始分句列表
        """
        # 执行 PySBD 分句
        pysbd_sentences = self.pysbd_seg.segment(text)
        segments = []

        if words:
            # 构建字符映射
            char_map = ASRDataLoader.build_char_to_timestamp_map(text, words)

            # 为每个 PySBD 句子创建 segment（不分割）
            current_char_index = 0
            for seg_id, sentence in enumerate(pysbd_sentences, start=1):
                sentence = sentence.strip()
                if not sentence:
                    continue

                # 计算句子在原文中的字符范围
                sentence_start_idx = text.find(sentence, current_char_index)
                if sentence_start_idx == -1:
                    # 找不到精确匹配，跳过
                    logger.warning(f"句子未找到精确匹配: {sentence[:30]}...")
                    continue

                sentence_end_idx = sentence_start_idx + len(sentence)

                # 提取该句子范围内的词级时间戳
                segment_words = []
                segment_start = None
                segment_end = None

                for char_idx in range(sentence_start_idx, sentence_end_idx):
                    if char_idx in char_map:
                        word_data = char_map[char_idx]
                        # 避免重复添加同一个词
                        if not segment_words or segment_words[-1]["text"] != word_data["word"]:
                            segment_words.append({
                                "text": word_data["word"],
                                "start": word_data["start"],
                                "end": word_data["end"]
                            })

                            # 更新 segment 时间范围
                            if segment_start is None:
                                segment_start = word_data["start"]
                            segment_end = word_data["end"]

                # 计算时长
                duration = None
                if segment_start is not None and segment_end is not None:
                    duration = round(segment_end - segment_start, 2)

                segments.append(SubtitleSegment(
                    id=seg_id,
                    text=sentence,
                    start=segment_start,
                    end=segment_end,
                    duration=duration,
                    word_count=len(segment_words),
                    char_count=len(sentence),
                    words=segment_words if segment_words else None
                ))

                current_char_index = sentence_end_idx

        else:
            # 无时间戳，仅保存文本
            for seg_id, sentence in enumerate(pysbd_sentences, start=1):
                sentence = sentence.strip()
                if sentence:
                    segments.append(SubtitleSegment(
                        id=seg_id,
                        text=sentence,
                        char_count=len(sentence)
                    ))

        return segments


class WServiceSubtitleSegmentationExecutor(BaseNodeExecutor):
    """
    WService 字幕分句执行器。

    使用 PySBD + LangChain 实现语义分句和字符限制。

    输入参数:
        - subtitle_text (str, 可选): 字幕文本
        - words (list, 可选): 词级时间戳列表 [{text, start, end}, ...]
        - subtitle_file (str, 可选): 包含字幕数据的 JSON 文件路径
        - max_chars (int, 可选): 最大字符数限制（默认 42）
        - language (str, 可选): 语言代码（默认 "en"）

    输出字段:
        - segmented_subtitle_file (str): 分句结果文件路径
        - statistics (dict): 统计信息
    """

    def __init__(self, stage_name: str, context):
        super().__init__(stage_name, context)
        self.segmenter = None
        self.file_service = get_file_service()

    def validate_input(self) -> None:
        """
        验证输入参数。

        至少需要提供以下之一：
        - subtitle_text
        - subtitle_file
        """
        input_data = self.get_input_data()

        has_text = get_param_with_fallback("subtitle_text", input_data, self.context) is not None
        has_file = get_param_with_fallback("subtitle_file", input_data, self.context) is not None

        if not has_text and not has_file:
            raise ValueError(
                "缺少必需参数: 请提供 subtitle_text 或 subtitle_file"
            )

        logger.info(f"[{self.context.workflow_id}] 输入参数验证通过")

    def execute_core_logic(self) -> Dict[str, Any]:
        """
        执行字幕分句核心逻辑。

        Returns:
            包含分句结果的字典
        """
        workflow_id = self.context.workflow_id
        input_data = self.get_input_data()

        logger.info(f"[{workflow_id}] 开始字幕分句")

        # 获取字幕数据
        subtitle_data = self._get_subtitle_data(input_data)

        # 获取参数
        max_chars = get_param_with_fallback("max_chars", input_data, self.context) or 42
        language = get_param_with_fallback("language", input_data, self.context) or "en"

        logger.info(
            f"[{workflow_id}] 配置: max_chars={max_chars}, language={language}"
        )

        # 创建分句器
        self.segmenter = PySBDLangChainSubtitleSegmenter(
            max_chars=max_chars,
            language=language
        )

        # 执行分句
        result = self.segmenter.segment(
            text=subtitle_data["text"],
            words=subtitle_data.get("words")
        )

        logger.info(
            f"[{workflow_id}] 分句完成，生成 {result['total_segments']} 个片段"
        )

        # 保存最终结果（经过 LangChain 字符限制处理）
        output_file = self._save_segmented_result(
            result,
            max_chars,
            language
        )

        # 获取并保存 PySBD 原始结果（不经过 LangChain 处理）
        pysbd_segments = self.segmenter.get_pysbd_segments(
            text=subtitle_data["text"],
            words=subtitle_data.get("words")
        )
        pysbd_output_file = self._save_pysbd_result(
            pysbd_segments,
            language
        )

        logger.info(
            f"[{workflow_id}] PySBD 原始结果已保存: {pysbd_output_file}"
        )

        return {
            "segmented_subtitle_file": output_file,
            "segmented_subtitle_pysbd_file": pysbd_output_file,
            "statistics": result["statistics"]
        }

    def _get_subtitle_data(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        获取字幕数据。

        优先级:
        1. 直接传入的 subtitle_text + words
        2. subtitle_file 文件路径

        Args:
            input_data: 输入数据

        Returns:
            {text: str, words: List[Dict] | None}
        """
        workflow_id = self.context.workflow_id

        # 1. 尝试直接获取
        subtitle_text = get_param_with_fallback(
            "subtitle_text",
            input_data,
            self.context
        )
        if subtitle_text:
            words = get_param_with_fallback("words", input_data, self.context)
            logger.info(f"[{workflow_id}] 从 subtitle_text 获取字幕数据")
            return {
                "text": subtitle_text,
                "words": words or None
            }

        # 2. 尝试从文件加载
        subtitle_file = get_param_with_fallback(
            "subtitle_file",
            input_data,
            self.context
        )
        if subtitle_file:
            subtitle_file = self._normalize_path(subtitle_file)
            logger.info(f"[{workflow_id}] 从文件加载字幕数据: {subtitle_file}")
            subtitle_file = self._download_if_needed(subtitle_file)
            if subtitle_file:
                return self._load_subtitle_from_file(subtitle_file, input_data)

        raise ValueError("无法获取字幕数据: subtitle_text 和 subtitle_file 均为空")

    def _normalize_path(self, file_path: str) -> str:
        """
        规范化文件路径（处理 MinIO URL、相对路径、绝对路径）。

        Args:
            file_path: 原始文件路径

        Returns:
            规范化后的路径
        """
        # 如果是 MinIO URL，直接返回
        if file_path.startswith("http://") or file_path.startswith("https://"):
            return file_path

        # 如果是相对路径，转换为绝对路径
        if not file_path.startswith("/"):
            file_path = f"/app/{file_path}"

        return file_path

    def _download_if_needed(self, file_path: str) -> Optional[str]:
        """
        如果是 MinIO URL，下载到本地；否则直接返回路径。

        Args:
            file_path: 文件路径或 MinIO URL

        Returns:
            本地文件路径或 None
        """
        workflow_id = self.context.workflow_id

        # 如果是 MinIO URL，下载到本地
        if file_path.startswith("http://") or file_path.startswith("https://"):
            try:
                local_path = self.file_service.download_from_minio(file_path)
                logger.info(f"[{workflow_id}] 从 MinIO 下载文件: {file_path} -> {local_path}")
                return local_path
            except Exception as e:
                logger.error(f"[{workflow_id}] MinIO 文件下载失败: {e}")
                return None

        # 本地文件路径
        return file_path

    def _extract_json_value(self, data: Dict[str, Any], path: str) -> Any:
        """
        从 JSON 数据中提取嵌套路径的值（使用 JMESPath）。

        JMESPath 是 AWS 官方维护的成熟 JSON 查询语言，支持：
        - 嵌套访问：main.text
        - 数组索引：results[0], results[-1]（负数索引）
        - 数组切片：results[0:2]
        - 投影：results[*].name
        - 过滤：results[?age > 20]
        - 函数：length(results)

        Args:
            data: JSON 数据
            path: JMESPath 表达式

        Returns:
            提取的值，如果路径不存在返回 None

        Examples:
            >>> _extract_json_value({"main": {"text": "hello"}}, "main.text")
            "hello"
            >>> _extract_json_value({"arr": [1, 2, 3]}, "arr[-1]")
            3
            >>> _extract_json_value({"users": [{"name": "Alice"}, {"name": "Bob"}]}, "users[*].name")
            ["Alice", "Bob"]

        文档：https://jmespath.org/
        """
        if not path:
            return None

        try:
            import jmespath
            result = jmespath.search(path, data)
            return result
        except ImportError:
            # 降级到简单实现（向后兼容）
            logger.warning(
                "jmespath 未安装，使用简化路径解析。"
                "建议安装：pip install jmespath>=1.0.1"
            )
            return self._extract_json_value_fallback(data, path)
        except jmespath.exceptions.JMESPathError as e:
            logger.error(f"JMESPath 表达式错误: {path} - {e}")
            return None

    def _extract_json_value_fallback(self, data: Dict[str, Any], path: str) -> Any:
        """
        简化的路径提取实现（JMESPath 降级方案）。

        仅支持基本功能：
        - 点分隔符：main.text
        - 数组索引：arr[0] 或 arr.0

        不支持：负数索引、切片、过滤、函数等
        """
        if not path:
            return None

        # 替换数组索引语法 [0] 为 .0
        path = path.replace("[", ".").replace("]", "")

        # 按点分隔符拆分路径
        parts = path.split(".")
        current = data

        for part in parts:
            if not part:  # 跳过空字符串
                continue

            try:
                # 尝试作为数组索引
                if part.isdigit():
                    index = int(part)
                    if isinstance(current, list) and 0 <= index < len(current):
                        current = current[index]
                    else:
                        return None
                # 作为字典键
                elif isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    return None
            except (KeyError, IndexError, TypeError):
                return None

        return current

    def _load_subtitle_from_file(self, file_path: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        从 JSON 文件加载字幕数据。

        Args:
            file_path: JSON 文件路径
            input_data: 输入参数字典（用于获取 JSON 字段路径配置）

        Returns:
            {text: str, words: List[Dict] | None}
        """
        workflow_id = self.context.workflow_id

        if not Path(file_path).exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 验证 JSON 格式
            if not isinstance(data, dict):
                raise ValueError("JSON 文件必须是对象格式")

            # 从输入参数获取 JSON 字段路径配置
            text_path = get_param_with_fallback(
                "text_json_path", input_data, self.context
            ) or "text"
            words_path = get_param_with_fallback(
                "words_json_path", input_data, self.context
            ) or "time_stamps,words"

            # 提取文本字段（支持多级路径）
            text_value = self._extract_json_value(data, text_path)
            if text_value is None:
                raise ValueError(f"JSON 文件缺少指定字段: {text_path}")

            # 提取词级时间戳（支持多个候选字段，逗号分隔，支持多级路径）
            words = None
            for candidate_path in words_path.split(","):
                candidate_path = candidate_path.strip()
                words = self._extract_json_value(data, candidate_path)
                if words is not None:
                    logger.info(
                        f"[{workflow_id}] 从字段 '{candidate_path}' 提取词级时间戳"
                    )
                    break

            logger.info(
                f"[{workflow_id}] 成功加载字幕数据: {file_path} "
                f"(text_field={text_path}, has_timestamps={words is not None})"
            )

            return {
                "text": text_value,
                "words": words  # 可选字段
            }

        except json.JSONDecodeError as e:
            raise ValueError(f"JSON 文件解析失败: {file_path}") from e

    def _save_segmented_result(
        self,
        result: Dict[str, Any],
        max_chars: int,
        language: str
    ) -> str:
        """
        保存分句结果到 JSON 文件。

        Args:
            result: 分句结果
            max_chars: 字符限制
            language: 语言代码

        Returns:
            输出文件路径
        """
        workflow_id = self.context.workflow_id

        # 生成输出文件路径
        output_file = build_node_output_path(
            task_id=workflow_id,
            node_name=self.stage_name,
            file_type="data",
            filename="segmented_subtitles.json"
        )
        ensure_directory(output_file)

        # 构建输出数据
        output_data = {
            "method": "PySBD + LangChain",
            "language": language,
            "max_chars": max_chars,
            "total_segments": result["total_segments"],
            "statistics": result["statistics"],
            "segments": [asdict(seg) for seg in result["segments"]]
        }

        # 保存到文件
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        logger.info(f"[{workflow_id}] 分句结果已保存: {output_file}")

        return output_file

    def _save_pysbd_result(
        self,
        pysbd_segments: List[SubtitleSegment],
        language: str
    ) -> str:
        """
        保存 PySBD 原始分句结果到 JSON 文件（不经过 LangChain 字符限制处理）。

        Args:
            pysbd_segments: PySBD 原始分句列表
            language: 语言代码

        Returns:
            输出文件路径
        """
        workflow_id = self.context.workflow_id

        # 生成输出文件路径
        output_file = build_node_output_path(
            task_id=workflow_id,
            node_name=self.stage_name,
            file_type="data",
            filename="segmented_subtitles_pysbd.json"
        )
        ensure_directory(output_file)

        # 构建输出数据
        output_data = {
            "method": "PySBD (without LangChain)",
            "language": language,
            "total_segments": len(pysbd_segments),
            "segments": [asdict(seg) for seg in pysbd_segments]
        }

        # 保存到文件
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        logger.info(f"[{workflow_id}] PySBD 原始分句结果已保存: {output_file}")

        return output_file

    def get_cache_key_fields(self) -> List[str]:
        """
        返回缓存键字段列表。

        Returns:
            缓存键字段列表
        """
        return [
            "subtitle_text",
            "subtitle_file",
            "max_chars",
            "language",
            "text_json_path",
            "words_json_path"
        ]

    def get_required_output_fields(self) -> List[str]:
        """
        返回必需的输出字段列表。

        Returns:
            输出字段列表
        """
        return ["segmented_subtitle_file", "segmented_subtitle_pysbd_file"]

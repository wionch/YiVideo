# services/workers/ffmpeg_service/app/modules/audio_splitter.py
# -*- coding: utf-8 -*-

"""
音频分割模块

提供基于字幕时间戳的音频分割功能，使用ffmpeg进行精确的音频片段提取。
支持多种音频格式和批量处理。
"""

import os
import subprocess
import json
import logging
import re
from typing import List, Dict, Optional, Union
from pathlib import Path
from dataclasses import dataclass, asdict
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from services.common.subtitle.subtitle_parser import SubtitleEntry as SubtitleSegment, parse_subtitle_file

logger = logging.getLogger(__name__)


@dataclass
class AudioSegmentInfo:
    """音频片段信息数据结构"""
    id: int                    # 片段ID
    start_time: float          # 开始时间（秒）
    end_time: float            # 结束时间（秒）
    duration: float            # 持续时间（秒）
    text: str                  # 对应的字幕文本
    speaker: Optional[str] = None     # 说话人
    file_path: Optional[str] = None   # 生成的音频文件路径
    file_size: Optional[int] = None   # 文件大小（字节）
    confidence: Optional[float] = None # 置信度
    words: Optional[List[Dict]] = None # 词级时间戳


@dataclass
class SplitResult:
    """音频分割结果数据结构"""
    total_segments: int                        # 总片段数
    successful_segments: int                   # 成功分割的片段数
    failed_segments: int                       # 失败的片段数
    total_duration: float                      # 总时长
    output_directory: str                      # 输出目录
    audio_format: str                          # 音频格式
    sample_rate: int                           # 采样率
    channels: int                              # 声道数
    segments: List[AudioSegmentInfo]           # 片段信息列表
    speaker_groups: Optional[Dict[str, List[AudioSegmentInfo]]] = None  # 按说话人分组
    split_info_file: Optional[str] = None      # 分割信息文件路径
    processing_time: Optional[float] = None    # 处理时间（秒）


class AudioSplitter:
    """音频分割器"""

    def __init__(
        self,
        output_format: str = "wav",
        sample_rate: int = 16000,
        channels: int = 1,
        min_segment_duration: float = 0.5,
        max_segment_duration: float = 30.0,
        ffmpeg_timeout: int = 300,
        enable_concurrent: bool = True,
        max_workers: int = 8,
        concurrent_timeout: int = 600
    ):
        """
        初始化音频分割器

        Args:
            output_format: 输出音频格式 (wav, flac, mp3)
            sample_rate: 采样率
            channels: 声道数
            min_segment_duration: 最小片段时长（秒）
            max_segment_duration: 最大片段时长（秒）
            ffmpeg_timeout: ffmpeg命令超时时间（秒）
            enable_concurrent: 是否启用并发分割
            max_workers: 最大并发线程数
            concurrent_timeout: 并发操作总超时时间（秒）
        """
        self.output_format = output_format.lower()
        self.sample_rate = sample_rate
        self.channels = channels
        self.min_segment_duration = min_segment_duration
        self.max_segment_duration = max_segment_duration
        self.ffmpeg_timeout = ffmpeg_timeout
        self.enable_concurrent = enable_concurrent
        self.max_workers = max_workers
        self.concurrent_timeout = concurrent_timeout

        # 验证音频格式
        supported_formats = ["wav", "flac", "mp3", "aac", "m4a"]
        if self.output_format not in supported_formats:
            raise ValueError(f"不支持的音频格式: {output_format}. 支持的格式: {supported_formats}")

        # 检查ffmpeg是否可用
        self._check_ffmpeg_availability()

    def _check_ffmpeg_availability(self) -> None:
        """检查ffmpeg命令是否可用"""
        try:
            from services.common.subprocess_utils import run_with_popen
            
            result = run_with_popen(
                ["ffmpeg", "-version"],
                stage_name="ffmpeg_availability_check",
                timeout=10,
                capture_output=True
            )
            if result.returncode != 0:
                raise RuntimeError("ffmpeg命令执行失败")
            logger.info("ffmpeg命令检查通过")
        except FileNotFoundError:
            raise RuntimeError("ffmpeg命令未找到，请确保ffmpeg已安装并在PATH中")
        except Exception as e:
            raise RuntimeError(f"ffmpeg检查失败: {e}")

    def _generate_filename(
        self,
        segment: SubtitleSegment,
        output_dir: str,
        prefix: str = "segment"
    ) -> str:
        """
        生成音频文件名

        Args:
            segment: 字幕片段
            output_dir: 输出目录
            prefix: 文件名前缀

        Returns:
            str: 生成的文件路径
        """
        # 格式：segment_001_Speaker_00.wav
        speaker_suffix = ""
        if segment.speaker:
            # 清理说话人标签，移除特殊字符
            speaker_clean = re.sub(r'[^\w]', '_', segment.speaker)
            speaker_suffix = f"_{speaker_clean}"

        filename = f"{prefix}_{segment.id:03d}{speaker_suffix}.{self.output_format}"
        return os.path.join(output_dir, filename)

    def _generate_filename_safe(
        self,
        segment: SubtitleSegment,
        output_dir: str,
        prefix: str = "segment",
        lock: Optional[threading.Lock] = None
    ) -> str:
        """
        线程安全的音频文件名生成方法

        Args:
            segment: 字幕片段
            output_dir: 输出目录
            prefix: 文件名前缀
            lock: 线程锁（可选）

        Returns:
            str: 生成的文件路径
        """
        if lock:
            with lock:
                return self._generate_filename(segment, output_dir, prefix)
        else:
            return self._generate_filename(segment, output_dir, prefix)

    def _extract_segment(
        self,
        input_audio: str,
        segment: SubtitleSegment,
        output_file: str
    ) -> Optional[Dict]:
        """
        使用ffmpeg提取单个音频片段

        Args:
            input_audio: 输入音频文件路径
            segment: 字幕片段
            output_file: 输出音频文件路径

        Returns:
            Optional[Dict]: 提取结果信息，失败时返回None
        """
        try:
            # 确保输出目录存在
            os.makedirs(os.path.dirname(output_file), exist_ok=True)

            # 构建ffmpeg命令
            command = [
                "ffmpeg",
                "-i", input_audio,
                "-ss", str(segment.start_time),
                "-t", str(segment.duration),
                "-vn",  # 不包含视频
                "-acodec", self._get_audio_codec(),
                "-ar", str(self.sample_rate),
                "-ac", str(self.channels),
                "-y",  # 覆盖输出文件
                "-loglevel", "error",  # 只显示错误信息
                output_file
            ]

            # 执行ffmpeg命令（升级为实时日志版本）
            start_time = time.time()
            from services.common.subprocess_utils import run_with_popen
            
            result = run_with_popen(
                command,
                stage_name=f"audio_splitter_segment_{segment.id}",
                timeout=self.ffmpeg_timeout,
                capture_output=True
            )
            processing_time = time.time() - start_time

            # 检查执行结果
            if result.returncode != 0:
                logger.error(f"ffmpeg执行失败: {result.stderr}")
                return None

            # 检查输出文件
            if not os.path.exists(output_file):
                logger.error(f"输出文件不存在: {output_file}")
                return None

            # 检查文件大小
            file_size = os.path.getsize(output_file)
            if file_size == 0:
                logger.error(f"输出文件为空: {output_file}")
                return None

            # 成功提取
            logger.debug(f"成功提取片段 {segment.id}: {segment.start_time:.2f}-{segment.end_time:.2f}s, "
                        f"文件: {output_file}, 大小: {file_size} bytes, 耗时: {processing_time:.2f}s")

            return {
                "file_path": output_file,
                "file_size": file_size,
                "processing_time": processing_time
            }

        except subprocess.TimeoutExpired:
            logger.error(f"ffmpeg命令超时: 片段 {segment.id}")
            return None
        except Exception as e:
            logger.error(f"提取音频片段失败: 片段 {segment.id}, 错误: {e}")
            return None

    def _get_audio_codec(self) -> str:
        """
        根据输出格式获取音频编码器

        Returns:
            str: ffmpeg音频编码器名称
        """
        codec_map = {
            "wav": "pcm_s16le",
            "flac": "flac",
            "mp3": "libmp3lame",
            "aac": "aac",
            "m4a": "aac"
        }
        return codec_map.get(self.output_format, "pcm_s16le")

    def _extract_segment_worker(
        self,
        args: tuple
    ) -> tuple:
        """
        并发工作线程：处理单个音频片段的提取

        Args:
            args: 包含 (input_audio, segment, output_file) 的元组

        Returns:
            tuple: (segment_id, extract_result or None)
        """
        input_audio, segment, output_file = args
        try:
            extract_result = self._extract_segment(input_audio, segment, output_file)
            return (segment.id, extract_result, None)
        except Exception as e:
            logger.error(f"工作线程处理片段 {segment.id} 时发生异常: {e}")
            return (segment.id, None, str(e))

    def _split_audio_segments_concurrent(
        self,
        input_audio: str,
        segments: List[SubtitleSegment],
        output_dir: str,
        group_by_speaker: bool = False,
        progress_callback: Optional[callable] = None
    ) -> tuple:
        """
        并发分割音频片段

        Args:
            input_audio: 输入音频文件路径
            segments: 字幕片段列表
            output_dir: 输出目录
            group_by_speaker: 是否按说话人分组
            progress_callback: 进度回调函数

        Returns:
            tuple: (successful_segments, failed_segments)
        """
        logger.info(f"开始并发音频分割: {len(segments)} 个片段，最大并发数: {self.max_workers}")

        # 准备工作参数
        work_items = []
        for segment in segments:
            # 确定输出文件路径
            if group_by_speaker and segment.speaker:
                segment_dir = os.path.join(output_dir, "by_speaker", segment.speaker)
            else:
                segment_dir = os.path.join(output_dir, "segments")

            os.makedirs(segment_dir, exist_ok=True)
            output_file = self._generate_filename(segment, segment_dir)
            work_items.append((input_audio, segment, output_file))

        # 使用线程池并发处理
        successful_segments = []
        failed_segments = []
        completed_count = 0

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有任务
            future_to_segment = {
                executor.submit(self._extract_segment_worker, item): item[1]
                for item in work_items
            }

            # 处理完成的任务
            for future in as_completed(future_to_segment, timeout=self.concurrent_timeout):
                segment = future_to_segment[future]
                completed_count += 1

                try:
                    segment_id, extract_result, error = future.result()

                    if extract_result:
                        # 创建音频片段信息
                        original_segment = next(s for s in segments if s.id == segment_id)
                        audio_info = AudioSegmentInfo(
                            id=original_segment.id,
                            start_time=original_segment.start_time,
                            end_time=original_segment.end_time,
                            duration=original_segment.duration,
                            text=original_segment.text,
                            speaker=original_segment.speaker,
                            file_path=extract_result["file_path"],
                            file_size=extract_result["file_size"],
                            confidence=original_segment.confidence,
                            words=original_segment.words
                        )
                        successful_segments.append(audio_info)
                    else:
                        failed_segments.append(segment_id)
                        if error:
                            logger.error(f"片段 {segment_id} 分割失败: {error}")

                except Exception as e:
                    logger.error(f"处理片段 {segment.id} 的future时发生异常: {e}")
                    failed_segments.append(segment.id)

                # 调用进度回调
                if progress_callback:
                    try:
                        progress_callback(completed_count, len(segments), segment.id, extract_result is not None)
                    except Exception as e:
                        logger.warning(f"进度回调函数执行失败: {e}")

        logger.info(f"并发分割完成: 成功 {len(successful_segments)}, 失败 {len(failed_segments)}")
        return successful_segments, failed_segments

    def split_audio_by_segments(
        self,
        input_audio: str,
        segments: List[SubtitleSegment],
        output_dir: str,
        group_by_speaker: bool = False,
        include_silence: bool = False,
        progress_callback: Optional[callable] = None
    ) -> SplitResult:
        """
        根据字幕片段分割音频

        Args:
            input_audio: 输入音频文件路径
            segments: 字幕片段列表
            output_dir: 输出目录
            group_by_speaker: 是否按说话人分组
            include_silence: 是否包含静音段
            progress_callback: 进度回调函数

        Returns:
            SplitResult: 分割结果
        """
        start_time = time.time()

        # 验证输入文件
        if not os.path.exists(input_audio):
            raise FileNotFoundError(f"输入音频文件不存在: {input_audio}")

        # 过滤片段
        filtered_segments = []
        for segment in segments:
            if self.min_segment_duration <= segment.duration <= self.max_segment_duration:
                filtered_segments.append(segment)
            elif include_silence and segment.duration < self.min_segment_duration:
                # 如果包含静音段且时长过短，可以扩展到最小时长
                filtered_segments.append(segment)
            else:
                logger.debug(f"跳过时长不符合要求的片段: {segment.id}, 时长: {segment.duration:.2f}s")

        if not filtered_segments:
            logger.warning("没有符合条件的音频片段")
            return SplitResult(
                total_segments=0,
                successful_segments=0,
                failed_segments=0,
                total_duration=0.0,
                output_directory=output_dir,
                audio_format=self.output_format,
                sample_rate=self.sample_rate,
                channels=self.channels,
                segments=[]
            )

        logger.info(f"开始音频分割: {len(filtered_segments)} 个片段")
        logger.info(f"输入音频: {input_audio}")
        logger.info(f"输出目录: {output_dir}")
        logger.info(f"音频格式: {self.output_format}, 采样率: {self.sample_rate}, 声道: {self.channels}")

        # 创建输出目录结构
        if group_by_speaker:
            # 按说话人创建子目录
            speakers = set(seg.speaker for seg in filtered_segments if seg.speaker)
            for speaker in speakers:
                speaker_dir = os.path.join(output_dir, "by_speaker", speaker)
                os.makedirs(speaker_dir, exist_ok=True)

        # 分割音频片段 - 根据配置选择串行或并发处理
        successful_segments = []
        failed_segments = []

        if self.enable_concurrent and len(filtered_segments) > 1:
            # 并发处理
            logger.info(f"使用并发模式处理 {len(filtered_segments)} 个音频片段")
            successful_segments, failed_segments = self._split_audio_segments_concurrent(
                input_audio=input_audio,
                segments=filtered_segments,
                output_dir=output_dir,
                group_by_speaker=group_by_speaker,
                progress_callback=progress_callback
            )
        else:
            # 串行处理（原始逻辑）
            if self.enable_concurrent and len(filtered_segments) <= 1:
                logger.info("片段数量 <= 1，使用串行模式")
            else:
                logger.info(f"使用串行模式处理 {len(filtered_segments)} 个音频片段")

            for i, segment in enumerate(filtered_segments):
                try:
                    # 确定输出文件路径
                    if group_by_speaker and segment.speaker:
                        segment_dir = os.path.join(output_dir, "by_speaker", segment.speaker)
                    else:
                        segment_dir = os.path.join(output_dir, "segments")

                    os.makedirs(segment_dir, exist_ok=True)
                    output_file = self._generate_filename(segment, segment_dir)

                    # 提取音频片段
                    extract_result = self._extract_segment(input_audio, segment, output_file)

                    if extract_result:
                        # 创建音频片段信息
                        audio_info = AudioSegmentInfo(
                            id=segment.id,
                            start_time=segment.start_time,
                            end_time=segment.end_time,
                            duration=segment.duration,
                            text=segment.text,
                            speaker=segment.speaker,
                            file_path=extract_result["file_path"],
                            file_size=extract_result["file_size"],
                            confidence=segment.confidence,
                            words=segment.words
                        )
                        successful_segments.append(audio_info)
                    else:
                        failed_segments.append(segment.id)

                    # 调用进度回调
                    if progress_callback:
                        progress_callback(i + 1, len(filtered_segments), segment.id, extract_result is not None)

                except Exception as e:
                    logger.error(f"处理片段 {segment.id} 时发生异常: {e}")
                    failed_segments.append(segment.id)

        # 计算总时长
        total_duration = sum(seg.duration for seg in filtered_segments)
        processing_time = time.time() - start_time

        # 创建结果对象
        result = SplitResult(
            total_segments=len(filtered_segments),
            successful_segments=len(successful_segments),
            failed_segments=len(failed_segments),
            total_duration=total_duration,
            output_directory=output_dir,
            audio_format=self.output_format,
            sample_rate=self.sample_rate,
            channels=self.channels,
            segments=successful_segments,
            processing_time=processing_time
        )

        # 按说话人分组
        if group_by_speaker:
            speaker_groups = {}
            for segment in successful_segments:
                speaker = segment.speaker or "UNKNOWN"
                if speaker not in speaker_groups:
                    speaker_groups[speaker] = []
                speaker_groups[speaker].append(segment)
            result.speaker_groups = speaker_groups

        # 生成分割信息文件
        result.split_info_file = self._save_split_info(result, output_dir)

        # 记录统计信息
        logger.info(f"音频分割完成:")
        logger.info(f"  总片段数: {result.total_segments}")
        logger.info(f"  成功分割: {result.successful_segments}")
        logger.info(f"  失败分割: {result.failed_segments}")
        logger.info(f"  总时长: {result.total_duration:.2f}s")
        logger.info(f"  处理时间: {result.processing_time:.2f}s")
        logger.info(f"  平均处理速度: {result.total_duration/result.processing_time:.2f}x")

        if result.failed_segments > 0:
            logger.warning(f"失败的片段ID: {failed_segments}")

        return result

    def _save_split_info(self, result: SplitResult, output_dir: str) -> str:
        """
        保存分割信息到JSON文件

        Args:
            result: 分割结果
            output_dir: 输出目录

        Returns:
            str: 信息文件路径
        """
        try:
            info_file = os.path.join(output_dir, "split_info.json")

            # 准备数据
            info_data = {
                "metadata": {
                    "total_segments": result.total_segments,
                    "successful_segments": result.successful_segments,
                    "failed_segments": result.failed_segments,
                    "success_rate": result.successful_segments / result.total_segments if result.total_segments > 0 else 0,
                    "total_duration": result.total_duration,
                    "processing_time": result.processing_time,
                    "processing_speed": result.total_duration / result.processing_time if result.processing_time > 0 else 0,
                    "audio_format": result.audio_format,
                    "sample_rate": result.sample_rate,
                    "channels": result.channels,
                    "output_directory": result.output_directory,
                    "created_at": time.time()
                },
                "segments": []
            }

            # 添加片段信息
            for segment in result.segments:
                segment_data = asdict(segment)
                # 移除None值
                segment_data = {k: v for k, v in segment_data.items() if v is not None}
                info_data["segments"].append(segment_data)

            # 添加说话人统计
            if result.speaker_groups:
                speaker_stats = {}
                for speaker, segments in result.speaker_groups.items():
                    total_duration = sum(seg.duration for seg in segments)
                    speaker_stats[speaker] = {
                        "count": len(segments),
                        "duration": total_duration,
                        "files": [seg.file_path for seg in segments if seg.file_path]
                    }
                info_data["speaker_groups"] = speaker_stats

            # 写入文件
            with open(info_file, 'w', encoding='utf-8') as f:
                json.dump(info_data, f, ensure_ascii=False, indent=2)

            logger.info(f"分割信息已保存到: {info_file}")
            return info_file

        except Exception as e:
            logger.error(f"保存分割信息失败: {e}")
            return None


def split_audio_segments(
    input_audio: str,
    subtitle_file: str,
    output_dir: str,
    **kwargs
) -> SplitResult:
    """
    便捷函数：分割音频片段

    Args:
        input_audio: 输入音频文件路径
        subtitle_file: 字幕文件路径
        output_dir: 输出目录
        **kwargs: 额外参数
            - output_format: 音频格式 (默认: wav)
            - sample_rate: 采样率 (默认: 16000)
            - channels: 声道数 (默认: 1)
            - min_segment_duration: 最小片段时长 (默认: 0.5)
            - max_segment_duration: 最大片段时长 (默认: 30.0)
            - group_by_speaker: 是否按说话人分组 (默认: False)
            - include_silence: 是否包含静音段 (默认: False)

    Returns:
        SplitResult: 分割结果
    """
    # 解析字幕文件
    segments = parse_subtitle_file(subtitle_file)
    if not segments:
        raise ValueError(f"无法解析字幕文件或文件为空: {subtitle_file}")

    # 创建音频分割器
    splitter = AudioSplitter(
        output_format=kwargs.get('output_format', 'wav'),
        sample_rate=kwargs.get('sample_rate', 16000),
        channels=kwargs.get('channels', 1),
        min_segment_duration=kwargs.get('min_segment_duration', 0.5),
        max_segment_duration=kwargs.get('max_segment_duration', 30.0)
    )

    # 执行分割
    return splitter.split_audio_by_segments(
        input_audio=input_audio,
        segments=segments,
        output_dir=output_dir,
        group_by_speaker=kwargs.get('group_by_speaker', False),
        include_silence=kwargs.get('include_silence', False)
    )
# -*- coding: utf-8 -*-

"""
Qwen3-ASR 转录执行器。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple
from services.common.base_node_executor import BaseNodeExecutor


def map_language(language: str | None) -> str | None:
    """将短码映射为 Qwen3-ASR 认可的语言标识。"""
    if language is None:
        return None
    lang = str(language).strip()
    if not lang:
        return None
    low = lang.lower()
    if low in {"auto"}:
        return None
    if low in {"zh", "zh-cn", "cn"}:
        return "Chinese"
    if low in {"en", "en-us"}:
        return "English"
    return lang


def map_words(time_stamps: List[Dict[str, Any]] | None, enable: bool) -> Tuple[list, int]:
    """将时间戳列表映射为 words 结构。"""
    if not enable:
        return [], 0
    if not time_stamps:
        return [], 0
    words = []
    for item in time_stamps:
        words.append({
            "word": item.get("text", ""),
            "start": item.get("start", 0.0),
            "end": item.get("end", 0.0),
            "probability": None,
        })
    return words, len(words)


def build_infer_command(
    audio_path: str,
    output_file: str,
    model_name: str,
    backend: str,
    language: str | None,
    enable_word_timestamps: bool,
    forced_aligner_model: str | None,
) -> list[str]:
    """构建 subprocess 推理命令。"""
    infer_script = Path(__file__).resolve().parents[1] / "app" / "qwen3_asr_infer.py"
    cmd = [
        sys.executable,
        str(infer_script),
        "--audio_path", audio_path,
        "--output_file", output_file,
        "--model_name", model_name,
        "--backend", backend,
    ]
    if language:
        cmd += ["--language", language]
    if enable_word_timestamps:
        cmd += ["--enable_word_timestamps"]
    if forced_aligner_model:
        cmd += ["--forced_aligner_model", forced_aligner_model]
    return cmd


def build_transcribe_json(
    stage_name: str,
    workflow_id: str,
    audio_file_name: str,
    segments: List[Dict[str, Any]],
    audio_duration: float,
    language: str,
    model_name: str,
    device: str,
    enable_word_timestamps: bool,
    transcribe_duration: float,
) -> Dict[str, Any]:
    total_segments = len(segments)
    total_words = sum(len(seg.get("words", [])) for seg in segments)
    avg_duration = 0
    if total_segments > 0:
        avg_duration = sum(seg.get("end", 0) - seg.get("start", 0) for seg in segments) / total_segments
    return {
        "metadata": {
            "task_name": stage_name,
            "workflow_id": workflow_id,
            "audio_file": audio_file_name,
            "total_duration": audio_duration,
            "language": language,
            "word_timestamps_enabled": enable_word_timestamps,
            "model_name": model_name,
            "device": device,
            "transcribe_method": "qwen3-asr-subprocess",
            "created_at": time.time(),
        },
        "segments": segments,
        "statistics": {
            "total_segments": total_segments,
            "total_words": total_words,
            "transcribe_duration": transcribe_duration,
            "average_segment_duration": avg_duration,
        },
    }


class Qwen3ASRTranscribeExecutor(BaseNodeExecutor):
    """Qwen3-ASR 语音转录执行器。"""

    def validate_input(self) -> None:
        input_data = self.get_input_data()
        if not input_data.get("audio_path"):
            raise ValueError("缺少必需参数: audio_path")

    def execute_core_logic(self) -> Dict[str, Any]:
        raise NotImplementedError("尚未实现核心转录逻辑")

    def get_cache_key_fields(self) -> List[str]:
        return []

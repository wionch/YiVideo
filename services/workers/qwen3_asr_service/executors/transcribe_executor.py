# -*- coding: utf-8 -*-

"""
Qwen3-ASR 转录执行器。
"""

from __future__ import annotations

import os
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from services.common.base_node_executor import BaseNodeExecutor
from services.common.config_loader import CONFIG
from services.common.file_service import get_file_service
from services.common.locks import gpu_lock
from services.common.path_builder import build_node_output_path, ensure_directory
from services.common.subprocess_utils import run_gpu_command


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


def _read_infer_output(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        raise RuntimeError(f"推理输出不存在: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _build_segments(text: str, time_stamps: List[Dict[str, Any]] | None, audio_duration: float, enable_words: bool):
    words, _ = map_words(time_stamps, enable=enable_words)
    if words:
        start = words[0].get("start", 0.0)
        end = words[-1].get("end", audio_duration)
    else:
        start = 0.0
        end = audio_duration
    segment = {
        "id": 0,
        "start": start,
        "end": end,
        "text": text or "",
    }
    if enable_words:
        segment["words"] = words
    return [segment]


def _run_infer(cmd: list[str], stage_name: str, cwd: str) -> Dict[str, Any]:
    result = run_gpu_command(cmd, stage_name=stage_name, timeout=1800, cwd=cwd)
    if result.returncode != 0:
        raise RuntimeError(f"subprocess 失败: {result.stderr}")
    return _read_infer_output(cmd[cmd.index("--output_file") + 1])


@gpu_lock()
def _run_infer_with_gpu_lock(cmd: list[str], stage_name: str, cwd: str) -> Dict[str, Any]:
    return _run_infer(cmd, stage_name, cwd)


class Qwen3ASRTranscribeExecutor(BaseNodeExecutor):
    """Qwen3-ASR 语音转录执行器。"""

    def validate_input(self) -> None:
        input_data = self.get_input_data()
        if not input_data.get("audio_path"):
            raise ValueError("缺少必需参数: audio_path")

    def execute_core_logic(self) -> Dict[str, Any]:
        input_data = self.get_input_data()
        audio_path = input_data["audio_path"]

        file_service = get_file_service()
        audio_path = file_service.resolve_and_download(audio_path, self.context.shared_storage_path)
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")

        service_config = CONFIG.get("qwen3_asr_service", {})
        backend = input_data.get("backend", service_config.get("backend", "vllm"))
        model_size = input_data.get("model_size", service_config.get("model_size", "0.6B"))
        language = map_language(input_data.get("language", service_config.get("language")))
        enable_word_timestamps = input_data.get(
            "enable_word_timestamps", service_config.get("enable_word_timestamps", True)
        )
        forced_aligner_model = input_data.get(
            "forced_aligner_model",
            service_config.get("forced_aligner_model", "Qwen/Qwen3-ForcedAligner-0.6B"),
        )
        device = input_data.get("device", service_config.get("device", "cuda"))

        if device == "cpu" and backend == "vllm":
            raise ValueError("CPU 模式不支持 vllm 后端")
        if device == "cpu" and "backend" not in input_data:
            backend = "transformers"

        task_id = self.context.workflow_id
        tmp_dir = f"/share/workflows/{task_id}/tmp"
        os.makedirs(tmp_dir, exist_ok=True)
        output_file = Path(tmp_dir) / f"qwen3_asr_result_{int(time.time() * 1000)}.json"

        model_name = f"Qwen/Qwen3-ASR-{model_size}"
        cmd = build_infer_command(
            audio_path=audio_path,
            output_file=str(output_file),
            model_name=model_name,
            backend=backend,
            language=language,
            enable_word_timestamps=enable_word_timestamps,
            forced_aligner_model=forced_aligner_model if enable_word_timestamps else None,
        )

        payload = (
            _run_infer_with_gpu_lock(cmd, self.stage_name, str(Path(__file__).parent))
            if device != "cpu"
            else _run_infer(cmd, self.stage_name, str(Path(__file__).parent))
        )

        segments = _build_segments(
            text=payload.get("text", ""),
            time_stamps=payload.get("time_stamps"),
            audio_duration=payload.get("audio_duration") or 0,
            enable_words=enable_word_timestamps,
        )

        transcribe_data = build_transcribe_json(
            stage_name=self.stage_name,
            workflow_id=self.context.workflow_id,
            audio_file_name=os.path.basename(audio_path),
            segments=segments,
            audio_duration=payload.get("audio_duration") or 0,
            language=payload.get("language") or (language or "unknown"),
            model_name=model_name,
            device=device,
            enable_word_timestamps=enable_word_timestamps,
            transcribe_duration=payload.get("transcribe_duration") or 0,
        )

        workflow_short_id = self.context.workflow_id[:8]
        segments_file = build_node_output_path(
            task_id=self.context.workflow_id,
            node_name=self.stage_name,
            file_type="data",
            filename=f"transcribe_data_{workflow_short_id}.json",
        )
        ensure_directory(segments_file)
        with open(segments_file, "w", encoding="utf-8") as f:
            json.dump(transcribe_data, f, ensure_ascii=False, indent=2)

        return {
            "segments_file": segments_file,
            "audio_duration": payload.get("audio_duration") or 0,
            "language": payload.get("language") or (language or "unknown"),
            "model_name": model_name,
            "device": device,
            "enable_word_timestamps": enable_word_timestamps,
            "statistics": transcribe_data["statistics"],
            "segments_count": len(segments),
        }

    def get_cache_key_fields(self) -> List[str]:
        return [
            "audio_path",
            "backend",
            "model_size",
            "language",
            "enable_word_timestamps",
        ]

    def get_required_output_fields(self) -> List[str]:
        return ["segments_file"]

# -*- coding: utf-8 -*-

"""
Qwen3-ASR 转录执行器。

职责范围：
- 调用 Qwen3-ASR 模型进行语音转录
- 返回原始 ASR 识别结果（文本、时间戳、语言等）
- 不进行任何分句处理（交由下游 wservice.segment_subtitles 节点负责）
"""

from __future__ import annotations

import os
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

from services.common.base_node_executor import BaseNodeExecutor
from services.common.config_loader import CONFIG
from services.common.file_service import get_file_service
from services.common.locks import gpu_lock
from services.common.logger import get_logger
from services.common.path_builder import build_node_output_path, ensure_directory
from services.common.subprocess_utils import run_gpu_command

logger = get_logger(__name__)


_PARAM_RANGES = {
    "max_model_len": (4096, 131072),
    "gpu_memory_utilization": (0.1, 0.95),
}


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


def _parse_numeric_param(
    name: str,
    raw_value: Any,
    default_value: Any,
    min_value: float | None,
    max_value: float | None,
    cast_type: type,
) -> Any:
    if raw_value is None:
        return default_value
    if isinstance(raw_value, bool):
        logger.warning(f"[qwen3_asr] 参数 {name} 类型无效，已回退默认值")
        return default_value
    try:
        value = cast_type(raw_value)
    except (TypeError, ValueError):
        logger.warning(f"[qwen3_asr] 参数 {name} 类型无效，已回退默认值")
        return default_value
    if min_value is not None and value < min_value:
        logger.warning(f"[qwen3_asr] 参数 {name} 超出范围，已回退默认值")
        return default_value
    if max_value is not None and value > max_value:
        logger.warning(f"[qwen3_asr] 参数 {name} 超出范围，已回退默认值")
        return default_value
    return value


def _resolve_audio_duration(audio_duration: float | None, time_stamps: List[Dict[str, Any]] | None) -> float:
    """
    解析音频时长。

    优先级：
    1. 模型返回的 audio_duration
    2. 最后一个时间戳的 end 时间
    3. 0.0
    """
    if audio_duration and audio_duration > 0:
        return audio_duration
    if time_stamps:
        try:
            last_end = float(time_stamps[-1].get("end", 0.0))
            return last_end if last_end > 0 else 0.0
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def build_infer_command(
    audio_path: str,
    output_file: str,
    model_name: str,
    backend: str,
    language: str | None,
    enable_word_timestamps: bool,
    forced_aligner_model: str | None,
    max_model_len: int | None,
    gpu_memory_utilization: float | None,
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
    if max_model_len is not None:
        cmd += ["--max_model_len", str(max_model_len)]
    if gpu_memory_utilization is not None:
        cmd += ["--gpu_memory_utilization", str(gpu_memory_utilization)]
    return cmd


def _read_infer_output(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        raise RuntimeError(f"推理输出不存在: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _run_infer(cmd: list[str], stage_name: str, cwd: str) -> Dict[str, Any]:
    result = run_gpu_command(cmd, stage_name=stage_name, timeout=1800, cwd=cwd)
    if result.returncode != 0:
        raise RuntimeError(f"subprocess 失败: {result.stderr}")
    return _read_infer_output(cmd[cmd.index("--output_file") + 1])


@gpu_lock()
def _run_infer_with_gpu_lock(cmd: list[str], stage_name: str, cwd: str) -> Dict[str, Any]:
    return _run_infer(cmd, stage_name, cwd)


class Qwen3ASRTranscribeExecutor(BaseNodeExecutor):
    """
    Qwen3-ASR 语音转录执行器。

    职责：
    - 调用 Qwen3-ASR 模型进行语音转录
    - 返回原始识别结果（text, time_stamps, language, audio_duration）

    不负责：
    - 字幕分句（交由 wservice.segment_subtitles 节点负责）
    - 字符限制处理
    - 读速控制
    """

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
        max_model_len = _parse_numeric_param(
            "max_model_len",
            input_data.get("max_model_len", service_config.get("max_model_len")),
            service_config.get("max_model_len"),
            *_PARAM_RANGES["max_model_len"],
            int,
        )
        gpu_memory_utilization = _parse_numeric_param(
            "gpu_memory_utilization",
            input_data.get("gpu_memory_utilization", service_config.get("gpu_memory_utilization")),
            service_config.get("gpu_memory_utilization"),
            *_PARAM_RANGES["gpu_memory_utilization"],
            float,
        )

        if device == "cpu" and backend == "vllm":
            raise ValueError("CPU 模式不支持 vllm 后端")
        if device == "cpu" and "backend" not in input_data:
            backend = "transformers"
        if backend != "vllm":
            if input_data.get("max_model_len") is not None or input_data.get("gpu_memory_utilization") is not None:
                logger.warning("[qwen3_asr] 非 vLLM 后端忽略 max_model_len/gpu_memory_utilization")
            max_model_len = None
            gpu_memory_utilization = None

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
            max_model_len=max_model_len,
            gpu_memory_utilization=gpu_memory_utilization,
        )

        try:
            payload = (
                _run_infer_with_gpu_lock(cmd, self.stage_name, str(Path(__file__).parent))
                if device != "cpu"
                else _run_infer(cmd, self.stage_name, str(Path(__file__).parent))
            )

            audio_duration = _resolve_audio_duration(payload.get("audio_duration"), payload.get("time_stamps"))

            # 保存原始转录结果
            workflow_short_id = self.context.workflow_id[:8]
            transcribe_result_file = build_node_output_path(
                task_id=self.context.workflow_id,
                node_name=self.stage_name,
                file_type="data",
                filename=f"transcribe_result_{workflow_short_id}.json",
            )
            ensure_directory(transcribe_result_file)

            # 构建输出 JSON
            output_json = {
                "metadata": {
                    "task_name": self.stage_name,
                    "workflow_id": self.context.workflow_id,
                    "audio_file": os.path.basename(audio_path),
                    "model_name": model_name,
                    "backend": backend,
                    "device": device,
                    "language": payload.get("language") or (language or "unknown"),
                    "word_timestamps_enabled": enable_word_timestamps,
                    "transcribe_method": "qwen3-asr-subprocess",
                    "created_at": time.time(),
                },
                "text": payload.get("text", ""),
                "language": payload.get("language") or (language or "unknown"),
                "audio_duration": audio_duration,
                "time_stamps": payload.get("time_stamps"),
                "transcribe_duration": payload.get("transcribe_duration") or 0,
            }

            with open(transcribe_result_file, "w", encoding="utf-8") as f:
                json.dump(output_json, f, ensure_ascii=False, indent=2)
            logger.info(f"[{self.stage_name}] 转录结果已保存: {transcribe_result_file}")

            return {
                "transcribe_result_file": transcribe_result_file,
                "text": output_json["text"],
                "language": output_json["language"],
                "audio_duration": audio_duration,
                "time_stamps": output_json["time_stamps"],
                "word_timestamps_enabled": enable_word_timestamps,
                "model_name": model_name,
                "backend": backend,
                "device": device,
                "transcribe_duration": output_json["transcribe_duration"],
            }
        finally:
            # 确保临时文件被清理（无论成功或失败）
            try:
                if os.path.exists(output_file):
                    os.remove(output_file)
                    logger.debug(f"[{self.stage_name}] 已清理临时文件: {output_file}")
            except Exception as e:
                logger.warning(f"[{self.stage_name}] 清理临时文件失败: {e}")

    def get_cache_key_fields(self) -> List[str]:
        return [
            "audio_path",
            "backend",
            "model_size",
            "language",
            "enable_word_timestamps",
            "forced_aligner_model",
            "max_model_len",
            "gpu_memory_utilization",
        ]

    def get_required_output_fields(self) -> List[str]:
        return ["transcribe_result_file", "text"]

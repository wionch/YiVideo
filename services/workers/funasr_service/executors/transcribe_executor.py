from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from services.common.base_node_executor import BaseNodeExecutor
from services.common.config_loader import CONFIG
from services.common.file_service import get_file_service
from services.common.locks import gpu_lock
from services.common.logger import get_logger
from services.common.path_builder import build_node_output_path, ensure_directory
from services.common.subprocess_utils import run_gpu_command

logger = get_logger(__name__)

def map_words(time_stamps: List[Dict[str, Any]] | None, enable: bool) -> Tuple[list, int]:
    if not enable or not time_stamps:
        return [], 0
    words = []
    for item in time_stamps:
        words.append(
            {
                "word": item.get("text", ""),
                "start": item.get("start", 0.0),
                "end": item.get("end", 0.0),
                "probability": None,
            }
        )
    return words, len(words)


def normalize_speaker(speaker: str | None) -> str | None:
    if speaker is None:
        return None
    value = str(speaker).strip()
    return value or None


def build_segments(
    text: str, words: list, audio_duration: float, speaker: str | None
) -> List[Dict[str, Any]]:
    if words:
        start = words[0].get("start", 0.0)
        end = words[-1].get("end", audio_duration)
    else:
        start, end = 0.0, audio_duration
    segment = {
        "id": 0,
        "start": start,
        "end": end,
        "text": text or "",
    }
    if words:
        segment["words"] = words
    spk = normalize_speaker(speaker)
    if spk is not None:
        segment["speaker"] = spk
    return [segment]


def build_segments_from_payload(
    payload: Dict[str, Any], audio_duration: float, enable_word_timestamps: bool
) -> List[Dict[str, Any]]:
    segments = payload.get("segments") or []
    if segments:
        normalized = []
        for idx, seg in enumerate(segments):
            item = dict(seg)
            if "id" not in item:
                item["id"] = idx
            normalized.append(item)
        return normalized
    words, _ = map_words(payload.get("time_stamps"), enable=enable_word_timestamps)
    return build_segments(
        text=payload.get("text", ""),
        words=words,
        audio_duration=audio_duration,
        speaker=payload.get("speaker"),
    )


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
    funasr_metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    total_segments = len(segments)
    total_words = sum(len(seg.get("words", [])) for seg in segments)
    avg_duration = 0.0
    if total_segments > 0:
        avg_duration = (
            sum(seg.get("end", 0) - seg.get("start", 0) for seg in segments)
            / total_segments
        )
    metadata = {
        "task_name": stage_name,
        "workflow_id": workflow_id,
        "audio_file": audio_file_name,
        "total_duration": audio_duration,
        "language": language,
        "word_timestamps_enabled": enable_word_timestamps,
        "model_name": model_name,
        "device": device,
        "transcribe_method": "funasr-subprocess",
        "created_at": time.time(),
    }
    if funasr_metadata:
        metadata["funasr"] = funasr_metadata
    return {
        "metadata": metadata,
        "segments": segments,
        "statistics": {
            "total_segments": total_segments,
            "total_words": total_words,
            "transcribe_duration": transcribe_duration,
            "average_segment_duration": avg_duration,
        },
    }


def build_infer_command(
    audio_path: str,
    output_file: str,
    model_name: str,
    device: str,
    enable_word_timestamps: bool,
    vad_model: str | None,
    punc_model: str | None,
    spk_model: str | None,
    language: str | None,
    hotwords: list | None,
    batch_size_s: int | None,
    use_itn: bool | None,
    merge_vad: bool | None,
    merge_length_s: int | None,
    trust_remote_code: bool | None,
    remote_code: str | None,
    model_revision: str | None,
    vad_model_revision: str | None,
    punc_model_revision: str | None,
    spk_model_revision: str | None,
    lm_model: str | None,
    lm_weight: float | None,
    beam_size: int | None,
) -> list[str]:
    infer_script = Path(__file__).resolve().parents[1] / "app" / "funasr_infer.py"
    cmd = [
        sys.executable,
        str(infer_script),
        "--audio_path",
        audio_path,
        "--output_file",
        output_file,
        "--model_name",
        model_name,
        "--device",
        device,
    ]
    if enable_word_timestamps:
        cmd.append("--enable_word_timestamps")
    if vad_model:
        cmd += ["--vad_model", vad_model]
    if punc_model:
        cmd += ["--punc_model", punc_model]
    if spk_model:
        cmd += ["--spk_model", spk_model]
    if language:
        cmd += ["--language", language]
    if hotwords:
        cmd += ["--hotwords", ",".join(hotwords)]
    if batch_size_s is not None:
        cmd += ["--batch_size_s", str(batch_size_s)]
    if use_itn is not None:
        cmd += ["--use_itn", str(use_itn).lower()]
    if merge_vad is not None:
        cmd += ["--merge_vad", str(merge_vad).lower()]
    if merge_length_s is not None:
        cmd += ["--merge_length_s", str(merge_length_s)]
    if trust_remote_code is not None:
        cmd += ["--trust_remote_code", str(trust_remote_code).lower()]
    if remote_code:
        cmd += ["--remote_code", remote_code]
    if model_revision:
        cmd += ["--model_revision", model_revision]
    if vad_model_revision:
        cmd += ["--vad_model_revision", vad_model_revision]
    if punc_model_revision:
        cmd += ["--punc_model_revision", punc_model_revision]
    if spk_model_revision:
        cmd += ["--spk_model_revision", spk_model_revision]
    if lm_model:
        cmd += ["--lm_model", lm_model]
    if lm_weight is not None:
        cmd += ["--lm_weight", str(lm_weight)]
    if beam_size is not None:
        cmd += ["--beam_size", str(beam_size)]
    return cmd


def _read_infer_output(output_file: str) -> Dict[str, Any]:
    with open(output_file, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _run_infer(cmd: list[str], stage_name: str, cwd: str) -> Dict[str, Any]:
    result = run_gpu_command(cmd, stage_name=stage_name, timeout=1800, cwd=cwd)
    if result.returncode != 0:
        raise RuntimeError(f"subprocess 失败: {result.stderr}")
    output_path = cmd[cmd.index("--output_file") + 1]
    return _read_infer_output(output_path)


@gpu_lock()
def _run_infer_with_gpu_lock(cmd: list[str], stage_name: str, cwd: str) -> Dict[str, Any]:
    return _run_infer(cmd, stage_name, cwd)


def _normalize_hotwords(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return [str(item) for item in data if str(item).strip()]
        except Exception:
            pass
    if "," in text:
        return [item.strip() for item in text.split(",") if item.strip()]
    return [text]


class FunASRTranscribeExecutor(BaseNodeExecutor):
    """FunASR 语音转录执行器。"""

    def validate_input(self) -> None:
        input_data = self.get_input_data()
        if not input_data.get("audio_path"):
            raise ValueError("缺少必需参数: audio_path")

    def execute_core_logic(self) -> Dict[str, Any]:
        input_data = self.get_input_data()
        audio_path = input_data["audio_path"]

        file_service = get_file_service()
        audio_path = file_service.resolve_and_download(
            audio_path, self.context.shared_storage_path
        )
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")

        service_config = CONFIG.get("funasr_service", {})
        model_name = input_data.get("model_name", service_config.get("model_name", "paraformer-zh"))
        device = input_data.get("device", service_config.get("device", "cuda"))
        language = input_data.get("language", service_config.get("language"))
        enable_word_timestamps = input_data.get(
            "enable_word_timestamps", service_config.get("enable_word_timestamps", True)
        )

        vad_model = input_data.get("vad_model", service_config.get("vad_model"))
        punc_model = input_data.get("punc_model", service_config.get("punc_model"))
        spk_model = input_data.get("spk_model", service_config.get("spk_model"))
        hotwords = input_data.get(
            "hotwords",
            input_data.get("hotword", service_config.get("hotwords", service_config.get("hotword"))),
        )
        batch_size_s = input_data.get("batch_size_s", service_config.get("batch_size_s"))
        use_itn = input_data.get("use_itn", input_data.get("itn", service_config.get("use_itn")))
        merge_vad = input_data.get("merge_vad", service_config.get("merge_vad"))
        merge_length_s = input_data.get("merge_length_s", service_config.get("merge_length_s"))
        trust_remote_code = input_data.get(
            "trust_remote_code", service_config.get("trust_remote_code")
        )
        remote_code = input_data.get("remote_code", service_config.get("remote_code"))
        model_revision = input_data.get("model_revision", service_config.get("model_revision"))
        vad_model_revision = input_data.get(
            "vad_model_revision", service_config.get("vad_model_revision")
        )
        punc_model_revision = input_data.get(
            "punc_model_revision", service_config.get("punc_model_revision")
        )
        spk_model_revision = input_data.get(
            "spk_model_revision", service_config.get("spk_model_revision")
        )
        lm_model = input_data.get("lm_model", service_config.get("lm_model"))
        lm_weight = input_data.get("lm_weight", service_config.get("lm_weight"))
        beam_size = input_data.get("beam_size", service_config.get("beam_size"))

        warnings = []
        if model_name and "Fun-ASR-Nano" in model_name:
            if enable_word_timestamps:
                enable_word_timestamps = False
                warnings.append("Fun-ASR-Nano 暂不支持时间戳，已自动降级")
            if spk_model:
                spk_model = None
                warnings.append("Fun-ASR-Nano 暂不支持说话人识别，已自动降级")

        task_id = self.context.workflow_id
        tmp_dir = f"/share/workflows/{task_id}/tmp"
        os.makedirs(tmp_dir, exist_ok=True)
        output_file = os.path.join(tmp_dir, f"funasr_result_{int(time.time() * 1000)}.json")

        cmd = build_infer_command(
            audio_path=audio_path,
            output_file=output_file,
            model_name=model_name,
            device=device,
            enable_word_timestamps=enable_word_timestamps,
            vad_model=vad_model,
            punc_model=punc_model,
            spk_model=spk_model,
            language=language,
            hotwords=_normalize_hotwords(hotwords),
            batch_size_s=batch_size_s,
            use_itn=use_itn,
            merge_vad=merge_vad,
            merge_length_s=merge_length_s,
            trust_remote_code=trust_remote_code,
            remote_code=remote_code,
            model_revision=model_revision,
            vad_model_revision=vad_model_revision,
            punc_model_revision=punc_model_revision,
            spk_model_revision=spk_model_revision,
            lm_model=lm_model,
            lm_weight=lm_weight,
            beam_size=beam_size,
        )

        payload = (
            _run_infer_with_gpu_lock(cmd, self.stage_name, str(Path(__file__).parent))
            if device != "cpu"
            else _run_infer(cmd, self.stage_name, str(Path(__file__).parent))
        )

        audio_duration = payload.get("audio_duration") or 0
        segments = build_segments_from_payload(payload, audio_duration, enable_word_timestamps)
        funasr_metadata = {
            "vad_model": vad_model,
            "punc_model": punc_model,
            "spk_model": spk_model,
            "hotwords": _normalize_hotwords(hotwords),
            "warnings": warnings,
        }

        transcribe_data = build_transcribe_json(
            stage_name=self.stage_name,
            workflow_id=self.context.workflow_id,
            audio_file_name=os.path.basename(audio_path),
            segments=segments,
            audio_duration=audio_duration,
            language=payload.get("language") or (language or "unknown"),
            model_name=model_name,
            device=device,
            enable_word_timestamps=enable_word_timestamps,
            transcribe_duration=payload.get("transcribe_duration") or 0,
            funasr_metadata=funasr_metadata,
        )

        workflow_short_id = self.context.workflow_id[:8]
        segments_file = build_node_output_path(
            task_id=self.context.workflow_id,
            node_name=self.stage_name,
            file_type="data",
            filename=f"transcribe_data_{workflow_short_id}.json",
        )
        ensure_directory(segments_file)
        with open(segments_file, "w", encoding="utf-8") as handle:
            json.dump(transcribe_data, handle, ensure_ascii=False, indent=2)

        logger.info(
            f"[{self.stage_name}] 转录完成，segments={len(segments)}，模型={model_name}"
        )

        return {
            "segments_file": segments_file,
            "audio_duration": audio_duration,
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
            "model_name",
            "language",
            "enable_word_timestamps",
        ]

    def get_required_output_fields(self) -> List[str]:
        return ["segments_file"]

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple


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

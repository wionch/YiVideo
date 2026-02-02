from __future__ import annotations

import argparse
import json
import os
import time
from typing import Any, Dict


def normalize_model_output(raw: Dict[str, Any]) -> Dict[str, Any]:
    time_stamps = (
        raw.get("time_stamps")
        or raw.get("timestamp")
        or raw.get("time_stamp")
        or []
    )
    speaker = raw.get("speaker") or raw.get("spk")
    segments = []
    for idx, item in enumerate(raw.get("sentence_info", []) or raw.get("sentences", [])):
        seg = {
            "id": idx,
            "start": item.get("start", 0.0),
            "end": item.get("end", 0.0),
            "text": item.get("text", ""),
        }
        spk = item.get("speaker") or item.get("spk")
        if spk:
            seg["speaker"] = spk
        segments.append(seg)
    extra = raw.get("extra") or {}
    for key in ("lid", "ser", "aed"):
        if key in raw and key not in extra:
            extra[key] = raw[key]
    return {
        "text": raw.get("text", ""),
        "time_stamps": time_stamps,
        "segments": segments,
        "speaker": speaker,
        "extra": extra,
    }


def parse_hotwords(value: str | None) -> list:
    if value is None:
        return []
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


def build_infer_payload(
    text: str,
    language: str,
    audio_duration: float,
    time_stamps: list,
    segments: list,
    speaker: str | None,
    extra: dict | None,
    transcribe_duration: float,
) -> Dict[str, Any]:
    payload = {
        "text": text or "",
        "language": language or "unknown",
        "audio_duration": audio_duration,
        "time_stamps": time_stamps or [],
        "segments": segments or [],
        "speaker": speaker,
        "transcribe_duration": transcribe_duration,
    }
    if extra:
        payload["extra"] = extra
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="FunASR subprocess infer")
    parser.add_argument("--audio_path", required=True)
    parser.add_argument("--output_file", required=True)
    parser.add_argument("--model_name", required=True)
    parser.add_argument("--device", required=True)
    parser.add_argument("--enable_word_timestamps", action="store_true")
    parser.add_argument("--vad_model")
    parser.add_argument("--punc_model")
    parser.add_argument("--spk_model")
    parser.add_argument("--language")
    parser.add_argument("--hotwords")
    parser.add_argument("--batch_size_s", type=int)
    parser.add_argument("--use_itn")
    parser.add_argument("--merge_vad")
    parser.add_argument("--merge_length_s", type=int)
    parser.add_argument("--trust_remote_code")
    parser.add_argument("--remote_code")
    parser.add_argument("--model_revision")
    parser.add_argument("--vad_model_revision")
    parser.add_argument("--punc_model_revision")
    parser.add_argument("--spk_model_revision")
    parser.add_argument("--lm_model")
    parser.add_argument("--lm_weight", type=float)
    parser.add_argument("--beam_size", type=int)
    return parser.parse_args(argv)


def get_audio_duration(audio_path: str) -> float:
    try:
        import librosa

        return float(librosa.get_duration(path=audio_path))
    except Exception:
        return 0.0


def run_infer(args: argparse.Namespace, model_loader=None) -> Dict[str, Any]:
    start_time = time.time()
    if model_loader is None:
        from funasr import AutoModel

        model_loader = AutoModel

    model_kwargs = {
        "model": args.model_name,
        "device": args.device,
    }
    if args.trust_remote_code is not None:
        model_kwargs["trust_remote_code"] = str(args.trust_remote_code).lower() == "true"
    if args.remote_code:
        model_kwargs["remote_code"] = args.remote_code
    if args.vad_model:
        model_kwargs["vad_model"] = args.vad_model
    if args.punc_model:
        model_kwargs["punc_model"] = args.punc_model
    if args.spk_model:
        model_kwargs["spk_model"] = args.spk_model
    if args.model_revision:
        model_kwargs["model_revision"] = args.model_revision
    if args.vad_model_revision:
        model_kwargs["vad_model_revision"] = args.vad_model_revision
    if args.punc_model_revision:
        model_kwargs["punc_model_revision"] = args.punc_model_revision
    if args.spk_model_revision:
        model_kwargs["spk_model_revision"] = args.spk_model_revision

    model = model_loader(**model_kwargs)
    generate_kwargs: Dict[str, Any] = {"input": [args.audio_path], "cache": {}}
    if args.language:
        generate_kwargs["language"] = args.language
    hotwords = parse_hotwords(args.hotwords)
    if hotwords:
        generate_kwargs["hotwords"] = hotwords
    if args.batch_size_s is not None:
        generate_kwargs["batch_size_s"] = args.batch_size_s
    if args.use_itn is not None:
        generate_kwargs["use_itn"] = str(args.use_itn).lower() == "true"
    if args.merge_vad is not None:
        generate_kwargs["merge_vad"] = str(args.merge_vad).lower() == "true"
    if args.merge_length_s is not None:
        generate_kwargs["merge_length_s"] = args.merge_length_s
    if args.lm_model:
        generate_kwargs["lm_model"] = args.lm_model
    if args.lm_weight is not None:
        generate_kwargs["lm_weight"] = args.lm_weight
    if args.beam_size is not None:
        generate_kwargs["beam_size"] = args.beam_size

    result = model.generate(**generate_kwargs)
    raw = result[0] if isinstance(result, list) and result else (result or {})
    normalized = normalize_model_output(raw)
    payload = build_infer_payload(
        text=normalized.get("text", ""),
        language=args.language or "unknown",
        audio_duration=get_audio_duration(args.audio_path),
        time_stamps=normalized.get("time_stamps", []),
        segments=normalized.get("segments", []),
        speaker=normalized.get("speaker"),
        extra=normalized.get("extra"),
        transcribe_duration=time.time() - start_time,
    )

    os.makedirs(os.path.dirname(args.output_file), exist_ok=True)
    with open(args.output_file, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False)
    return payload


def main(argv: list[str] | None = None, model_loader=None) -> Dict[str, Any]:
    args = parse_args(argv)
    return run_infer(args, model_loader=model_loader)


if __name__ == "__main__":
    main()

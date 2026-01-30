# -*- coding: utf-8 -*-

"""Qwen3-ASR 推理脚本（subprocess 入口）。"""

import argparse
import json
import os
import time


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio_path", required=True)
    parser.add_argument("--output_file", required=True)
    parser.add_argument("--model_name", required=True)
    parser.add_argument("--backend", required=True, choices=["vllm", "transformers"])
    parser.add_argument("--language", default=None)
    parser.add_argument("--enable_word_timestamps", action="store_true")
    parser.add_argument("--forced_aligner_model", default=None)
    return parser.parse_args()


def build_infer_payload(text, language, time_stamps, audio_duration, transcribe_duration):
    return {
        "text": text,
        "language": language,
        "time_stamps": time_stamps,
        "audio_duration": audio_duration,
        "transcribe_duration": transcribe_duration,
    }


def main():
    import soundfile as sf
    from qwen_asr import Qwen3ASRModel

    args = parse_args()
    start = time.time()
    audio, sr = sf.read(args.audio_path)
    cuda_visible = os.environ.get("CUDA_VISIBLE_DEVICES")
    if cuda_visible:
        print(f"CUDA_VISIBLE_DEVICES={cuda_visible}")

    if args.backend == "vllm":
        model = Qwen3ASRModel.LLM(
            model=args.model_name,
            forced_aligner=args.forced_aligner_model if args.enable_word_timestamps else None,
        )
    else:
        model = Qwen3ASRModel.from_pretrained(
            args.model_name,
            forced_aligner=args.forced_aligner_model if args.enable_word_timestamps else None,
        )

    results = model.transcribe(
        audio=(audio, sr),
        language=args.language,
        return_time_stamps=args.enable_word_timestamps,
    )

    item = results[0]
    payload = build_infer_payload(
        text=item.text,
        language=item.language,
        time_stamps=getattr(item, "time_stamps", None),
        audio_duration=getattr(item, "duration", None),
        transcribe_duration=time.time() - start,
    )

    with open(args.output_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()

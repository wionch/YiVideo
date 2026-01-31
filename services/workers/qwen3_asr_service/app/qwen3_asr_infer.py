# -*- coding: utf-8 -*-

"""Qwen3-ASR 推理脚本（subprocess 入口）。"""

import argparse
import json
import os
import time


class ForcedAlignEncoder(json.JSONEncoder):
    """自定义 JSON Encoder，处理 ForcedAlignResult/ForcedAlignItem 等对象。"""

    def default(self, obj):
        # 处理 ForcedAlignItem 对象 (属性: text, start_time, end_time)
        if hasattr(obj, "text") and hasattr(obj, "start_time") and hasattr(obj, "end_time"):
            return {
                "text": obj.text,
                "start": obj.start_time,
                "end": obj.end_time,
            }
        # 处理 ForcedAlignResult 对象 (属性: items，包含 ForcedAlignItem 列表)
        if hasattr(obj, "items") and isinstance(obj.items, list):
            return [self.default(item) for item in obj.items]
        # 处理其他对象
        return super().default(obj)


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
        # max_model_len: 限制最大序列长度以适应 GPU 显存
        # 默认值 65536 需要 7.0 GiB KV cache，根据可用显存调整为 50000
        model = Qwen3ASRModel.LLM(
            model=args.model_name,
            forced_aligner=args.forced_aligner_model if args.enable_word_timestamps else None,
            max_model_len=50000,
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

    # 处理 time_stamps: ForcedAlignResult 对象需要转换为可 JSON 序列化的格式
    # 注意: time_stamps 是 ForcedAlignResult 对象，实际数据在 .items 属性中
    time_stamps = getattr(item, "time_stamps", None)
    if time_stamps is not None:
        # ForcedAlignResult 是一个包装对象，实际列表在 .items 中
        if hasattr(time_stamps, "items"):
            time_stamps = [
                {
                    "text": seg.text,
                    "start": seg.start_time,
                    "end": seg.end_time,
                }
                for seg in time_stamps.items
            ]
        elif isinstance(time_stamps, list):
            # 直接是列表的情况（向后兼容）
            converted = []
            for seg in time_stamps:
                if hasattr(seg, "text"):
                    converted.append({
                        "text": seg.text,
                        "start": getattr(seg, "start_time", getattr(seg, "start", 0.0)),
                        "end": getattr(seg, "end_time", getattr(seg, "end", 0.0)),
                    })
                elif isinstance(seg, dict):
                    converted.append({
                        "text": seg.get("text", ""),
                        "start": seg.get("start_time", seg.get("start", 0.0)),
                        "end": seg.get("end_time", seg.get("end", 0.0)),
                    })
            time_stamps = converted

    payload = build_infer_payload(
        text=item.text,
        language=item.language,
        time_stamps=time_stamps,
        audio_duration=getattr(item, "duration", None),
        transcribe_duration=time.time() - start,
    )

    with open(args.output_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, cls=ForcedAlignEncoder)


if __name__ == "__main__":
    main()

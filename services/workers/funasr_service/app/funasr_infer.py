from __future__ import annotations

import argparse
import importlib.util
import json
import os
import time
from typing import Any, Dict, List


def normalize_model_output(raw: Dict[str, Any]) -> Dict[str, Any]:
    time_stamps = (
        raw.get("time_stamps")
        or raw.get("timestamp")
        or raw.get("time_stamp")
        or []
    )
    speaker = raw.get("speaker") or raw.get("spk")
    segments = []
    sentence_list = raw.get("sentence_info", []) or raw.get("sentences", [])
    # 处理可能的嵌套情况：sentence_list 可能是 [[{...}]] 而不是 [{...}]
    while isinstance(sentence_list, list) and sentence_list and isinstance(sentence_list[0], list):
        sentence_list = sentence_list[0]
    for idx, item in enumerate(sentence_list):
        # 确保 item 是字典而非列表
        if isinstance(item, list) and item:
            item = item[0] if isinstance(item[0], dict) else {}
        if not isinstance(item, dict):
            continue
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


def _is_funasr_nano(model_name: str | None) -> bool:
    if not model_name:
        return False
    return model_name.startswith("FunAudioLLM/Fun-ASR")


def _is_paraformer_en(model_name: str | None) -> bool:
    """检测是否为英文 Paraformer 模型（不支持 language/use_itn 参数）。"""
    if not model_name:
        return False
    return "paraformer" in model_name.lower() and "-en" in model_name.lower()


def _load_token_list_if_mismatch(model_name: str | None) -> List[str] | None:
    """当 bpe.model vocab 小于 tokens.json 时返回 token_list，用于绕过解码越界。

    也处理没有 bpe.model 的情况（如 CharTokenizer 模型），只要有 tokens.json 就返回。
    """
    if not model_name:
        return None
    try:
        from modelscope import snapshot_download
        from funasr.download.download_model_from_hub import name_maps_ms
    except Exception:
        return None

    # 使用 FunASR 的模型名称映射解析别名（如 paraformer-en -> iic/...）
    resolved_name = name_maps_ms.get(model_name, model_name)

    try:
        model_dir = snapshot_download(resolved_name)
    except Exception:
        return None
    tokens_path = os.path.join(model_dir, "tokens.json")
    bpe_path = os.path.join(model_dir, "bpe.model")

    # 必须有 tokens.json
    if not os.path.exists(tokens_path):
        return None

    try:
        with open(tokens_path, "r", encoding="utf-8") as handle:
            tokens = json.load(handle)
        if not isinstance(tokens, list) or not tokens:
            return None

        # 如果有 bpe.model，检查词表大小是否匹配
        if os.path.exists(bpe_path):
            import sentencepiece as spm

            sp = spm.SentencePieceProcessor()
            sp.load(bpe_path)
            if len(tokens) <= sp.get_piece_size():
                return None
        # 如果没有 bpe.model（如 CharTokenizer 模型），直接返回 tokens
        # 这避免了 SentencePiece 解码越界问题
        return tokens
    except Exception:
        return None


def _ensure_token_list_tokenizer_registered() -> bool:
    """注册基于 token_list 的 tokenizer，避免 SentencePiece 解码越界。"""
    try:
        from funasr.register import tables
        from funasr.tokenizer.abs_tokenizer import BaseTokenizer
        from funasr.utils import postprocess_utils
    except Exception:
        return False

    if tables.tokenizer_classes.get("TokenListTokenizer") is not None:
        return True

    @tables.register("tokenizer_classes", "TokenListTokenizer")
    class TokenListTokenizer(BaseTokenizer):
        def __init__(self, token_list: List[str], **kwargs):
            super().__init__(token_list=token_list, **kwargs)

        def text2tokens(self, line: str) -> List[str]:
            # 最小实现：仅用于满足抽象方法，不影响推理解码
            text = str(line or "")
            if " " in text:
                return [item for item in text.split(" ") if item]
            return list(text) if text else []

        def tokens2text(self, tokens):
            text, _ = postprocess_utils.sentence_postprocess(list(tokens))
            return text

    return True


def resolve_remote_code_path(
    model_name: str | None,
    remote_code: str | None,
    snapshot_download=None,
) -> str | None:
    if remote_code:
        return remote_code
    if _is_funasr_nano(model_name):
        spec = importlib.util.find_spec("funasr.models.fun_asr_nano.model")
        if spec and spec.origin:
            return spec.origin
    if not model_name:
        return None
    if snapshot_download is None:
        try:
            from modelscope import snapshot_download as _snapshot_download
        except Exception:
            return None
        snapshot_download = _snapshot_download
    try:
        model_dir = snapshot_download(model_name)
    except Exception:
        return None
    candidate = os.path.join(model_dir, "model.py")
    if os.path.exists(candidate):
        return candidate
    return None


def _needs_trust_remote_code(model_name: str | None) -> bool:
    """检测模型是否需要 trust_remote_code=True 才能正确加载。

    包括：
    - FunASR Nano 系列模型
    - 带说话人分离的模型 (-spk)
    """
    if not model_name:
        return False
    # FunASR Nano 系列
    if _is_funasr_nano(model_name):
        return True
    # 带说话人分离的模型
    if "-spk" in model_name.lower():
        return True
    return False


def run_infer(args: argparse.Namespace, model_loader=None) -> Dict[str, Any]:
    start_time = time.time()
    if model_loader is None:
        from funasr import AutoModel

        model_loader = AutoModel

    model_kwargs = {
        "model": args.model_name,
        "device": args.device,
    }
    trust_remote_code = None
    if args.trust_remote_code is not None:
        trust_remote_code = str(args.trust_remote_code).lower() == "true"
        model_kwargs["trust_remote_code"] = trust_remote_code
        if trust_remote_code and not args.remote_code:
            auto_remote_code = resolve_remote_code_path(args.model_name, None)
            if auto_remote_code:
                model_kwargs["remote_code"] = auto_remote_code
        if trust_remote_code and not model_kwargs.get("remote_code"):
            # 对于需要 trust_remote_code 的模型（如 Nano、-spk 等），保持 trust_remote_code=True
            # 让 AutoModel 自行处理模型加载；其他模型则关闭以避免导入不存在的模块
            if not _needs_trust_remote_code(args.model_name):
                model_kwargs["trust_remote_code"] = False
    if args.remote_code:
        model_kwargs["remote_code"] = args.remote_code
    if args.vad_model:
        model_kwargs["vad_model"] = args.vad_model
    if args.punc_model:
        model_kwargs["punc_model"] = args.punc_model
    if args.spk_model:
        model_kwargs["spk_model"] = args.spk_model
    if _is_funasr_nano(args.model_name) and args.vad_model:
        model_kwargs["ctc_decoder"] = None
    if args.model_revision:
        model_kwargs["model_revision"] = args.model_revision
    if args.vad_model_revision:
        model_kwargs["vad_model_revision"] = args.vad_model_revision
    if args.punc_model_revision:
        model_kwargs["punc_model_revision"] = args.punc_model_revision
    if args.spk_model_revision:
        model_kwargs["spk_model_revision"] = args.spk_model_revision

    token_list = _load_token_list_if_mismatch(args.model_name)
    if token_list and _ensure_token_list_tokenizer_registered():
        model_kwargs["tokenizer"] = "TokenListTokenizer"
        model_kwargs["tokenizer_conf"] = {"token_list": token_list}
        print("检测到 bpe.model 与 tokens.json 词表不一致，已切换 TokenListTokenizer")

    try:
        model = model_loader(**model_kwargs)
    except AssertionError as exc:
        if (
            "is not registered" in str(exc)
            and model_kwargs.get("trust_remote_code")
            and not model_kwargs.get("remote_code")
        ):
            remote_code_path = resolve_remote_code_path(args.model_name, None)
            if remote_code_path:
                model_kwargs["remote_code"] = remote_code_path
                model = model_loader(**model_kwargs)
            else:
                raise
        else:
            raise
    generate_kwargs: Dict[str, Any] = {"input": [args.audio_path], "cache": {}}

    # 检测是否为英文 Paraformer 模型（不支持 language/use_itn 参数）
    is_paraformer_en = _is_paraformer_en(args.model_name)

    # 只有非英文 Paraformer 模型才传递 language 参数
    if args.language and not is_paraformer_en:
        generate_kwargs["language"] = args.language
    hotwords = parse_hotwords(args.hotwords)
    if hotwords:
        generate_kwargs["hotwords"] = hotwords
    if args.batch_size_s is not None:
        generate_kwargs["batch_size_s"] = args.batch_size_s
    if args.use_itn is not None and not is_paraformer_en:
        # 英文 Paraformer 模型不支持 use_itn 参数
        itn_value = str(args.use_itn).lower() == "true"
        generate_kwargs["use_itn"] = itn_value
        if _is_funasr_nano(args.model_name):
            generate_kwargs["itn"] = itn_value
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
    if _is_funasr_nano(args.model_name):
        generate_kwargs["batch_size"] = 1
        generate_kwargs["batch_size_s"] = 0

    result = model.generate(**generate_kwargs)
    # 处理可能的嵌套列表情况（某些模型返回 [[{...}]] 而不是 [{...}]）
    raw = result[0] if isinstance(result, list) and result else (result or {})
    # 如果还是列表（多层嵌套），继续解包直到拿到字典或空值
    while isinstance(raw, list):
        raw = raw[0] if raw else {}
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

from __future__ import annotations

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

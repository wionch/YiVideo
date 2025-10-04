#!/usr/bin/env python3
"""
faster-whisper-large-v2 调优版测试脚本
用法：python test_fw_v2_optim.py 111.wav
"""
import os
import sys
import time
import logging
import torch
from faster_whisper import WhisperModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# -------------------------------------------------
# 可调常量
# -------------------------------------------------
MODEL_NAME = "Systran/faster-whisper-large-v3"   # 真正要测的模型
COMPUTE_TYPE = "float16"                         # 速度/显存甜点
BEAM_SIZE = 3                                    # 官方默认 5，3 更平衡
HOTWORDS = ["王思聪", "王健林", "政法学院", "国民老公"]  # 中文专名
AUDIO_PATH = sys.argv[1] if len(sys.argv) > 1 else "/app/services/workers/whisperx_service/111.wav"

# -------------------------------------------------
# 核心转录函数
# -------------------------------------------------
def transcribe(audio_path: str):
    """返回 (results, info, load_time, transcribe_time)"""
    logger.info("=== 测试 %s ===", MODEL_NAME)

    # 1. 加载模型
    t0 = time.time()
    model = WhisperModel(
        MODEL_NAME,
        device="cuda",
        compute_type=COMPUTE_TYPE
    )
    load_time = time.time() - t0
    logger.info("✅ 模型加载成功 - 耗时: %.3fs", load_time)

    # 2. 转录（调优参数全部给出）
    t0 = time.time()
    segments, info = model.transcribe(
        audio_path,
        beam_size=BEAM_SIZE,
        best_of=BEAM_SIZE,
        temperature=(0.0, 0.2, 0.4, 0.6),
        condition_on_previous_text=False,      # 抑制循环幻觉
        compression_ratio_threshold=2.0,
        # logprob_threshold=-1.0,
        no_speech_threshold=0.5,
        # hotwords=HOTWORDS,
        word_timestamps=True
    )

    results = []
    for idx, seg in enumerate(segments, 1):
        logger.info("   片段%d: [%.2fs-%.2fs] %s",
                    idx, seg.start, seg.end, seg.text.strip())
        results.append({"start": seg.start, "end": seg.end, "text": seg.text.strip()})

    transcribe_time = time.time() - t0
    logger.info("✅ 转录完成 - 耗时: %.3fs", transcribe_time)
    logger.info("📊 检测语言: %s (概率: %.2f)", info.language, info.language_probability)
    logger.info("📊 处理片段: %d 个", len(results))
    if results:
        logger.info("📊 音频总时长: %.2fs", results[-1]["end"])

    # 3. 清理
    del model
    torch.cuda.empty_cache()

    return results, info, load_time, transcribe_time

# -------------------------------------------------
# 统一总结模板
# -------------------------------------------------
def print_summary(success: bool, load_t: float, trans_t: float):
    total = load_t + trans_t
    logger.info("=" * 60)
    logger.info("测试总结")
    logger.info("=" * 60)
    logger.info("总耗时: %.3fs", total)
    if success:
        logger.info("🎉 %s 测试成功", MODEL_NAME)
        logger.info("")
        logger.info("💡 本次已启用调优参数：")
        logger.info("   - beam_size=%d + best_of=%d", BEAM_SIZE, BEAM_SIZE)
        logger.info("   - condition_on_previous_text=False")
        logger.info("   - hotwords 中文专名")
        logger.info("   - float16 推理")
    else:
        logger.error("❌ %s 测试失败", MODEL_NAME)

# -------------------------------------------------
# CLI 入口
# -------------------------------------------------
def main():
    if not os.path.exists(AUDIO_PATH):
        logger.error("❌ 音频文件不存在: %s", AUDIO_PATH)
        sys.exit(1)

    try:
        _, _, load_t, trans_t = transcribe(AUDIO_PATH)
        print_summary(True, load_t, trans_t)
    except Exception as e:
        logger.exception("测试异常: %s", e)
        print_summary(False, 0, 0)
        sys.exit(2)

if __name__ == "__main__":
    main()
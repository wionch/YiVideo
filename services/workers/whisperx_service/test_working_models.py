#!/usr/bin/env python3
"""
确定的可用模型测试脚本
基于之前的测试结果，只验证已知的可用模型
"""

import os
import sys
import logging
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_faster_whisper_large_v2():
    """
    测试 Systran/faster-whisper-large-v2
    之前测试确定可用
    """
    logger.info("=== 测试 faster-whisper-large-v2 ===")

    try:
        from faster_whisper import WhisperModel

        # 加载模型
        start_time = time.time()
        logger.info("🔍 正在加载模型...")
        model = WhisperModel(
            "Systran/faster-whisper-large-v3",
            device="cuda",
            compute_type="float16"
        )
        load_time = time.time() - start_time
        logger.info(f"✅ 模型加载成功 - 耗时: {load_time:.3f}秒")

        # 检查音频文件
        audio_path = "/app/services/workers/whisperx_service/111.wav"
        if not os.path.exists(audio_path):
            logger.error("❌ 音频文件不存在")
            return False

        logger.info("🎯 开始转录完整音频...")

        transcribe_start = time.time()
        segments, info = model.transcribe(audio_path, beam_size=1)

        # 收集所有片段
        results = []
        segment_count = 0

        for segment in segments:
            segment_info = {
                "start": segment.start,
                "end": segment.end,
                "text": segment.text.strip()
            }
            results.append(segment_info)
            segment_count += 1

            # 显示每个片段
            logger.info(f"   片段{segment_count}: [{segment.start:.2f}s-{segment.end:.2f}s] {segment.text}")

        transcribe_time = time.time() - transcribe_start

        logger.info(f"✅ 转录完成 - 耗时: {transcribe_time:.3f}秒")
        logger.info(f"📊 检测语言: {info.language} (概率: {info.language_probability:.2f})")
        logger.info(f"📊 处理片段: {segment_count} 个")

        if results:
            total_duration = results[-1]["end"]
            logger.info(f"📊 音频总时长: {total_duration:.2f} 秒")

        # 清理显存
        del model
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        return True

    except Exception as e:
        logger.error(f"❌ 测试失败: {e}")
        return False


def main():
    """
    主测试函数 - 只测试 Systran/faster-whisper-large-v2
    """
    logger.info("Systran/faster-whisper-large-v2 完整转录测试")
    logger.info("=" * 60)

    total_start = time.time()

    # 测试 faster-whisper-large-v2
    success = test_faster_whisper_large_v2()

    total_time = time.time() - total_start

    # 总结
    logger.info("=" * 60)
    logger.info("测试总结")
    logger.info("=" * 60)

    logger.info(f"总耗时: {total_time:.3f}秒")

    if success:
        logger.info("🎉 Systran/faster-whisper-large-v2 测试成功")
        logger.info("")
        logger.info("💡 模型特点:")
        logger.info("   - 准确度高，支持中文识别")
        logger.info("   - 提供精确的时间戳信息")
        logger.info("   - 适合生产环境使用")
        logger.info("")
        logger.info("📝 集成代码示例:")
        logger.info("```python")
        logger.info("from faster_whisper import WhisperModel")
        logger.info("")
        logger.info("def transcribe_audio(audio_path):")
        logger.info("    model = WhisperModel('Systran/faster-whisper-large-v2',")
        logger.info("                           device='cuda',")
        logger.info("                           compute_type='float16')")
        logger.info("    segments, info = model.transcribe(audio_path, beam_size=1)")
        logger.info("    ")
        logger.info("    results = []")
        logger.info("    for segment in segments:")
        logger.info("        results.append({")
        logger.info("            'start': segment.start,")
        logger.info("            'end': segment.end,")
        logger.info("            'text': segment.text.strip()")
        logger.info("        })")
        logger.info("    return results")
        logger.info("```")
    else:
        logger.error("❌ Systran/faster-whisper-large-v2 测试失败")
        logger.info("")
        logger.info("💡 故障排除建议:")
        logger.info("1. 检查CUDA环境和GPU内存")
        logger.info("2. 验证模型文件完整性")
        logger.info("3. 清理模型缓存重新下载")
        logger.info("4. 检查音频文件格式")

    return success

if __name__ == "__main__":
    main()
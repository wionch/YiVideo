#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Pyannote Audio Service 使用示例

演示如何使用 pyannote_audio.diarize_speakers 工作流节点
"""

import os
import json
from pathlib import Path
import tempfile

def create_sample_audio():
    """创建示例音频文件"""
    try:
        import numpy as np
        import soundfile as sf

        # 创建简单的测试音频
        sample_rate = 16000
        duration = 10.0
        t = np.linspace(0., duration, int(sample_rate * duration))

        # 生成测试信号 (两个不同频率的正弦波模拟不同说话人)
        # 前5秒是说话人1 (440 Hz)
        audio_data1 = np.sin(2. * np.pi * 440 * t[:len(t)//2])

        # 后5秒是说话人2 (880 Hz)
        audio_data2 = np.sin(2. * np.pi * 880 * t[len(t)//2:])

        # 合并
        audio_data = np.concatenate([audio_data1, audio_data2])

        # 保存为WAV文件
        audio_path = "/tmp/sample_audio.wav"
        sf.write(audio_path, audio_data, sample_rate)

        return audio_path

    except ImportError:
        print("⚠️  音频生成库未安装，跳过示例音频创建")
        return None

def demo_workflow_context():
    """演示工作流上下文配置"""
    print("🎯 工作流上下文示例:")

    # 示例工作流上下文
    context = {
        "workflow_id": "demo_workflow_001",
        "input_params": {
            "video_path": "/share/videos/sample.mp4",
            "output_dir": "/share/workflows/demo_001"
        },
        "stages": [
            {
                "name": "extract_audio",
                "service": "ffmpeg_service",
                "task": "extract_audio",
                "status": "completed",
                "result": {
                    "audio_path": "/share/workflows/demo_001/audio.wav"
                }
            }
        ],
        "error": None
    }

    # 添加pyannote_audio任务
    context["stages"].append({
        "name": "diarize_speakers",
        "service": "pyannote_audio_service",
        "task": "pyannote_audio.diarize_speakers",
        "status": "pending",
        "context": context
    })

    print(json.dumps(context, indent=2, ensure_ascii=False))
    return context

def demo_diarize_speakers_usage():
    """演示说话人分离任务使用方法"""
    print("\n🎤 说话人分离任务使用示例:")

    # 创建示例音频
    audio_path = create_sample_audio()

    if audio_path and os.path.exists(audio_path):
        print(f"✅ 已创建示例音频: {audio_path}")

        # 构建任务上下文
        context = {
            "workflow_id": "demo_diarization_001",
            "input_params": {
                "audio_path": audio_path
            },
            "stages": [],
            "error": None
        }

        print("📋 任务上下文:")
        print(json.dumps(context, indent=2, ensure_ascii=False))

        # 注意：这里只是演示，实际的diarize_speakers任务需要通过Celery调用
        # 在实际使用中，会这样调用：
        # from tasks import diarize_speakers
        # result = diarize_speakers(context)
        # print("任务结果:", result)

    else:
        print("⚠️  无法创建示例音频，请确保有音频文件用于测试")

def demo_result_format():
    """演示结果格式"""
    print("\n📊 说话人分离结果格式示例:")

    # 示例结果
    sample_result = {
        "success": True,
        "data": {
            "diarization_file": "/share/workflows/demo_001/diarization_result.json",
            "speaker_segments": [
                {
                    "start": 0.0,
                    "end": 2.5,
                    "speaker": "SPEAKER_00",
                    "duration": 2.5
                },
                {
                    "start": 3.0,
                    "end": 5.5,
                    "speaker": "SPEAKER_01",
                    "duration": 2.5
                },
                {
                    "start": 6.0,
                    "end": 8.5,
                    "speaker": "SPEAKER_00",
                    "duration": 2.5
                },
                {
                    "start": 9.0,
                    "end": 10.0,
                    "speaker": "SPEAKER_01",
                    "duration": 1.0
                }
            ],
            "total_speakers": 2,
            "summary": "检测到 2 个说话人，共 4 个说话片段"
        }
    }

    print("📋 任务结果示例:")
    print(json.dumps(sample_result, indent=2, ensure_ascii=False))

    # 示例详细的diarization结果文件
    diarization_result = {
        "workflow_id": "demo_001",
        "audio_path": "/share/workflows/demo_001/audio.wav",
        "total_speakers": 2,
        "segments": [
            {
                "start": 0.0,
                "end": 2.5,
                "speaker": "SPEAKER_00",
                "duration": 2.5
            },
            {
                "start": 3.0,
                "end": 5.5,
                "speaker": "SPEAKER_01",
                "duration": 2.5
            },
            {
                "start": 6.0,
                "end": 8.5,
                "speaker": "SPEAKER_00",
                "duration": 2.5
            },
            {
                "start": 9.0,
                "end": 10.0,
                "speaker": "SPEAKER_01",
                "duration": 1.0
            }
        ],
        "metadata": {
            "model": "pyannote/speaker-diarization-community-1",
            "mode": "local",
            "processing_time": 15.3
        }
    }

    print("\n📋 详细的diarization结果文件示例:")
    print(json.dumps(diarization_result, indent=2, ensure_ascii=False))

def demo_config_examples():
    """演示配置示例"""
    print("\n⚙️  配置示例:")

    print("📄 config.yml 中的配置:")
    config_example = """
# 14. Pyannote Audio Service 配置 (新增)
# 基于 pyannote.audio 的说话人分离服务
pyannote_audio_service:
  # === 模式配置 ===
  # 使用模式: "local" (本地模式) 或 "api" (pyannoteAI API模式)
  use_paid_api: false

  # === 本地模式配置 ===
  # Hugging Face Token (用于访问HuggingFace模型)
  hf_token: "your_hf_token_here"

  # === API模式配置 ===
  # PyannoteAI API Key (API模式需要)
  pyannoteai_api_key: ""

  # === 模型配置 ===
  # 说话人分离模型选择
  diarization_model: "pyannote/speaker-diarization-community-1"

  # === 处理配置 ===
  # 音频采样率
  audio_sample_rate: 16000
  # 最小片段时长（秒）
  min_segment_duration: 0.5
  # 最大片段时长（秒）
  max_segment_duration: 30.0

  # === GPU配置 ===
  # 是否启用GPU锁机制
  enable_gpu_lock: true
  # GPU设备ID，0表示第一个GPU
  gpu_device_id: 0

  # === 质量控制 ===
  # 最小说话人数量
  min_speakers: 1
  # 最大说话人数量
  max_speakers: 10

  # === 监控配置 ===
  # 日志级别
  log_level: "INFO"
"""

    print(config_example)

    print("🌐 环境变量配置:")
    env_example = """
# 环境变量配置 (通过 .env 文件设置)

# Hugging Face Token (本地模式需要)
HF_TOKEN=your_huggingface_token_here

# PyannoteAI API Key (API模式需要)
PYANNOTEAI_API_KEY=your_pyannoteai_api_key_here

# Redis连接
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/1
"""

    print(env_example)

def demo_workflow_integration():
    """演示工作流集成示例"""
    print("\n🔄 完整工作流集成示例:")

    print("工作流配置文件示例:")
    workflow_example = {
        "workflow_chain": [
            "ffmpeg.extract_audio",
            "faster_whisper.transcribe_audio",
            "pyannote_audio.diarize_speakers",
            "faster_whisper.generate_subtitle_files"
        ],
        "input_params": {
            "video_path": "/share/videos/input/example.mp4",
            "workflow_config": {
                "subtitle_generation": {
                    "strategy": "asr",
                    "provider": "whisperx"
                },
                "speaker_diarization": {
                    "strategy": "pyannote",
                    "provider": "pyannote_audio"
                }
            }
        }
    }

    print(json.dumps(workflow_example, indent=2, ensure_ascii=False))

    print("\n📋 前端API调用示例:")
    api_example = """
# 创建和执行工作流
curl -X POST http://localhost:8788/v1/workflows \\
  -H "Content-Type: application/json" \\
  -d '{
    "video_path": "/share/videos/input/example.mp4",
    "workflow_chain": [
      "ffmpeg.extract_audio",
      "faster_whisper.transcribe_audio",
      "pyannote_audio.diarize_speakers",
      "faster_whisper.generate_subtitle_files"
    ]
  }'
"""

    print(api_example)

def main():
    """主函数"""
    print("🚀 Pyannote Audio Service 使用示例")
    print("=" * 50)

    demo_workflow_context()
    demo_diarize_speakers_usage()
    demo_result_format()
    demo_config_examples()
    demo_workflow_integration()

    print("\n" + "=" * 50)
    print("💡 使用说明:")
    print("1. 确保配置好 Hugging Face Token 或 PyannoteAI API Key")
    print("2. 准备音频文件 (推荐 WAV 格式)")
    print("3. 通过工作流调用 pyannote_audio.diarize_speakers 任务")
    print("4. 查看结果中的说话人片段信息")
    print("5. 根据需要使用 get_speaker_segments 和 validate_diarization 任务")

if __name__ == "__main__":
    main()
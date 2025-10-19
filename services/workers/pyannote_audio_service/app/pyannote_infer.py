#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
独立的pyannote推理脚本
用于通过subprocess调用，避免Celery环境下的潜在问题
"""

import sys
import json
import time
import argparse
from pathlib import Path

# 记录开始时间
script_start_time = time.time()
print(f"=== Python start === [脚本启动时间: 0.000s]", flush=True)

import torch
torch_import_time = time.time() - script_start_time
print(f"=== torch version: {torch.__version__} === [导入torch模块耗时: {torch_import_time:.3f}s]", flush=True)

print("=== import pyannote.audio ===", flush=True)
from pyannote.audio import Pipeline
pyannote_import_time = time.time() - script_start_time
print(f"=== import ok === [导入pyannote.audio模块耗时: {pyannote_import_time:.3f}s]", flush=True)

def run_diarization(audio_path: str, output_file: str, hf_token: str = None,
                   use_paid_api: bool = False, pyannoteai_api_key: str = None):
    """
    执行说话人分离

    Args:
        audio_path: 音频文件路径
        output_file: 输出结果文件路径
        hf_token: HuggingFace token (用于免费接口)
        use_paid_api: 是否使用付费接口
        pyannoteai_api_key: PyannoteAI API key (用于付费接口)
    """
    try:
        print(f"开始说话人分离任务，累计耗时: {time.time() - script_start_time:.3f}s", flush=True)

        # 加载模型 - 根据配置选择免费或付费接口
        print(f"[准备加载模型，累计耗时: {time.time() - script_start_time:.3f}s]", flush=True)
        pipeline_start_time = time.time()

        if use_paid_api:
            # 使用付费接口 (precision-2)
            model_name = "pyannote/speaker-diarization-precision-2"
            if not pyannoteai_api_key:
                raise ValueError("使用付费接口需要提供 pyannoteai_api_key")
            print(f"[使用付费接口] 模型: {model_name}", flush=True)
            pipeline = Pipeline.from_pretrained(model_name, token=pyannoteai_api_key)
        else:
            # 使用免费接口 (community-1)
            model_name = "pyannote/speaker-diarization-community-1"
            if not hf_token:
                raise ValueError("使用免费接口需要提供 hf_token")
            print(f"[使用免费接口] 模型: {model_name}", flush=True)
            pipeline = Pipeline.from_pretrained(model_name, token=hf_token)

        pipeline_load_time = time.time() - pipeline_start_time
        print(f"[模型加载完成，模型加载耗时: {pipeline_load_time:.3f}s，累计耗时: {time.time() - script_start_time:.3f}s]", flush=True)

        # 移动到CUDA
        pipeline.to(torch.device("cuda"))
        print(f"[准备说话人分离任务，累计耗时: {time.time() - script_start_time:.3f}s]", flush=True)

        # 执行说话人分离
        print(f"开始说话人分离任务，累计耗时: {time.time() - script_start_time:.3f}s", flush=True)
        diarization_start_time = time.time()

        diarization = pipeline(audio_path)

        diarization_time = time.time() - diarization_start_time
        print(f"[说话人分离完成，分离耗时: {diarization_time:.3f}s，累计耗时: {time.time() - script_start_time:.3f}s]", flush=True)

        # 处理结果
        print("开始处理结果...", flush=True)
        result_start_time = time.time()

        speaker_segments = []
        for turn, speaker in diarization.speaker_diarization:
            segment = {
                "start": turn.start,
                "end": turn.end,
                "speaker": speaker,
                "duration": turn.end - turn.start
            }
            speaker_segments.append(segment)

        # 按开始时间排序
        speaker_segments.sort(key=lambda x: x['start'])

        # 准备结果数据
        result_data = {
            "success": True,
            "audio_path": audio_path,
            "total_speakers": len(set(seg['speaker'] for seg in speaker_segments)),
            "segments": speaker_segments,
            "metadata": {
                "model": model_name,
                "api_type": "paid" if use_paid_api else "free",
                "processing_time": diarization_time,
                "total_time": time.time() - script_start_time
            }
        }

        # 保存结果
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)

        result_processing_time = time.time() - result_start_time
        print(f"[结果处理耗时: {result_processing_time:.3f}s，总脚本执行时间: {time.time() - script_start_time:.3f}s]", flush=True)

        print(f"说话人分离完成: {result_data['total_speakers']} 个说话人，{len(speaker_segments)} 个片段", flush=True)
        print(f"结果已保存到: {output_path}", flush=True)

        return result_data

    except Exception as e:
        error_msg = f"说话人分离失败: {str(e)}"
        print(error_msg, flush=True)

        # 保存错误结果
        error_data = {
            "success": False,
            "error": {
                "message": str(e),
                "type": type(e).__name__
            },
            "audio_path": audio_path
        }

        try:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(error_data, f, ensure_ascii=False, indent=2)
        except Exception as save_error:
            print(f"保存错误结果失败: {save_error}", flush=True)

        return error_data

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='Pyannote说话人分离独立推理脚本')
    parser.add_argument('--audio_path', required=True, help='音频文件路径')
    parser.add_argument('--output_file', required=True, help='输出结果文件路径')
    parser.add_argument('--hf_token', help='HuggingFace token (用于免费接口)')
    parser.add_argument('--use_paid_api', action='store_true', help='使用付费接口 (precision-2)')
    parser.add_argument('--pyannoteai_api_key', help='PyannoteAI API key (用于付费接口)')

    args = parser.parse_args()

    print(f"收到推理请求:", flush=True)
    print(f"  音频路径: {args.audio_path}", flush=True)
    print(f"  输出文件: {args.output_file}", flush=True)
    print(f"  使用付费接口: {args.use_paid_api}", flush=True)

    if args.use_paid_api:
        print(f"  PyannoteAI API Key: {'已提供' if args.pyannoteai_api_key else '未提供'}", flush=True)
    else:
        print(f"  HF Token: {'已提供' if args.hf_token else '未提供'}", flush=True)

    # 执行推理
    result = run_diarization(
        args.audio_path,
        args.output_file,
        args.hf_token,
        args.use_paid_api,
        args.pyannoteai_api_key
    )

    if result.get('success', False):
        print("推理成功完成", flush=True)
        sys.exit(0)
    else:
        print("推理失败", flush=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
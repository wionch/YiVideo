#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Faster Whisper 独立推理脚本

此脚本通过 subprocess 调用，在独立进程中执行语音转录任务。
解决 Celery prefork pool 与 CUDA 初始化的冲突问题。

使用方式:
    python faster_whisper_infer.py \\
        --audio_path /path/to/audio.mp3 \\
        --output_file /path/to/result.json \\
        --model_name large-v3 \\
        --device cuda \\
        --compute_type float16

作者: YiVideo Team
日期: 2025-10-21
参考: pyannote_audio_service/app/pyannote_infer.py
"""

import argparse
import json
import logging
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List

# ===== 日志配置 =====
# 独立进程需要独立的日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr)  # 输出到 stderr，避免污染 stdout
    ]
)
logger = logging.getLogger(__name__)

# ===== 路径修复 =====
# 确保项目根目录在 sys.path 中
project_root = Path(__file__).resolve().parents[4]  # 向上4级到项目根目录
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
    logger.debug(f"已添加项目根目录到 sys.path: {project_root}")


def parse_arguments() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='Faster Whisper 独立推理脚本',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # ===== 必需参数 =====
    parser.add_argument(
        '--audio_path',
        type=str,
        required=True,
        help='音频文件的绝对路径'
    )
    parser.add_argument(
        '--output_file',
        type=str,
        required=True,
        help='结果 JSON 文件的输出路径'
    )

    # ===== 模型参数 =====
    parser.add_argument(
        '--model_name',
        type=str,
        default='large-v3',
        help='Whisper 模型名称 (默认: large-v3)'
    )
    parser.add_argument(
        '--device',
        type=str,
        default='cuda',
        choices=['cuda', 'cpu'],
        help='计算设备 (默认: cuda)'
    )
    parser.add_argument(
        '--compute_type',
        type=str,
        default='float16',
        choices=['float16', 'int8', 'float32'],
        help='计算精度 (默认: float16)'
    )
    parser.add_argument(
        '--device_index',
        type=int,
        default=0,
        help='GPU 设备索引 (默认: 0)'
    )

    # ===== 转录参数 =====
    parser.add_argument(
        '--language',
        type=str,
        default=None,
        help='语言代码 (如 zh, en)，None 表示自动检测'
    )
    parser.add_argument(
        '--beam_size',
        type=int,
        default=3,
        help='Beam search 大小 (默认: 3)'
    )
    parser.add_argument(
        '--best_of',
        type=int,
        default=3,
        help='候选数量 (默认: 3)'
    )
    parser.add_argument(
        '--temperature',
        type=str,
        default='0.0,0.2,0.4,0.6',
        help='温度值列表，逗号分隔 (默认: 0.0,0.2,0.4,0.6)'
    )
    parser.add_argument(
        '--word_timestamps',
        action='store_true',
        help='是否生成词级时间戳'
    )
    parser.add_argument(
        '--vad_filter',
        action='store_true',
        help='是否启用 VAD 过滤'
    )
    parser.add_argument(
        '--vad_parameters',
        type=str,
        default=None,
        help='VAD 参数 JSON 字符串'
    )

    return parser.parse_args()


def serialize_segment(segment: Any) -> Dict[str, Any]:
    """
    将 faster-whisper 的 Segment 对象序列化为字典

    Args:
        segment: faster_whisper 返回的 Segment 对象

    Returns:
        可 JSON 序列化的字典
    """
    try:
        # 使用 _asdict() 方法（如果是 namedtuple）
        if hasattr(segment, '_asdict'):
            segment_dict = segment._asdict()
        else:
            # 否则手动提取属性
            segment_dict = {
                'id': getattr(segment, 'id', None),
                'seek': getattr(segment, 'seek', None),
                'start': getattr(segment, 'start', None),
                'end': getattr(segment, 'end', None),
                'text': getattr(segment, 'text', ''),
                'tokens': getattr(segment, 'tokens', []),
                'temperature': getattr(segment, 'temperature', None),
                'avg_logprob': getattr(segment, 'avg_logprob', None),
                'compression_ratio': getattr(segment, 'compression_ratio', None),
                'no_speech_prob': getattr(segment, 'no_speech_prob', None),
            }

        # 处理 words（如果存在）
        if hasattr(segment, 'words') and segment.words:
            segment_dict['words'] = [
                {
                    'word': w.word,
                    'start': w.start,
                    'end': w.end,
                    'probability': w.probability
                }
                for w in segment.words
            ]

        return segment_dict

    except Exception as e:
        logger.warning(f"序列化 segment 失败: {e}，使用降级方案")
        return {
            'text': str(segment),
            'error': str(e)
        }


def serialize_transcription_info(info: Any) -> Dict[str, Any]:
    """
    将 faster-whisper 的 TranscriptionInfo 对象序列化为字典

    Args:
        info: faster_whisper 返回的 TranscriptionInfo 对象

    Returns:
        可 JSON 序列化的字典
    """
    try:
        if hasattr(info, '_asdict'):
            return info._asdict()
        else:
            return {
                'language': getattr(info, 'language', None),
                'language_probability': getattr(info, 'language_probability', None),
                'duration': getattr(info, 'duration', None),
                'duration_after_vad': getattr(info, 'duration_after_vad', None),
                'all_language_probs': getattr(info, 'all_language_probs', None),
            }
    except Exception as e:
        logger.warning(f"序列化 info 失败: {e}")
        return {'error': str(e)}


def execute_transcription(args: argparse.Namespace) -> Dict[str, Any]:
    """
    执行语音转录任务

    Args:
        args: 命令行参数

    Returns:
        包含转录结果或错误信息的字典
    """
    start_time = time.time()

    try:
        # ===== 参数验证 =====
        audio_path = Path(args.audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")

        logger.info("=" * 60)
        logger.info("Faster Whisper 推理脚本启动")
        logger.info("=" * 60)
        logger.info(f"音频文件: {audio_path}")
        logger.info(f"模型: {args.model_name}")
        logger.info(f"设备: {args.device} (索引: {args.device_index})")
        logger.info(f"计算类型: {args.compute_type}")
        logger.info(f"语言: {args.language or '自动检测'}")

        # ===== 加载 WhisperModel =====
        logger.info("开始加载 WhisperModel...")

        # 在独立进程中导入，避免污染主进程
        from faster_whisper import WhisperModel

        # 设置 CUDA 设备（如果使用 CUDA）
        if args.device == 'cuda':
            import os
            os.environ['CUDA_VISIBLE_DEVICES'] = str(args.device_index)
            logger.info(f"设置 CUDA_VISIBLE_DEVICES={args.device_index}")

        # 创建模型实例
        model = WhisperModel(
            args.model_name,
            device=args.device,
            compute_type=args.compute_type,
            download_root=os.environ.get('HF_HOME'),
            local_files_only=False
        )

        logger.info("WhisperModel 加载完成！")

        # ===== 准备转录参数 =====
        # 解析温度参数
        temperature_list = [float(t.strip()) for t in args.temperature.split(',')]

        # 解析 VAD 参数
        vad_parameters = None
        if args.vad_parameters:
            try:
                vad_parameters = json.loads(args.vad_parameters)
            except json.JSONDecodeError as e:
                logger.warning(f"VAD 参数解析失败: {e}，使用默认值")

        transcribe_options = {
            'language': args.language,
            'beam_size': args.beam_size,
            'best_of': args.best_of,
            'temperature': temperature_list,
            'word_timestamps': args.word_timestamps,
            'vad_filter': args.vad_filter,
            'vad_parameters': vad_parameters,
            'condition_on_previous_text': False,
            'compression_ratio_threshold': 2.4,
            'no_speech_threshold': 0.5,
        }

        logger.info("转录参数:")
        for key, value in transcribe_options.items():
            if value is not None:
                logger.info(f"  {key}: {value}")

        # ===== 执行转录 =====
        logger.info("开始转录...")
        transcribe_start = time.time()

        segments, info = model.transcribe(
            str(audio_path),
            **transcribe_options
        )

        # 收集所有 segments（注意：这是一个生成器）
        segments_list = []
        for segment in segments:
            segment_dict = serialize_segment(segment)
            segments_list.append(segment_dict)

            # 实时日志（避免过多输出）
            if len(segments_list) % 10 == 0:
                logger.info(f"已处理 {len(segments_list)} 个片段...")

        transcribe_duration = time.time() - transcribe_start
        logger.info(f"转录完成！共 {len(segments_list)} 个片段，耗时: {transcribe_duration:.2f}s")

        # ===== 序列化结果 =====
        info_dict = serialize_transcription_info(info)

        execution_time = time.time() - start_time

        result = {
            'success': True,
            'segments': segments_list,
            'info': info_dict,
            'execution_time': execution_time,
            'model_info': {
                'model_name': args.model_name,
                'device': args.device,
                'compute_type': args.compute_type,
            },
            'statistics': {
                'total_segments': len(segments_list),
                'transcribe_duration': transcribe_duration,
                'audio_duration': info_dict.get('duration', 0),
                'language': info_dict.get('language'),
                'language_probability': info_dict.get('language_probability'),
            }
        }

        logger.info("=" * 60)
        logger.info("转录成功！")
        logger.info(f"语言: {info_dict.get('language')} (置信度: {info_dict.get('language_probability', 0):.2%})")
        logger.info(f"音频时长: {info_dict.get('duration', 0):.2f}s")
        logger.info(f"转录片段数: {len(segments_list)}")
        logger.info(f"总耗时: {execution_time:.2f}s")
        logger.info("=" * 60)

        return result

    except Exception as e:
        execution_time = time.time() - start_time
        error_traceback = traceback.format_exc()

        logger.error("=" * 60)
        logger.error("转录失败！")
        logger.error(f"错误类型: {type(e).__name__}")
        logger.error(f"错误信息: {str(e)}")
        logger.error("=" * 60)
        logger.error("详细堆栈:")
        logger.error(error_traceback)
        logger.error("=" * 60)

        return {
            'success': False,
            'error': {
                'type': type(e).__name__,
                'message': str(e),
                'traceback': error_traceback
            },
            'execution_time': execution_time
        }


def main() -> int:
    """
    主函数

    Returns:
        退出码 (0 表示成功，1 表示失败)
    """
    try:
        # 解析参数
        args = parse_arguments()

        # 执行转录
        result = execute_transcription(args)

        # 写入结果文件
        output_file = Path(args.output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        logger.info(f"结果已写入: {output_file}")

        # 返回退出码
        return 0 if result['success'] else 1

    except Exception as e:
        logger.critical(f"脚本执行失败: {e}")
        logger.critical(traceback.format_exc())

        # 尝试写入错误结果
        try:
            if 'args' in locals() and hasattr(args, 'output_file'):
                error_result = {
                    'success': False,
                    'error': {
                        'type': type(e).__name__,
                        'message': str(e),
                        'traceback': traceback.format_exc()
                    }
                }
                with open(args.output_file, 'w', encoding='utf-8') as f:
                    json.dump(error_result, f, ensure_ascii=False, indent=2)
        except:
            pass

        return 1


if __name__ == '__main__':
    sys.exit(main())

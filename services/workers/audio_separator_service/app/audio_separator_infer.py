#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Audio Separator - Standalone Inference Script

This script is designed to be called via subprocess to isolate the model
loading and inference from the main Celery worker process, avoiding CUDA
and multiprocessing conflicts.
"""

import os
import json
import argparse
import logging
import time
import sys
from pathlib import Path

# 配置日志记录器
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    stream=sys.stderr  # 将日志输出到 stderr，以便主进程捕获
)
logger = logging.getLogger(__name__)

def write_output(output_file, data):
    """Writes the final data to the output JSON file."""
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        # 如果写入失败，记录到日志
        logger.error(f"Fatal: Failed to write output to {output_file}: {e}")

def main():
    """Main function to run the audio separation process."""
    parser = argparse.ArgumentParser(description="Standalone Audio Separator Inference Script")
    parser.add_argument("--audio_path", required=True, help="Path to the input audio file.")
    parser.add_argument("--output_file", required=True, help="Path to the output JSON file for results.")
    parser.add_argument("--model_name", required=True, help="Name of the separation model to use.")
    parser.add_argument("--model_type", required=True, help="Type of the model (e.g., 'demucs', 'mdx').")
    parser.add_argument("--output_dir", required=True, help="Directory to save the separated audio files.")
    
    # 添加 audio-separator 库支持的其他参数
    parser.add_argument("--output_format", default="flac", help="Output format for separated files (e.g., 'flac', 'wav', 'mp3').")
    parser.add_argument("--log_level", default="INFO", help="Logging level for the separator.")
    parser.add_argument("--optimization_level", default=None, help="Vocal separation optimization level.")

    args = parser.parse_args()

    start_time = time.time()

    try:
        logger.info(f"Starting audio separation for: {args.audio_path}")
        logger.info(f"Model: {args.model_name} ({args.model_type})")
        logger.info(f"Output directory: {args.output_dir}")

        # 动态导入 audio_separator
        try:
            from audio_separator.separator import Separator
        except ImportError:
            logger.error("audio-separator library not found. Please ensure it is installed.")
            raise

        # 验证输入文件
        if not Path(args.audio_path).exists():
            raise FileNotFoundError(f"Input audio file not found: {args.audio_path}")

        # 创建输出目录
        Path(args.output_dir).mkdir(parents=True, exist_ok=True)

        # 初始化 Separator
        # 将字符串日志级别转换为 logging 模块的整数常量
        log_level_int = getattr(logging, args.log_level.upper(), logging.INFO)
        
        separator = Separator(
            log_level=log_level_int,
            output_dir=args.output_dir,
            output_format=args.output_format
        )

        if args.optimization_level:
            logger.info(f"Applying optimization level: {args.optimization_level}")
            # 在这里可以根据 optimization_level 设置 specific separator parameters
            # 例如: separator.mdx_pre_chunk_size = 1024 (这只是一个例子)

        # 加载模型
        # 根据模型类型选择不同的加载方式
        # 注意：load_model方法只接受model_filename参数，不接受demucs_model_path参数
        separator.load_model(model_filename=args.model_name)

        logger.info(f"Model '{args.model_name}' loaded successfully.")

        # 执行分离
        output_files = separator.separate(args.audio_path)
        
        separation_time = time.time() - start_time
        logger.info(f"Separation complete in {separation_time:.2f} seconds.")
        logger.info(f"Output files: {output_files}")

        if not output_files:
            raise RuntimeError("Audio separation failed to produce any output files.")

        # 准备结果
        result = {
            "success": True,
            "statistics": {
                "separation_time": separation_time,
                "model_used": args.model_name,
                "model_type": args.model_type,
            },
            "output_files": output_files
        }
        write_output(args.output_file, result)

    except Exception as e:
        logger.error(f"An error occurred during audio separation: {e}", exc_info=True)
        error_result = {
            "success": False,
            "error": {
                "type": type(e).__name__,
                "message": str(e)
            },
            "statistics": {
                "separation_time": time.time() - start_time
            }
        }
        write_output(args.output_file, error_result)
        sys.exit(1) # 退出并返回非零状态码表示失败

if __name__ == "__main__":
    main()
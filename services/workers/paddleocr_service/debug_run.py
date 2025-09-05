# services/workers/paddleocr_service/debug_run.py
import argparse
import yaml
import json
import os
import sys

# --- Setup sys.path ---
# This allows the script to be run from the project root 
# and still find the necessary modules within the service.
SERVICE_ROOT = os.path.dirname(__file__)
APP_ROOT = os.path.join(SERVICE_ROOT, 'app')
# Add the service's app directory to the Python path
sys.path.insert(0, APP_ROOT)
# Add the common services directory to the path
COMMON_SERVICES_ROOT = os.path.abspath(os.path.join(SERVICE_ROOT, '..', '..', 'common'))
sys.path.insert(0, COMMON_SERVICES_ROOT)

from logic import extract_subtitles_from_video

# --- Constants ---
# Assume the script is run from the project root, so config is at './config.yml'
DEFAULT_CONFIG_PATH = os.path.abspath(os.path.join(SERVICE_ROOT, '..', '..', '..', 'config.yml'))

def format_time_srt(seconds):
    """将秒转换为SRT格式的时间戳 (HH:MM:SS,mmm)"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millisecs = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millisecs:03d}"

def generate_srt(subtitles):
    """将字幕数据转换为SRT格式字符串"""
    srt_content = []
    for i, subtitle in enumerate(subtitles, 1):
        start_time = format_time_srt(subtitle['startTime'])
        end_time = format_time_srt(subtitle['endTime'])
        srt_content.append(f"{i}\n{start_time} --> {end_time}\n{subtitle['text']}\n")
    return "\n".join(srt_content)

def main():
    """
    本地调试和单步测试的入口点。
    """
    parser = argparse.ArgumentParser(
        description="对 paddleocr_service 的核心逻辑进行单步测试。",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        '-i', '--input', 
        required=True, 
        help="要处理的视频文件的路径。\n在容器内运行时，请使用容器内的绝对路径, e.g., /app/videos/test.mp4"
    )
    parser.add_argument(
        '--config', 
        default=DEFAULT_CONFIG_PATH, 
        help=f"配置文件的路径。\n(默认: {DEFAULT_CONFIG_PATH})"
    )
    parser.add_argument(
        '-o', '--output', 
        default=None, 
        help="（可选）将结果保存为JSON文件的路径。\n如果未提供，结果将保存在视频同目录下。"
    )

    args = parser.parse_args()

    # 1. 检查文件是否存在
    if not os.path.exists(args.input):
        print(f"错误: 输入的视频文件不存在: {args.input}")
        sys.exit(1)
    if not os.path.exists(args.config):
        print(f"错误: 配置文件不存在: {args.config}")
        sys.exit(1)

    # 2. 加载配置
    with open(args.config, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    # 3. 执行核心逻辑
    try:
        subtitles = extract_subtitles_from_video(args.input, config)

        # 4. 生成输出文件
        video_name = os.path.splitext(os.path.basename(args.input))[0]
        output_dir = os.path.dirname(args.input)
        
        # 生成JSON文件
        json_path = os.path.join(output_dir, f"{video_name}.json")
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(subtitles, f, ensure_ascii=False, indent=4)
        
        # 生成SRT文件
        srt_path = os.path.join(output_dir, f"{video_name}.srt")
        srt_content = generate_srt(subtitles)
        with open(srt_path, 'w', encoding='utf-8') as f:
            f.write(srt_content)
        
        # 只打印文件路径
        print(f"JSON文件: {json_path}")
        print(f"SRT文件: {srt_path}")

    except Exception as e:
        print(f"执行过程中发生错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
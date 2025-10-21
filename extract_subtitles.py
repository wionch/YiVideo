#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
主要的字幕提取程序
用于从视频文件中提取字幕，生成 JSON 和 SRT 文件
"""

import argparse
import json
import os
import sys
import time

import yaml

# 添加服务路径到 Python 路径
SERVICE_ROOT = os.path.join(os.path.dirname(__file__), 'services', 'workers', 'paddleocr_service')
APP_ROOT = os.path.join(SERVICE_ROOT, 'app')
sys.path.insert(0, APP_ROOT)

from logic import extract_subtitles_from_video


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
    """主程序入口"""
    parser = argparse.ArgumentParser(description="从视频中提取字幕")
    parser.add_argument('-i', '--input', required=True, help="输入视频文件路径")
    parser.add_argument('-o', '--output', help="输出目录路径（默认为视频所在目录）")
    parser.add_argument('--lang', default='ch', help="OCR语言设置（默认为中文）")
    parser.add_argument('--config', default='config.yml', help="配置文件路径")
    
    args = parser.parse_args()
    
    # 检查输入文件
    if not os.path.exists(args.input):
        # print(f"错误: 输入文件不存在: {args.input}")
        sys.exit(1)
    
    # 检查配置文件
    config_path = args.config
    if not os.path.exists(config_path):
        config_path = os.path.join(os.path.dirname(__file__), 'config.yml')
    
    if not os.path.exists(config_path):
        # print(f"错误: 配置文件不存在: {config_path}")
        sys.exit(1)
    
    # 加载配置
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    # 设置语言
    if 'ocr' not in config:
        config['ocr'] = {}
    config['ocr']['lang'] = args.lang
    
    # 开始计时
    start_time = time.time()
    
    try:
        # 执行字幕提取
        subtitles = extract_subtitles_from_video(args.input, config)
        
        # 计算执行时间
        end_time = time.time()
        execution_time = end_time - start_time
        valid_subtitle_count = len(subtitles)
        
        # 确定输出目录
        if args.output:
            output_dir = args.output
            os.makedirs(output_dir, exist_ok=True)
        else:
            output_dir = os.path.dirname(args.input)
        
        # 生成输出文件名
        video_name = os.path.splitext(os.path.basename(args.input))[0]
        json_path = os.path.join(output_dir, f"{video_name}.json")
        srt_path = os.path.join(output_dir, f"{video_name}.srt")
        
        # 保存 JSON 文件
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(subtitles, f, ensure_ascii=False, indent=2)
        
        # 保存 SRT 文件
        srt_content = generate_srt(subtitles)
        with open(srt_path, 'w', encoding='utf-8') as f:
            f.write(srt_content)
        
        # 输出统计信息和文件路径
        # print(f"执行时间: {execution_time:.2f}秒, 提取有效字幕: {valid_subtitle_count}条")
        # print(f"JSON文件: {json_path}")
        # print(f"SRT文件: {srt_path}")
        
    except Exception as e:
        # print(f"字幕提取失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
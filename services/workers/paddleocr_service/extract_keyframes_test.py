#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
关键帧抽取与字幕区域标注测试脚本
从视频中抽取JSON中指定的所有关键帧，并用蓝色框标注字幕区域
"""

import os
import json
import cv2
import numpy as np
from typing import List, Dict, Tuple, Optional
import argparse


class KeyFrameExtractor:
    """关键帧抽取器"""
    
    def __init__(self, video_path: str, json_path: str, output_dir: str = "./pics"):
        """
        初始化关键帧抽取器
        
        Args:
            video_path: 视频文件路径
            json_path: JSON结果文件路径  
            output_dir: 输出目录，默认为"./pics"
        """
        self.video_path = video_path
        self.json_path = json_path
        self.output_dir = output_dir
        
        # 确保输出目录存在
        os.makedirs(self.output_dir, exist_ok=True)
        
        print(f"视频路径: {self.video_path}")
        print(f"JSON路径: {self.json_path}")
        print(f"输出目录: {self.output_dir}")
    
    def load_json_data(self) -> List[Dict]:
        """
        加载JSON数据
        
        Returns:
            包含字幕信息的字典列表
        """
        try:
            with open(self.json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            print(f"成功加载JSON数据，共{len(data)}条记录")
            return data
        except Exception as e:
            print(f"加载JSON数据失败: {e}")
            return []
    
    def extract_key_frames(self, subtitle_data: List[Dict]) -> List[int]:
        """
        从字幕数据中提取所有关键帧号
        
        Args:
            subtitle_data: 字幕数据列表
            
        Returns:
            关键帧号列表
        """
        key_frames = []
        for item in subtitle_data:
            if 'keyFrame' in item:
                key_frames.append(item['keyFrame'])
        
        # 去重并排序
        key_frames = sorted(list(set(key_frames)))
        print(f"提取到{len(key_frames)}个唯一关键帧: {key_frames}")
        return key_frames
    
    def draw_subtitle_region(self, frame: np.ndarray, subtitle_region: Tuple[int, int, int, int]) -> np.ndarray:
        """
        在帧上绘制蓝色字幕区域框
        
        Args:
            frame: 视频帧
            subtitle_region: 字幕区域坐标 (x1, y1, x2, y2)
            
        Returns:
            标注后的帧
        """
        x1, y1, x2, y2 = subtitle_region
        
        # 绘制蓝色矩形框，BGR格式中蓝色为 (255, 0, 0)
        cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 3)
        
        # 在框的左上角添加文字标签
        label = f"字幕区域 ({x1},{y1},{x2},{y2})"
        label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)[0]
        
        # 绘制文字背景
        cv2.rectangle(frame, (x1, y1-30), (x1 + label_size[0], y1), (255, 0, 0), -1)
        
        # 绘制白色文字
        cv2.putText(frame, label, (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        return frame
    
    def extract_and_annotate_frames(self, key_frames: List[int], subtitle_region: Tuple[int, int, int, int]) -> bool:
        """
        抽取关键帧并标注字幕区域
        
        Args:
            key_frames: 关键帧号列表
            subtitle_region: 字幕区域坐标 (x1, y1, x2, y2)
            
        Returns:
            是否成功
        """
        try:
            # 打开视频文件
            cap = cv2.VideoCapture(self.video_path)
            if not cap.isOpened():
                print(f"无法打开视频文件: {self.video_path}")
                return False
            
            # 获取视频信息
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            print(f"视频信息 - 总帧数: {total_frames}, 帧率: {fps}")
            
            extracted_count = 0
            
            for frame_num in key_frames:
                # 检查帧号是否在有效范围内
                if frame_num >= total_frames:
                    print(f"警告: 关键帧号 {frame_num} 超出视频总帧数 {total_frames}")
                    continue
                
                # 定位到指定帧
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
                ret, frame = cap.read()
                
                if not ret:
                    print(f"警告: 无法读取第 {frame_num} 帧")
                    continue
                
                # 标注字幕区域
                annotated_frame = self.draw_subtitle_region(frame, subtitle_region)
                
                # 保存帧
                output_filename = f"keyframe_{frame_num:06d}_annotated.jpg"
                output_path = os.path.join(self.output_dir, output_filename)
                
                success = cv2.imwrite(output_path, annotated_frame)
                if success:
                    print(f"成功保存: {output_path}")
                    extracted_count += 1
                else:
                    print(f"保存失败: {output_path}")
            
            cap.release()
            print(f"抽取完成! 共成功保存 {extracted_count} 帧")
            return True
            
        except Exception as e:
            print(f"抽取帧时发生错误: {e}")
            return False
    
    def run(self, subtitle_region: Tuple[int, int, int, int] = (0, 601, 1280, 683)) -> bool:
        """
        执行关键帧抽取与标注
        
        Args:
            subtitle_region: 字幕区域坐标，默认为 (0, 601, 1280, 683)
            
        Returns:
            是否成功
        """
        print("=" * 50)
        print("开始关键帧抽取与标注任务")
        print("=" * 50)
        
        # 1. 加载JSON数据
        subtitle_data = self.load_json_data()
        if not subtitle_data:
            return False
        
        # 2. 提取关键帧
        key_frames = self.extract_key_frames(subtitle_data)
        if not key_frames:
            print("未找到任何关键帧")
            return False
        
        # 3. 抽取并标注帧
        success = self.extract_and_annotate_frames(key_frames, subtitle_region)
        
        if success:
            print("=" * 50)
            print("任务完成!")
            print(f"输出目录: {os.path.abspath(self.output_dir)}")
            print("=" * 50)
        
        return success


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="关键帧抽取与字幕区域标注测试脚本")
    parser.add_argument("--video", "-v", required=True, help="视频文件路径")
    parser.add_argument("--json", "-j", required=True, help="JSON结果文件路径")
    parser.add_argument("--output", "-o", default="./pics", help="输出目录，默认为./pics")
    parser.add_argument("--region", "-r", nargs=4, type=int, metavar=('X1', 'Y1', 'X2', 'Y2'),
                       default=[0, 601, 1280, 683], help="字幕区域坐标 (x1 y1 x2 y2)")
    
    args = parser.parse_args()
    
    # 检查输入文件是否存在
    if not os.path.exists(args.video):
        print(f"错误: 视频文件不存在: {args.video}")
        return False
    
    if not os.path.exists(args.json):
        print(f"错误: JSON文件不存在: {args.json}")
        return False
    
    # 创建抽取器并执行
    extractor = KeyFrameExtractor(args.video, args.json, args.output)
    subtitle_region = tuple(args.region)
    
    return extractor.run(subtitle_region)


if __name__ == "__main__":
    # 如果直接运行脚本，使用默认参数进行测试
    if len(os.sys.argv) == 1:
        print("使用默认参数进行测试...")
        
        # 默认参数
        video_path = "../../../videos/223.mp4"  # 相对于当前脚本位置
        json_path = "../../../videos/223.json"
        output_dir = "./pics"
        subtitle_region = (0, 601, 1280, 683)
        
        # 检查文件是否存在
        if not os.path.exists(video_path):
            print(f"错误: 默认视频文件不存在: {video_path}")
            print("请使用命令行参数指定正确的文件路径，例如:")
            print("python extract_keyframes_test.py --video /path/to/video.mp4 --json /path/to/result.json")
            exit(1)
        
        if not os.path.exists(json_path):
            print(f"错误: 默认JSON文件不存在: {json_path}")
            print("请使用命令行参数指定正确的文件路径，例如:")
            print("python extract_keyframes_test.py --video /path/to/video.mp4 --json /path/to/result.json")
            exit(1)
        
        # 执行测试
        extractor = KeyFrameExtractor(video_path, json_path, output_dir)
        success = extractor.run(subtitle_region)
        
        if success:
            print("测试完成!")
        else:
            print("测试失败!")
    else:
        # 使用命令行参数
        main()
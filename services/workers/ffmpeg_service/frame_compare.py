#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频帧数对比工具
快速获取原视频和所有子视频的帧数，验证分割是否完整
"""

import json
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

# --- 配置 ---
ORIGINAL_VIDEO = "/app/videos/777.mp4"
SEGMENTS_DIR = "output_segments"

def get_frame_count_fast(video_path):
    """
    使用ffprobe快速获取视频帧数
    方法1: 直接计算帧数 (最快)
    """
    try:
        # 方法1: 使用nb_frames (如果视频有此信息)
        cmd1 = [
            'ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'stream=nb_frames', '-of', 'json', video_path
        ]
        result = subprocess.run(cmd1, capture_output=True, text=True, timeout=10)
        data = json.loads(result.stdout)
        
        if 'streams' in data and data['streams']:
            nb_frames = data['streams'][0].get('nb_frames')
            if nb_frames and nb_frames != 'N/A':
                return int(nb_frames), "metadata"
        
        # 方法2: 计算包数量 (备用方法，较慢但更准确)
        cmd2 = [
            'ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-count_packets', '-show_entries', 'stream=nb_read_packets', 
            '-of', 'json', video_path
        ]
        result = subprocess.run(cmd2, capture_output=True, text=True, timeout=30)
        data = json.loads(result.stdout)
        
        if 'streams' in data and data['streams']:
            packets = data['streams'][0].get('nb_read_packets')
            if packets:
                return int(packets), "packet_count"
        
        return None, "failed"
        
    except Exception as e:
        print(f"获取帧数失败 {video_path}: {e}")
        return None, "error"

def get_video_info_fast(video_path):
    """
    快速获取视频基本信息：时长、帧率、帧数
    """
    try:
        cmd = [
            'ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'stream=duration,r_frame_rate,nb_frames',
            '-show_entries', 'format=duration',
            '-of', 'json', video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        data = json.loads(result.stdout)
        
        info = {
            'path': video_path,
            'filename': os.path.basename(video_path),
            'duration': 0.0,
            'fps': 0.0,
            'frame_count': None,
            'method': 'unknown'
        }
        
        # 获取时长
        if 'format' in data:
            info['duration'] = float(data['format'].get('duration', 0))
        
        # 获取流信息
        if 'streams' in data and data['streams']:
            stream = data['streams'][0]
            
            # 帧率
            fps_str = stream.get('r_frame_rate', '0/1')
            if '/' in fps_str:
                num, den = map(int, fps_str.split('/'))
                info['fps'] = num / den if den != 0 else 0
            
            # 帧数
            nb_frames = stream.get('nb_frames')
            if nb_frames and nb_frames != 'N/A':
                info['frame_count'] = int(nb_frames)
                info['method'] = 'metadata'
        
        # 如果没有帧数信息，使用备用方法
        if info['frame_count'] is None:
            frame_count, method = get_frame_count_fast(video_path)
            info['frame_count'] = frame_count
            info['method'] = method
        
        return info
        
    except Exception as e:
        print(f"获取视频信息失败 {video_path}: {e}")
        return None

def analyze_single_segment(segment_path):
    """分析单个子视频的帧信息"""
    return get_video_info_fast(segment_path)

def clean_segments_directory(segments_dir):
    """清空子视频目录中的所有文件"""
    if os.path.exists(segments_dir):
        print(f"🧹 正在清空临时目录: {segments_dir}")
        try:
            files_removed = 0
            for filename in os.listdir(segments_dir):
                file_path = os.path.join(segments_dir, filename)
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    files_removed += 1
            print(f"✅ 已清空 {files_removed} 个文件")
        except Exception as e:
            print(f"❌ 清空目录失败: {e}")
    else:
        print(f"📁 创建临时目录: {segments_dir}")
        os.makedirs(segments_dir, exist_ok=True)

def get_video_duration_simple(filepath):
    """快速获取视频时长"""
    try:
        cmd = [
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', filepath
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=10)
        return float(result.stdout.strip())
    except Exception as e:
        print(f"❌ 无法获取视频时长: {e}")
        return None

def split_video_segments(input_video, output_dir, num_segments=10):
    """分割视频为指定数量的片段"""
    print(f"\n🔪 正在分割视频为 {num_segments} 个片段...")
    
    # 获取视频时长
    duration = get_video_duration_simple(input_video)
    if not duration:
        return []
    
    print(f"📹 视频时长: {duration:.2f} 秒")
    
    segment_duration = duration / num_segments
    output_pattern = os.path.join(output_dir, 'segment_%03d.mp4')
    
    cmd = [
        'ffmpeg', '-y', '-i', input_video, '-c', 'copy', '-map', '0', 
        '-f', 'segment', '-segment_time', str(segment_duration), 
        '-reset_timestamps', '1', output_pattern
    ]
    
    try:
        split_start = time.time()
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        split_time = time.time() - split_start
        
        # 获取生成的文件
        generated_files = [
            os.path.join(output_dir, f) 
            for f in os.listdir(output_dir) 
            if f.startswith('segment_') and f.endswith('.mp4')
        ]
        generated_files.sort()
        
        print(f"✅ 分割完成！生成 {len(generated_files)} 个片段 (耗时: {split_time:.3f}秒)")
        return generated_files
        
    except subprocess.CalledProcessError as e:
        print(f"❌ FFmpeg 分割失败: {e}")
        if e.stderr:
            print(f"错误详情: {e.stderr}")
        return []

def main():
    """主函数：对比原视频和子视频的帧数"""
    print("🎬 视频帧数对比分析工具")
    print("=" * 80)
    
    total_start = time.time()
    
    # 0. 清空临时目录
    clean_segments_directory(SEGMENTS_DIR)
    
    # 1. 检查原视频存在性
    if not os.path.exists(ORIGINAL_VIDEO):
        print(f"❌ 原视频不存在: {ORIGINAL_VIDEO}")
        return
    
    # 2. 执行视频分割
    segment_files = split_video_segments(ORIGINAL_VIDEO, SEGMENTS_DIR, num_segments=10)
    if not segment_files:
        print("❌ 视频分割失败，无法继续分析")
        return
    
    print(f"📁 成功生成 {len(segment_files)} 个子视频文件")
    
    # 3. 分析原视频
    print("\n🎯 正在分析原视频...")
    analysis_start = time.time()
    original_info = get_video_info_fast(ORIGINAL_VIDEO)
    analysis_time1 = time.time() - analysis_start
    
    if not original_info:
        print("❌ 无法获取原视频信息")
        return
    
    print(f"✅ 原视频分析完成 (耗时: {analysis_time1:.3f}秒)")
    
    # 4. 并发分析所有子视频
    print(f"\n🔄 正在并发分析 {len(segment_files)} 个子视频...")
    analysis_start = time.time()
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        segment_infos = list(executor.map(analyze_single_segment, segment_files))
    
    analysis_time2 = time.time() - analysis_start
    print(f"✅ 子视频分析完成 (耗时: {analysis_time2:.3f}秒)")
    
    # 5. 过滤失败的分析结果
    valid_segments = [info for info in segment_infos if info and info['frame_count'] is not None]
    failed_count = len(segment_files) - len(valid_segments)
    
    if failed_count > 0:
        print(f"⚠️  {failed_count} 个子视频分析失败")
    
    # 6. 计算统计数据
    total_segment_frames = sum(info['frame_count'] for info in valid_segments)
    total_segment_duration = sum(info['duration'] for info in valid_segments)
    
    # 7. 输出详细结果
    print("\n" + "=" * 80)
    print("📊 详细分析结果")
    print("=" * 80)
    
    # 原视频信息
    print(f"\n🎬 原视频: {original_info['filename']}")
    print(f"   时长: {original_info['duration']:.2f} 秒")
    print(f"   帧率: {original_info['fps']:.2f} fps")
    print(f"   帧数: {original_info['frame_count']:,} 帧 (方法: {original_info['method']})")
    
    # 子视频汇总
    print(f"\n📁 子视频汇总 ({len(valid_segments)} 个有效文件):")
    print(f"   总时长: {total_segment_duration:.2f} 秒")
    print(f"   总帧数: {total_segment_frames:,} 帧")
    
    # 详细列表
    print(f"\n📋 子视频详细列表:")
    print(f"{'文件名':<20} {'时长(秒)':<10} {'帧数':<10} {'帧率':<8} {'方法':<12}")
    print("-" * 70)
    
    for info in valid_segments:
        print(f"{info['filename']:<20} {info['duration']:<10.2f} {info['frame_count']:<10,} "
              f"{info['fps']:<8.1f} {info['method']:<12}")
    
    # 8. 对比分析
    print("\n" + "=" * 80)
    print("🔍 对比分析结果")
    print("=" * 80)
    
    # 帧数对比
    frame_diff = total_segment_frames - original_info['frame_count']
    frame_match = frame_diff == 0
    
    print(f"\n📈 帧数对比:")
    print(f"   原视频帧数:     {original_info['frame_count']:,} 帧")
    print(f"   子视频总帧数:   {total_segment_frames:,} 帧")
    print(f"   差异:          {frame_diff:+,} 帧")
    print(f"   匹配状态:       {'✅ 完全匹配' if frame_match else '❌ 不匹配'}")
    
    # 时长对比
    duration_diff = total_segment_duration - original_info['duration']
    duration_match = abs(duration_diff) < 0.1  # 允许0.1秒误差
    
    print(f"\n⏱️  时长对比:")
    print(f"   原视频时长:     {original_info['duration']:.2f} 秒")
    print(f"   子视频总时长:   {total_segment_duration:.2f} 秒") 
    print(f"   差异:          {duration_diff:+.2f} 秒")
    print(f"   匹配状态:       {'✅ 基本匹配' if duration_match else '❌ 不匹配'}")
    
    # 9. 结论
    print("\n" + "=" * 80)
    print("🎯 结论")
    print("=" * 80)
    
    if frame_match and duration_match:
        print("✅ 分割完美！子视频的帧数和时长都与原视频匹配")
        print("✅ 合并这些子视频应该能完全恢复原视频")
    elif frame_match:
        print("✅ 帧数匹配！但时长有微小差异")
        print("✅ 合并应该能保持完整性，时长差异可能是精度问题")
    else:
        print("⚠️  帧数不匹配！需要检查分割过程")
        if frame_diff > 0:
            print(f"   子视频比原视频多 {frame_diff} 帧")
        else:
            print(f"   子视频比原视频少 {-frame_diff} 帧")
    
    # 10. 性能统计
    total_time = time.time() - total_start
    print(f"\n⚡ 性能统计:")
    print(f"   原视频分析:     {analysis_time1:.3f} 秒")
    print(f"   子视频分析:     {analysis_time2:.3f} 秒")
    print(f"   总计耗时:       {total_time:.3f} 秒")
    print(f"   平均每文件:     {total_time/(len(valid_segments)+1):.3f} 秒")

if __name__ == "__main__":
    main()
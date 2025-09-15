# -*- coding: utf-8 -*-
import argparse
import os
import sys
import time

# 将上层目录添加到sys.path中，以便导入app模块
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.modules.new_decoder import get_video_info, split_video, split_video_pyav

def test_decoder(video_path: str, num_splits: int, temp_dir: str):
    """
    测试视频分割功能并验证其无损性。

    :param video_path: 视频路径。
    :param num_splits: 分割数量。
    :param temp_dir: 临时文件保存目录。
    """
    print(f"--- 开始测试视频: {video_path} ---")
    print(f"分割数量: {num_splits}")
    print(f"临时目录: {temp_dir}")

    # 1. 获取原始视频信息
    print("\n--- 正在获取原始视频信息 ---")
    original_info = get_video_info(video_path)
    if not original_info:
        print("获取原始视频信息失败，测试终止。")
        return

    original_frames = original_info.get('total_frames')
    original_duration = float(original_info.get('duration', 0))
    print(f"原始视频信息 -> 帧数: {original_frames}, 时长: {original_duration:.3f}s")

    # 2. 将视频分割成指定数量
    print("\n--- 正在分割视频 ---")
    start_time = time.time()
    sub_video_paths = split_video(video_path, num_splits, temp_dir)
    end_time = time.time()
    split_duration = end_time - start_time

    if not sub_video_paths:
        print("视频分割失败，测试终止。")
        return
    
    print(f"视频成功分割成 {len(sub_video_paths)} 个子视频。")
    print(f"分割总耗时: {split_duration:.2f} 秒。")

    # 3. 循环获取子视频信息并累加
    print("--- 正在获取并累加子视频信息 ---")
    total_sub_frames = 0
    total_sub_duration = 0.0

    for i, sub_path in enumerate(sub_video_paths):
        print(f"正在处理子视频 {i+1}/{len(sub_video_paths)}: {sub_path}")
        sub_info = get_video_info(sub_path)
        if not sub_info:
            print(f"获取子视频 {sub_path} 信息失败，测试终止。")
            return
        
        sub_frames = sub_info.get('total_frames')
        sub_duration = float(sub_info.get('duration', 0))
        total_sub_frames += sub_frames
        total_sub_duration += sub_duration
        print(f" -> 帧数: {sub_frames}, 时长: {sub_duration:.3f}s")

    # 4. 对比结果
    print("--- 测试结果对比 ---")
    print(f"原始视频总帧数: {original_frames}")
    print(f"所有子视频总帧数: {total_sub_frames}")
    print("---------------------------------")
    print(f"原始视频总时长: {original_duration:.3f}s")
    print(f"所有子视频总时长: {total_sub_duration:.3f}s")
    print("---------------------------------")

    frames_match = original_frames == total_sub_frames
    # 时长对比设置一个小的容忍误差，因为浮点数计算可能不完全精确
    duration_match = abs(original_duration - total_sub_duration) < 0.1

    if frames_match:
        print("✅ 帧数验证通过！总帧数完全匹配。")
    else:
        print(f"❌ 帧数验证失败！差异: {original_frames - total_sub_frames} 帧。")

    if duration_match:
        print("✅ 时长验证通过！总时长在容忍误差内。")
    else:
        print(f"❌ 时长验证失败！差异: {original_duration - total_sub_duration:.3f}s.")

    print("\n--- 测试结束 ---")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="测试 new_decoder.py 视频分割功能")
    parser.add_argument('-i', '--video_path', type=str, default='videos/223.mp4', help='输入视频的路径')
    parser.add_argument('-n', '--num_splits', type=int, default=4, help='要分割的子视频数量')
    parser.add_argument('-o', '--temp_dir', type=str, default='./tmp/test_decoder', help='临时保存分割后视频的目录')

    args = parser.parse_args()

    # 确保路径在项目根目录下是正确的
    # 我们假设脚本是从 YiVideo 目录运行的
    # 或者路径是相对于 services/workers/paddleocr_service 的
    # 为了健壮性，我们构建一个更可靠的路径
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
    video_path_abs = os.path.join(project_root, args.video_path)
    temp_dir_abs = os.path.join(os.path.dirname(os.path.abspath(__file__)), args.temp_dir)

    if not os.path.exists(video_path_abs):
        print(f"错误: 视频文件未找到于 '{video_path_abs}'")
        print("请确保视频文件存在，并且路径相对于项目根目录是正确的。")
    else:
        test_decoder(video_path_abs, args.num_splits, temp_dir_abs)

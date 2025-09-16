import os
import time
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed

# 导入更新后的核心模块函数
from app.modules.video_decoder import get_video_info, split_video_fast

def get_segment_frame_count(video_path: str) -> int:
    """线程安全的辅助函数，用于获取单个视频文件的帧数。"""
    info = get_video_info(video_path)
    if info and info['frame_count'] > 0:
        return info['frame_count']
    print(f"警告: 无法获取 '{os.path.basename(video_path)}' 的帧数，计为 0。")
    return 0

if __name__ == "__main__":
    # --- 配置 ---
    video_path = '/app/videos/777.mp4'
    output_dir = '/app/services/workers/ffmpeg_worker/tmp_output'
    num_splits = 10
    # ---

    # 准备工作
    if not os.path.exists(video_path):
        print(f"错误: 输入视频 '{video_path}' 不存在，测试终止。")
        exit()

    total_start_time = time.perf_counter()
    print("--- 开始核心解码模块测试 (快速模式) ---")

    # 1. 使用新的 get_video_info 获取原始视频信息
    print(f"\n--- 步骤 1: 获取原始视频信息 ---")
    info_start_time = time.perf_counter()
    original_video_info = get_video_info(video_path)
    info_end_time = time.perf_counter()

    if not original_video_info or original_video_info['frame_count'] == 0:
        print(f"获取原视频 '{video_path}' 的信息失败，测试终止。")
        exit()
    
    original_total_frames = original_video_info['frame_count']
    print(f"获取信息成功 (耗时: {info_end_time - info_start_time:.2f} 秒)")
    print(f"  - 视频路径: {video_path}")
    print(f"  - 总帧数: {original_total_frames}")
    print(f"  - 总时长: {original_video_info['duration']:.2f} 秒")
    print(f"  - 目标分割数: {num_splits}")

    # 2. 使用新的 split_video_fast 执行快速分割
    print(f"\n--- 步骤 2: 执行快速视频分割 (-c copy) ---")
    split_start_time = time.perf_counter()
    split_parts = split_video_fast(
        video_path=video_path,
        output_dir=output_dir,
        num_splits=num_splits
    )
    split_end_time = time.perf_counter()

    if not split_parts:
        print("视频分割失败，测试终止。")
        exit()
    
    print(f"分割完成 (耗时: {split_end_time - split_start_time:.2f} 秒)，生成 {len(split_parts)} 个文件。")

    # 3. 并发获取所有子视频的帧数
    print(f"\n--- 步骤 3: 并发分析所有子视频的帧数 ---")
    analysis_start_time = time.perf_counter()
    total_segment_frames = 0
    with ThreadPoolExecutor(max_workers=num_splits) as executor:
        future_to_path = {executor.submit(get_segment_frame_count, part_path): part_path for part_path in split_parts}
        
        # 使用 as_completed 来处理已完成的任务
        results = []
        for future in as_completed(future_to_path):
            path = future_to_path[future]
            try:
                frame_count = future.result()
                results.append({'path': os.path.basename(path), 'frame_count': frame_count})
            except Exception as exc:
                print(f"处理 '{path}' 时发生错误: {exc}")
                results.append({'path': os.path.basename(path), 'frame_count': 0})

    # 按文件名排序并加总
    results.sort(key=lambda x: x['path'])
    for res in results:
        print(f"  - 文件: {res['path']}, 帧数: {res['frame_count']}")
        total_segment_frames += res['frame_count']

    analysis_end_time = time.perf_counter() 
    print(f"并发分析完成 (耗时: {analysis_end_time - analysis_start_time:.2f} 秒)。")

    # 4. 最终验证和总结
    print("\n" + "="*60)
    print("--- 最终验证结果 ---")
    print("="*60)
    
    print(f"原始视频总帧数: {original_total_frames}")
    print(f"所有子视频帧数总和: {total_segment_frames}")
    
    frame_difference = original_total_frames - total_segment_frames

    if frame_difference == 0:
        print("\n✅ 帧数验证通过！总帧数完全匹配，视频内容完整无缺。")
    else:
        print(f"\n❌ 帧数验证失败！差异: {frame_difference} 帧。")
        print("注意: 使用 -c copy 分割时，由于不按关键帧精确分割，存在几帧的差异是正常现象。")

    total_end_time = time.perf_counter()
    print("\n--- 耗时总结 ---")
    print(f"步骤 1 [获取信息]   耗时: {info_end_time - info_start_time:.4f} 秒")
    print(f"步骤 2 [快速分割]     耗时: {split_end_time - split_start_time:.4f} 秒")
    print(f"步骤 3 [并发分析]   耗时: {analysis_end_time - analysis_start_time:.4f} 秒")
    print(f"总计执行时间         耗时: {total_end_time - total_start_time:.4f} 秒")
    print("="*60)
import os
import time
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from app.modules.video_decoder import get_video_info, get_video_info_accurate, split_video_by_gpu, decode_and_count_frames_gpu

if __name__ == "__main__":
    video_path = '/app/videos/777.mp4'
    output_dir = '/app/services/workers/ffmpeg_worker/tmp_output'
    num_splits = 8

    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir)

    print("--- 开始核心解码模块测试 (精确模式) ---")

    # 1. 快速获取视频信息用于即时显示
    fast_info = get_video_info(video_path)
    if fast_info:
        print(f"原视频 (快速检测): {video_path}")
        print(f"  - 预估时长: {fast_info['duration']:.2f} 秒")
        print(f"  - 预估总帧数: {fast_info['frame_count']}")
    print(f"分割数量: {num_splits}")

    # 2. 精确获取总帧数，用于后续分割（此步骤会比较慢）
    print("\n--- 开始精确计算总帧数 (此过程可能需要一些时间) ---")
    accurate_info_start_time = time.perf_counter()
    original_video_info = get_video_info_accurate(video_path)
    accurate_info_end_time = time.perf_counter()
    if not original_video_info:
        print(f"获取原视频 '{video_path}' 的精确信息失败，测试终止。")
        exit()
    print(f"精确帧数计算耗时: {accurate_info_end_time - accurate_info_start_time:.2f} 秒")
    print(f"精确总帧数: {original_video_info['frame_count']}")


    print("\n--- 开始视频分割 (解码再编码模式) ---")
    split_start_time = time.perf_counter()
    split_parts = split_video_by_gpu(
        video_path=video_path,
        output_dir=output_dir,
        num_splits=num_splits,
        total_frames=original_video_info['frame_count'] # 传入精确帧数
    )
    split_end_time = time.perf_counter()

    print(f"\n分割总耗时: {split_end_time - split_start_time:.2f} 秒")

    if not split_parts:
        print("\n视频分割失败，测试终止。")
        exit()

    print("\n--- 开始并发解码并验证帧数 ---")
    total_decoded_frames = 0
    with ThreadPoolExecutor(max_workers=num_splits) as executor:
        # 使用新的字典来存储 future -> (part_info, start_time)
        future_to_part_and_start_time = {}
        for part in split_parts:
            start_time = time.perf_counter()
            future = executor.submit(decode_and_count_frames_gpu, part['path'])
            future_to_part_and_start_time[future] = (part, start_time)

        for future in as_completed(future_to_part_and_start_time):
            part_info, start_time = future_to_part_and_start_time[future]
            try:
                decoded_frames = future.result()
                end_time = time.perf_counter()
                duration = end_time - start_time
                total_decoded_frames += decoded_frames
                
                print(f"\n文件: {os.path.basename(part_info['path'])}")
                print(f"  - 解码耗时: {duration:.2f} 秒")
                print(f"  - 预期帧数: {part_info['expected_frames']}")
                print(f"  - 解码帧数: {decoded_frames}")
                if decoded_frames == part_info['expected_frames']:
                    print("  - 结果: 帧数匹配成功")
                else:
                    print(f"  - 结果: 帧数不匹配! (差异: {decoded_frames - part_info['expected_frames']})")
            except Exception as exc:
                print(f"解码 {part_info['path']} 时发生错误: {exc}")

    print("\n--- 开始时长校验 ---")
    total_split_duration = 0
    for part in split_parts:
        info = get_video_info(part['path'])
        if info:
            total_split_duration += info['duration']
    print(f"原视频时长: {original_video_info['duration']:.4f} 秒")
    print(f"所有分片时长总和: {total_split_duration:.4f} 秒")
    duration_diff = abs(original_video_info['duration'] - total_split_duration)
    print(f"时长差异: {duration_diff:.4f} 秒")

    print("\n--- 测试完成 ---")
    print(f"原视频理论总帧数: {original_video_info['frame_count']}")
    print(f"所有分片解码总帧数: {total_decoded_frames}")
    if total_decoded_frames == original_video_info['frame_count']:
        print("最终帧数校验: 成功! 总帧数完全匹配。")
    else:
        print(f"最终帧数校验: 失败! 总帧数不匹配，差异为 {total_decoded_frames - original_video_info['frame_count']}。")

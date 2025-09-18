import subprocess
import os
import json
import time
import shutil
from concurrent.futures import ThreadPoolExecutor

# 导入新增的并发解码函数
from app.modules.video_decoder import decode_video_concurrently

# --- 用户配置 ---
INPUT_VIDEO = "/app/videos/223.mp4"         # 你的视频文件名
NUM_SEGMENTS = 10               # 你想分割成的子视频数量
OUTPUT_DIR = "output_segments"  # 存放子视频的文件夹

def get_video_duration(filepath):
    """使用 ffprobe 快速获取视频时长"""
    print("--- 准备阶段: 正在快速获取视频时长... ---")
    command = [
        'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1', filepath
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=10)
        duration = float(result.stdout.strip())
        print(f"获取时长成功: {duration:.2f} 秒")
        return duration
    except Exception as e:
        print(f"致命错误：无法获取视频时长 '{filepath}'。错误: {e}")
        return None

def get_frame_count(filepath):
    """
    (高速版) 使用 MediaInfo 快速、准确地获取视频帧数。
    请确保 'mediainfo' 已在您的环境中安装。
    """
    command = [
        'mediainfo',
        '--Output=Video;%FrameCount%',
        filepath
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=10)
        return int(result.stdout.strip())
    except FileNotFoundError:
        print("致命错误: 'mediainfo' 命令未找到。请先在您的环境中安装 MediaInfo。")
        # 返回 -1 作为特殊错误码，以便主程序可以决定是否终止
        return -1
    except Exception:
        print(f"警告：使用 mediainfo 无法计算文件 '{os.path.basename(filepath)}' 的帧数，将计为 0。")
        return 0

def split_video(filepath, num_segments, total_duration, output_dir):
    """使用 ffmpeg 快速分割视频, 并在开始前清理目录"""
    print("\n--- 步骤 1: 清理并准备输出目录 ---")
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir)
    print(f"目录 '{output_dir}' 已清空并准备就绪。")

    print("--- 步骤 1.1: 正在进行快速分割 ---")
    segment_duration = total_duration / num_segments
    output_pattern = os.path.join(output_dir, f'segment_%03d.mp4')
    
    command = ['ffmpeg','-y','-i',filepath,'-c','copy','-map','0','-f','segment',
        '-segment_time', str(segment_duration),'-reset_timestamps','1',output_pattern]

    try:
        subprocess.run(command, capture_output=True, text=True, check=True)
        generated_files = [os.path.join(output_dir, f) for f in os.listdir(output_dir) if f.startswith('segment_')]
        generated_files.sort()
        return generated_files
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"错误：ffmpeg 分割失败。\nFFmpeg Stderr: {e.stderr.strip()}")
        return []

def analyze_single_video(args):
    """分析单个子视频的偏差值和帧数 (最终诊断版)"""
    filepath, expected_start_time = args
    
    frame_count = get_frame_count(filepath)
    if frame_count == -1: return None

    # 这是我们用来获取真实时间戳的命令
    command = [
        'ffprobe', '-v', 'error', '-select_streams', 'v:0',
        '-show_entries', 'packet=pts_time', '-of', 'json', filepath
    ]
    
    result_dict = {
        "filename": os.path.basename(filepath),
        "expected_start": expected_start_time,
        "actual_start": -1.0, # 初始值设为错误码
        "deviation": 0.0,
        "frame_count": frame_count
    }

    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=10)
        data = json.loads(result.stdout)
        if 'packets' in data and data['packets']:
            actual_start_time = float(data['packets'][0].get('pts_time', 0.0))
            result_dict["actual_start"] = actual_start_time
            result_dict["deviation"] = actual_start_time - expected_start_time
        else:
            # 文件有效但没有数据包
            result_dict["actual_start"] = 0.0
            result_dict["deviation"] = 0.0 - expected_start_time
            
    except Exception as e:
        # 捕获任何可能的错误并打印出来
        print(f"\n--- DEBUG: 偏差值计算失败，文件: {os.path.basename(filepath)} ---")
        print(f"命令原文: {' '.join(command)}")
        print(f"错误类型: {type(e).__name__}")
        print(f"错误详情: {e}")
        # 如果是子进程错误，打印 stderr
        if hasattr(e, 'stderr'):
            print(f"FFprobe 返回的错误信息 (Stderr):\n{e.stderr.strip()}")
        print("---------------------------------------------------\n")

    return result_dict

def analyze_videos_concurrently(filepaths, segment_duration):
    """并发分析所有子视频的偏差和帧数"""
    print("\n--- 步骤 2: 正在并发分析子视频 (偏差和帧数) ---")
    tasks = [(filepath, i * segment_duration) for i, filepath in enumerate(filepaths)]
    
    with ThreadPoolExecutor() as executor:
        results = list(executor.map(analyze_single_video, tasks))

    # 过滤掉可能因 mediainfo 缺失导致的 None 结果
    valid_results = [r for r in results if r is not None]
    if len(valid_results) != len(results):
        # 如果有任务失败，说明 mediainfo 很可能未安装，终止程序
        return None
    
    valid_results.sort(key=lambda x: x['filename'])
    return valid_results

def print_results(results):
    """格式化并打印分析结果表格"""
    print("\n--- 步骤 3: 分析结果如下 ---")
    print("-" * 100)
    header = f"{ '文件名':<20} | { '期望开始时间 (s)':<20} | { '实际开始时间 (s)':<20} | { '偏差 (s)':<15} | { '视频帧数':<10}"
    print(header)
    print("-" * 100)
    for res in results:
        line = f"{res['filename']:<20} | {res['expected_start']:<20.6f} | {res['actual_start']:<20.6f} | {res['deviation']:<+15.6f} | {res['frame_count']:<10}"
        print(line)
    print("-" * 100)

def main():
    """主执行函数"""
    total_start_time = time.time()

    if not os.path.exists(INPUT_VIDEO):
        print(f"错误: 输入文件 '{INPUT_VIDEO}' 不存在。")
        return

    total_duration = get_video_duration(INPUT_VIDEO)
    if total_duration is None: return
    
    print("--- 准备阶段: 正在快速获取原视频总帧数... ---")
    original_total_frames = get_frame_count(INPUT_VIDEO)
    # 如果get_frame_count因为mediainfo未安装而失败，则终止
    if original_total_frames == -1: return
    
    print(f"\n原视频 '{os.path.basename(INPUT_VIDEO)}' -> 总时长: {total_duration:.2f} 秒, 总帧数: {original_total_frames} 帧")
    segment_duration = total_duration / NUM_SEGMENTS
    print(f"目标分割数量: {NUM_SEGMENTS}, 计算得出每个分段目标时长: {segment_duration:.2f} 秒")

    split_start_time = time.time()
    generated_files = split_video(INPUT_VIDEO, NUM_SEGMENTS, total_duration, OUTPUT_DIR)
    split_end_time = time.time()
    if not generated_files: return
    
    analyze_start_time = time.time()
    analysis_results = analyze_videos_concurrently(generated_files, segment_duration)
    analyze_end_time = time.time()
    # 如果并发分析过程中断，则退出
    if analysis_results is None: return

    print_results(analysis_results)
    
    total_segment_frames = sum(res['frame_count'] for res in analysis_results)
    print("\n--- 帧数统计总结 ---")
    print(f"原视频总帧数: {original_total_frames}")
    print(f"所有子视频帧数总和: {total_segment_frames}")
    if original_total_frames > 0 and original_total_frames == total_segment_frames:
        print("结论: 帧数一致，视频内容完整无缺。")
    else:
        print(f"结论: 帧数可能不一致 (相差 {abs(original_total_frames - total_segment_frames)} 帧)。")

    total_end_time = time.time()
    print("\n--- 耗时总结 ---")
    print(f"步骤1 [分割及清理]   耗时: {split_end_time - split_start_time:.4f} 秒")
    print(f"步骤2 [分析偏差/帧数] 耗时: {analyze_end_time - analyze_start_time:.4f} 秒")
    prep_time = (split_start_time - total_start_time)
    print(f"准备阶段 [获取信息] 耗时: {prep_time:.4f} 秒")
    print(f"总计执行时间        耗时: {total_end_time - total_start_time:.4f} 秒")

# --- 新增：并发解码函数的测试 ---
def test_concurrent_decoder():
    """
    用于测试新增的 decode_video_concurrently 函数。
    """
    print("\n" + "="*80)
    print("###   开始测试新的并发解码函数 (decode_video_concurrently)   ###")
    print("="*80 + "\n")

    # --- 测试配置 ---
    test_video_path = "/app/videos/777.mp4"
    test_output_dir = "/app/tmp/ffmpeg_service/concurrent_decode_output"
    test_num_processes = 10
    # 可选：设置裁剪区域 [x1, y1, x2, y2] or None
    # 例如，从左上角(100, 50)裁剪一个 640x360 的区域
    # crop_x2 = 100 + 640
    # crop_y2 = 50 + 360
    # test_crop_area = [100, 50, crop_x2, crop_y2]
    test_crop_area = [0, 940, 1280, 1010]
    # ---

    if not os.path.exists(test_video_path):
        print(f"错误: 测试视频 '{test_video_path}' 不存在，测试终止。")
        return

    print(f"测试视频: {test_video_path}")
    print(f"输出目录: {test_output_dir}")
    print(f"并发进程数: {test_num_processes}")
    print(f"裁剪区域: {'无' if test_crop_area is None else test_crop_area}")
    print("-" * 80)

    # 调用新函数
    result = decode_video_concurrently(
        video_path=test_video_path,
        output_dir=test_output_dir,
        num_processes=test_num_processes,
        crop_area=test_crop_area
    )

    print("\n--- 测试完成 ---")
    print(f"函数返回状态: {'成功' if result['status'] else '失败'}")
    print(f"返回消息: {result['msg']}")
    
    # 检查输出目录和 task.json 是否生成
    task_json_path = os.path.join(test_output_dir, "task.json")
    if os.path.exists(task_json_path):
        print(f"报告文件已生成: {task_json_path}")
        # 可以在这里添加更多对json内容的验证
    else:
        print(f"错误: 未找到预期的报告文件 {task_json_path}")

    print("\n" + "="*80)
    print("###   并发解码函数测试结束   ###")
    print("="*80 + "\n")


if __name__ == "__main__":
    # 您可以在这里选择要运行的测试
    # main()  # 运行旧的分割分析功能
    test_concurrent_decoder() # 运行新的并发解码功能

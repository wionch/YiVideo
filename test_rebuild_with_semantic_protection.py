#!/usr/bin/env python3
"""
测试字幕重构功能（带语义保护）

重新执行 rebuild_subtitle_with_words 任务，生成优化后的字幕文件
"""
import requests
import json
import time
import os

# API 配置
API_BASE_URL = "http://localhost:8788"
TASK_ENDPOINT = f"{API_BASE_URL}/v1/tasks"

# 任务配置
task_config = {
    "task_name": "wservice.rebuild_subtitle_with_words",
    "task_id": f"test_rebuild_{int(time.time())}",
    "input_data": {
        "segments_file": "share/workflows/video_to_subtitle_task/nodes/faster_whisper.transcribe_audio/data/transcribe_data_task_id.json",
        "optimized_text_file": "share/workflows/video_to_subtitle_task/nodes/wservice.ai_optimize_text/data/transcribe_data_task_id_optimized_text.txt",
        "report": True  # 生成报告
    }
}

def check_input_files():
    """检查输入文件是否存在"""
    segments_file = f"share/workflows/video_to_subtitle_task/nodes/faster_whisper.transcribe_audio/data/transcribe_data_task_id.json"
    optimized_text_file = f"share/workflows/video_to_subtitle_task/nodes/wservice.ai_optimize_text/data/transcribe_data_task_id_optimized_text.txt"

    print("检查输入文件...")
    if os.path.exists(segments_file):
        print(f"✓ segments_file 存在: {segments_file}")
        file_size = os.path.getsize(segments_file)
        print(f"  文件大小: {file_size} bytes")
    else:
        print(f"✗ segments_file 不存在: {segments_file}")
        return False

    if os.path.exists(optimized_text_file):
        print(f"✓ optimized_text_file 存在: {optimized_text_file}")
        file_size = os.path.getsize(optimized_text_file)
        print(f"  文件大小: {file_size} bytes")
    else:
        print(f"✗ optimized_text_file 不存在: {optimized_text_file}")
        return False

    return True

def submit_task():
    """提交任务到 API"""
    print(f"\n提交任务到 {TASK_ENDPOINT}...")
    print(f"任务配置:\n{json.dumps(task_config, indent=2, ensure_ascii=False)}")

    try:
        response = requests.post(
            TASK_ENDPOINT,
            json=task_config,
            timeout=300
        )

        print(f"\n响应状态码: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            print(f"响应数据:\n{json.dumps(result, indent=2, ensure_ascii=False)}")
            return result
        else:
            print(f"请求失败: {response.status_code}")
            print(f"响应内容: {response.text}")
            return None

    except requests.exceptions.RequestException as e:
        print(f"请求异常: {e}")
        return None

def check_output_file(result):
    """检查输出文件"""
    if not result:
        return False

    print("\n检查输出文件...")

    # 从结果中获取输出文件路径
    output_data = result.get("output", {})
    optimized_file = output_data.get("optimized_segments_file")
    report_file = output_data.get("report_file")

    if optimized_file:
        print(f"✓ 优化后的字幕文件: {optimized_file}")
        if os.path.exists(optimized_file):
            file_size = os.path.getsize(optimized_file)
            print(f"  文件大小: {file_size} bytes")

            # 读取前几行查看内容
            with open(optimized_file, 'r', encoding='utf-8') as f:
                content = json.load(f)
                print(f"  片段数量: {len(content)}")
                print(f"  第一个片段: {content[0]}")
        else:
            print(f"  文件不存在!")

    if report_file:
        print(f"✓ 报告文件: {report_file}")
        if os.path.exists(report_file):
            file_size = os.path.getsize(report_file)
            print(f"  文件大小: {file_size} bytes")

    return True

def main():
    print("=" * 80)
    print("测试字幕重构功能（带语义保护）")
    print("=" * 80)

    # 1. 检查输入文件
    if not check_input_files():
        print("\n输入文件检查失败，终止执行")
        return

    # 2. 提交任务
    result = submit_task()

    # 3. 检查输出文件
    if result:
        check_output_file(result)
        print("\n✓ 任务执行完成！")
    else:
        print("\n✗ 任务执行失败")

if __name__ == "__main__":
    main()

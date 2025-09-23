# test.py
# -*- coding: utf-8 -*- 

"""
端到端集成测试脚本 (Stage 5)

该脚本用于测试AI工作流引擎的完整流程：
1. 发送请求到api_gateway，创建一个新的工作流。
2. 轮询状态查询接口，直到工作流完成或失败。
3. 打印最终结果。
"""

import requests
import time
import json
import os

# --- 配置 ---
API_BASE_URL = "http://localhost:8000"
TEST_VIDEO_PATH = "/app/videos/777.mp4"

# --- 工作流定义 ---

# 1. 完整OCR工作流
OCR_WORKFLOW_CONFIG = {
    "video_path": TEST_VIDEO_PATH,
    "workflow_config": {
        "workflow_chain": [
            "ffmpeg.extract_keyframes",
            "paddleocr.detect_subtitle_area",
            "ffmpeg.crop_subtitle_images",
            "paddleocr.perform_ocr",
            "paddleocr.postprocess_and_finalize"
        ]
    }
}

# 2. 纯ASR工作流
ASR_WORKFLOW_CONFIG = {
    "video_path": TEST_VIDEO_PATH,
    "workflow_config": {
        "workflow_chain": [
            "whisperx.generate_subtitles"
        ]
    }
}

# 3. ASR + LLM校对工作流 (新增)
ASR_PROOFREAD_WORKFLOW_CONFIG = {
    "video_path": TEST_VIDEO_PATH,
    "workflow_config": {
        "workflow_chain": [
            "whisperx.generate_subtitles",
            "llm.process_text"
        ],
        # 为llm.process_text任务提供额外参数
        "llm_params": {
            "action": "proofread",
            "provider": "gemini", # 可以指定gemini或deepseek，或不指定使用config.yml中的默认值
            "prompt": "你是一个专业的字幕校对员。请仔细校对以下由ASR生成的字幕文本，修正其中的错别字、语病和不通顺之处，使其更符合中文口语习惯，但不要改变原意。直接返回校对后的纯文本即可。\n\n原始文本如下：\n--- --- ---\n{text}"
        }
    }
}

def run_test(workflow_name: str, payload: dict):
    """执行单个工作流测试的全过程。"""
    print("="*80)
    print(f"🚀 开始执行 '{workflow_name}' 工作流测试")
    print("="*80)

    try:
        print(f"📤 正在向 {API_BASE_URL}/v1/workflows 发送POST请求...")
        print(f"   - 视频路径: {payload['video_path']}")
        chain_str = " -> ".join(payload['workflow_config']['workflow_chain'])
        print(f"   - 工作流链: {chain_str}")

        start_time = time.time()
        response = requests.post(f"{API_BASE_URL}/v1/workflows", json=payload, timeout=30)
        response.raise_for_status()

        workflow_id = response.json()["workflow_id"]
        print(f"✅ 请求成功，工作流已启动。 Workflow ID: {workflow_id}")

    except requests.exceptions.RequestException as e:
        print(f"❌ 启动工作流失败: {e}")
        return

    status_url = f"{API_BASE_URL}/v1/workflows/status/{workflow_id}"
    print(f"🔄 开始轮询状态: {status_url}")

    polling_interval = 5
    final_status = None

    while True:
        try:
            response = requests.get(status_url, timeout=30)
            response.raise_for_status()
            status_data = response.json()

            current_top_level_status = status_data.get("status", "UNKNOWN")
            stages = status_data.get("stages", {})

            print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] 工作流状态: {current_top_level_status}")
            for stage_name, stage_info in stages.items():
                print(f"    - 阶段: {stage_name:<35} | 状态: {stage_info.get('status', 'N/A')}")

            if current_top_level_status in ["SUCCESS", "FAILED"]:
                final_status = status_data
                break

            time.sleep(polling_interval)

        except requests.exceptions.RequestException as e:
            print(f"❌ 轮询状态时发生错误: {e}")
            time.sleep(polling_interval)
        except KeyboardInterrupt:
            print("\n🛑 用户中断测试。")
            return

    end_time = time.time()
    total_duration = end_time - start_time
    print("="*80)
    print(f"🏁 工作流 '{workflow_id}' 已结束，总耗时: {total_duration:.2f} 秒")
    print("="*80)
    print("最终状态和结果:")
    print(json.dumps(final_status, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    # --- 在这里选择要运行的测试 ---
    # 提示: 
    # 1. 运行前请确保docker-compose已启动所有服务。
    # 2. 确保已在 config.yml 中填入所使用模型的API Key。
    # 3. 确保 ./videos/test.mp4 文件存在。

    # 运行 ASR + LLM 校对测试 (新)
    run_test("ASR + LLM Proofread", ASR_PROOFREAD_WORKFLOW_CONFIG)

    # 运行 纯ASR 测试
    # run_test("ASR", ASR_WORKFLOW_CONFIG)

    # 运行 纯OCR 测试
    # run_test("OCR", OCR_WORKFLOW_CONFIG)

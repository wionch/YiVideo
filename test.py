import requests
import threading
import time
import json
import os # 导入 os 模块

# --- 配置区 ---
# 目标 URL
URL = "http://127.0.0.1:8080/ocr"

# 请求头
HEADERS = {
    'content-type': 'application/json'
}

# 请求体 (Payload)
PAYLOADS = [
    {
        "file": "https://www.paddleocr.ai/v3.1.1/images/Arch_cn.png",
        "visualize": False
    },
    {
        "file": "https://raw.githubusercontent.com/cuicheng01/PaddleX_doc_images/main/images/paddleocr/README/Arch_cn.jpg",
        "visualize": False
    }
]

# 并发线程数
THREAD_COUNT = 10
# 每个线程的请求次数
REQUESTS_PER_THREAD = 1

# --- 脚本核心逻辑 ---

def send_request(thread_id, request_num):
    """
    单个请求的发送函数，将被每个线程调用。
    """
    payload = PAYLOADS[(thread_id + request_num) % len(PAYLOADS)]
    
    log_prefix = f"[线程 {thread_id:02d} | 请求 {request_num:02d}]"
    print(f"{log_prefix} 正在发送请求，图片URL: {payload['file']}")
    
    start_time = time.time()
    
    try:
        response = requests.post(URL, headers=HEADERS, data=json.dumps(payload), timeout=120)
        
        end_time = time.time()
        elapsed_time = end_time - start_time
        
        print(f"{log_prefix} 响应状态码: {response.status_code} (耗时: {elapsed_time:.2f} 秒)")
        
        if response.status_code == 200:
            try:
                result_data = response.json()
                
                # --- 修改部分：保存文件而不是打印 ---
                # 定义文件名和路径
                output_dir = "test"
                filename = f"thread_{thread_id:02d}_req_{request_num:02d}.json"
                filepath = os.path.join(output_dir, filename)
                
                # 将结果写入 JSON 文件
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(result_data, f, indent=2, ensure_ascii=False)
                
                print(f"{log_prefix} 结果已成功保存至: {filepath}")
                # --- 修改结束 ---

            except json.JSONDecodeError:
                print(f"{log_prefix} 错误: 无法解析 JSON 响应体。原始文本: {response.text}")
        else:
            print(f"{log_prefix} 请求失败，响应内容: {response.text}")

    except requests.exceptions.RequestException as e:
        end_time = time.time()
        elapsed_time = end_time - start_time
        print(f"{log_prefix} 请求异常 (耗时: {elapsed_time:.2f} 秒): {e}")
    
    print("-" * 50)


if __name__ == "__main__":
    # --- 新增部分：创建输出目录 ---
    output_directory = "test"
    if not os.path.exists(output_directory):
        os.makedirs(output_directory)
        print(f"已创建目录: {output_directory}")
    # --- 新增结束 ---
    
    threads = []
    
    print(f"启动 {THREAD_COUNT} 个线程，每个线程发送 {REQUESTS_PER_THREAD} 个请求...")
    print("=" * 50)
    
    for i in range(THREAD_COUNT):
        for j in range(REQUESTS_PER_THREAD):
            thread = threading.Thread(target=send_request, args=(i + 1, j + 1))
            threads.append(thread)
            thread.start()
            
    for thread in threads:
        thread.join()
        
    print("=" * 50)
    print("所有并发请求已完成。")
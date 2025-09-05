# -*- coding: utf-8 -*-
import os
import time
import json
import multiprocessing
import yaml
from paddleocr import PaddleOCR

# --- 配置区 ---
# 图片路径。脚本位于 services/workers/paddleocr_service/，因此需要向上回溯到项目根目录
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
IMAGE_DIR = os.path.join(PROJECT_ROOT, "videos")
RESULT_FILE_PATH = os.path.join(IMAGE_DIR, "result.txt")
# 生成包含300个图片路径的列表，交替使用 1.png 和 2.png
base_image_names = ["1.png", "2.png"]
IMAGE_PATHS = [
    os.path.join(IMAGE_DIR, base_image_names[i % len(base_image_names)])
    for i in range(100)
]

# --- 全局变量，用于多进程 ---
# 每个工作进程将持有自己的OCR引擎实例
ocr_engine_process_global = None

# --- 工具函数 ---
def log_info(message):
    """打印带有时间戳的日志信息"""
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] {message}")

def format_ocr_results(image_path, ocr_output):
    """
    将PaddleOCR返回的字典格式原始输出，格式化为指定的JSON结构。
    """
    if not isinstance(ocr_output, list) or not ocr_output or not isinstance(ocr_output[0], dict):
        return {"image_path": image_path, "results": []}

    data_dict = ocr_output[0]
    
    positions = data_dict.get('rec_polys', [])
    texts = data_dict.get('rec_texts', [])
    confidences = data_dict.get('rec_scores', [])

    formatted_results = []
    for i in range(len(texts)):
        formatted_results.append({
            "text": texts[i],
            "position": positions[i].tolist() if hasattr(positions[i], 'tolist') else positions[i],
            "confidence": confidences[i]
        })
        
    return {"image_path": image_path, "results": formatted_results}

def append_results_to_file(test_name, results, is_first_write=False):
    """
    将指定测试的识别结果追加写入到结果文件中。
    """
    if not results:
        log_info(f"'{test_name}' 没有产生任何结果，无需写入文件。")
        return

    mode = 'w' if is_first_write else 'a'
    try:
        with open(RESULT_FILE_PATH, mode, encoding='utf-8') as f:
            f.write(f"--- {test_name} ---\n")
            json.dump(results, f, ensure_ascii=False, indent=4)
            f.write("\n\n")
        log_info(f"'{test_name}' 的识别结果已成功保存到: {RESULT_FILE_PATH}")
    except Exception as e:
        log_info(f"错误：保存 '{test_name}' 的结果到文件失败: {e}")

# --- 测试实现 ---

def test_gpu_batch_processing():
    """
    测试GPU批处理模式：使用PaddleOCR的批量预测功能一次性处理多张图片。
    返回 (初始化耗时, OCR总耗时, 总耗时, 结果列表)
    """
    log_info("--- 开始测试：GPU批处理模式 ---")
    
    all_formatted_results = []
    
    # 1. 初始化PaddleOCR并计时
    log_info("正在初始化PaddleOCR引擎 (GPU批处理)...")
    init_start_time = time.time()
    try:
        # 使用PaddleOCR 3.x的正确参数
        ocr_engine = PaddleOCR(
            lang="ch", 
            device="gpu",  # 指定使用GPU设备
            text_recognition_batch_size=8,  # 设置识别批处理数量 (原rec_batch_num)
            text_det_limit_side_len=960,  # 检测模型输入图像长边尺寸 (原det_limit_side_len)
            use_tensorrt=False,  # 可选：启用TensorRT加速
            precision="fp32"  # 推理精度
        )
    except Exception as e:
        log_info(f"PaddleOCR 初始化失败: {e}")
        return 0.0, 0.0, 0.0, []
    init_end_time = time.time()
    init_duration = init_end_time - init_start_time
    log_info(f"PaddleOCR（GPU批处理）初始化完成 (耗时: {init_duration:.4f} 秒)。")

    # 2. 检查图片文件是否存在
    valid_image_paths = []
    for img_path in IMAGE_PATHS:
        if os.path.exists(img_path):
            valid_image_paths.append(img_path)
        else:
            log_info(f"错误：找不到图片文件 {img_path}")
    
    if not valid_image_paths:
        log_info("错误：没有找到有效的图片文件。")
        return init_duration, 0.0, init_duration, []
    
    log_info(f"找到 {len(valid_image_paths)} 个有效图片文件。")

    # 3. 批处理识别图片
    log_info("开始批处理识别所有图片...")
    batch_start_time = time.time()
    
    try:
        # 使用PaddleOCR的批量预测功能
        log_info("调用批量预测API...")
        batch_results = ocr_engine.predict(valid_image_paths)
        
        # 格式化批量结果
        log_info("正在格式化批量识别结果...")
        for i, (img_path, result) in enumerate(zip(valid_image_paths, batch_results)):
            formatted_result = format_ocr_results(img_path, [result])  # 包装成列表以匹配原格式
            all_formatted_results.append(formatted_result)
            if (i + 1) % 50 == 0:  # 每50张图片输出一次进度
                log_info(f"  - 已处理 {i+1}/{len(valid_image_paths)} 张图片")
        
    except Exception as e:
        log_info(f"批量预测过程中发生错误: {e}")
        # 如果批处理失败，回退到逐张处理
        log_info("回退到逐张处理模式...")
        for i, img_path in enumerate(valid_image_paths):
            try:
                result = ocr_engine.predict(img_path)
                all_formatted_results.append(format_ocr_results(img_path, result))
                if (i + 1) % 50 == 0:
                    log_info(f"  - 已处理 {i+1}/{len(valid_image_paths)} 张图片")
            except Exception as single_error:
                log_info(f"单张图片处理失败 {img_path}: {single_error}")
    
    batch_end_time = time.time()
    batch_duration = batch_end_time - batch_start_time

    log_info("批处理识别完成。")
    log_info(f"GPU批处理 - 纯OCR识别总耗时: {batch_duration:.4f} 秒")
    log_info("--- GPU批处理测试结束 ---")
    
    total_elapsed_time = init_duration + batch_duration
    return init_duration, batch_duration, total_elapsed_time, all_formatted_results

def test_single_instance_loop():
    """
    测试单实例循环识别多张图片。
    返回 (初始化耗时, OCR总耗时, 总耗时, 结果列表)
    """
    log_info("--- 开始测试：单实例循环识别 ---")
    
    all_formatted_results = []
    
    # 1. 【新日志点】初始化PaddleOCR并计时
    log_info("正在初始化PaddleOCR引擎 (单实例)...")
    init_start_time = time.time()
    try:
        ocr_engine = PaddleOCR(lang="ch")
    except Exception as e:
        log_info(f"PaddleOCR 初始化失败: {e}")
        return 0.0, 0.0, 0.0, []
    init_end_time = time.time()
    init_duration = init_end_time - init_start_time
    log_info(f"PaddleOCR（单实例）初始化完成 (耗时: {init_duration:.4f} 秒)。")

    # 2. 【新日志点】循环识别图片并对每次识别计时
    total_ocr_duration = 0
    log_info("开始循环识别所有图片...")
    
    # 只计算循环识别部分的时间
    loop_start_time = time.time()
    for i, img_path in enumerate(IMAGE_PATHS):
        if not os.path.exists(img_path):
            log_info(f"错误：找不到图片文件 {img_path}")
            continue
        
        # 【新日志点】单张图片识别计时
        ocr_start_time = time.time()
        result = ocr_engine.predict(img_path)
        ocr_end_time = time.time()
        
        ocr_duration = ocr_end_time - ocr_start_time
        total_ocr_duration += ocr_duration
        log_info(f"  - 图片 {i+1}/{len(IMAGE_PATHS)}: {os.path.basename(img_path)} (识别耗时: {ocr_duration:.4f} 秒)")
        
        all_formatted_results.append(format_ocr_results(img_path, result))
    
    loop_end_time = time.time()
    loop_duration = loop_end_time - loop_start_time

    log_info("所有图片识别完成。")
    log_info(f"【新】单实例 - 纯OCR识别总耗时: {total_ocr_duration:.4f} 秒 (循环体总耗时: {loop_duration:.4f} 秒)")
    log_info("--- 单实例测试结束 ---")
    
    total_elapsed_time = init_duration + loop_duration
    return init_duration, total_ocr_duration, total_elapsed_time, all_formatted_results

# --- 多进程相关函数 ---

def get_num_workers_from_config():
    try:
        # 导入通用配置加载器
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))
        from utils.config_loader import get_num_workers
        num_workers = get_num_workers(section='area_detector', default_workers=2)
        log_info(f"从通用配置加载器加载：num_workers = {num_workers}")
        return num_workers
    except Exception as e:
        log_info(f"通用配置加载器加载失败: {e}")
    
    # 后备方案：尝试直接读取配置文件
    config_path = os.path.join(PROJECT_ROOT, "config.yml")
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        num_workers = config.get('area_detector', {}).get('num_workers')
        if isinstance(num_workers, int) and num_workers > 0:
            log_info(f"从 config.yml 加载配置：num_workers = {num_workers}")
            return num_workers
    except Exception: pass
    log_info(f"警告：未找到有效配置，将使用默认值 2。")
    return 2

def worker_initializer():
    global ocr_engine_process_global
    pid = os.getpid()
    log_info(f"[PID: {pid}] 开始初始化独立的PaddleOCR引擎...")
    
    # 使用通用配置加载器获取语言设置
    try:
        # 导入通用配置加载器
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))
        from utils.config_loader import get_ocr_lang
        lang = get_ocr_lang(default_lang='ch')
        log_info(f"[PID: {pid}] 从配置加载语言设置: {lang}")
    except Exception as e:
        lang = 'ch'  # 后备默认值
        log_info(f"[PID: {pid}] 配置加载失败，使用默认语言: {lang}，错误: {e}")
    
    # 【日志点】记录每个子进程的引擎初始化时间
    init_start_time = time.time()
    ocr_engine_process_global = PaddleOCR(lang=lang)
    init_end_time = time.time()
    
    init_duration = init_end_time - init_start_time
    log_info(f"[PID: {pid}] PaddleOCR引擎初始化完成 (语言: {lang}, 耗时: {init_duration:.4f} 秒)。")

def ocr_worker_task(img_path_tuple):
    global ocr_engine_process_global
    pid = os.getpid()
    i, img_path = img_path_tuple

    if not ocr_engine_process_global: return None
    if not os.path.exists(img_path): return None

    ocr_start_time = time.time()
    result = ocr_engine_process_global.predict(img_path)
    ocr_end_time = time.time()
    ocr_duration = ocr_end_time - ocr_start_time
    log_info(f"[PID: {pid}] 图片 {i+1}/{len(IMAGE_PATHS)}: {os.path.basename(img_path)} (识别耗时: {ocr_duration:.4f} 秒)")
    
    return format_ocr_results(img_path, result)

def test_multiprocess_concurrent():
    """
    测试多进程并发识别。
    返回 (OCR执行耗时, 总耗时, 结果列表)
    """
    log_info("--- 开始测试：多进程并发识别 ---")
    
    num_processes = get_num_workers_from_config()
    log_info(f"创建 {num_processes} 个子进程进行并发处理...")
    
    overall_start_time = time.time()
    
    pool = None
    all_formatted_results = []
    map_duration = 0
    try:
        indexed_image_paths = list(enumerate(IMAGE_PATHS))
        pool = multiprocessing.Pool(processes=num_processes, initializer=worker_initializer)
        
        log_info("开始将任务映射到工作进程...")
        
        # 【日志点】对 pool.map() 计时，这是多进程模式下的总OCR执行时间
        map_start_time = time.time()
        all_formatted_results = pool.map(ocr_worker_task, indexed_image_paths)
        map_end_time = time.time()
        
        map_duration = map_end_time - map_start_time
        log_info(f"【新】多进程 - 纯OCR识别总耗时 (pool.map 耗时): {map_duration:.4f} 秒。")
        
        log_info("正在关闭进程池...")
        pool.close()
        pool.join()
        log_info("进程池已关闭。")
        
    except Exception as e:
        log_info(f"多进程处理期间发生错误: {e}")
        if pool:
            pool.terminate()
            pool.join()

    overall_end_time = time.time()
    overall_elapsed_time = overall_end_time - overall_start_time
    
    log_info("所有并发任务已完成。")
    log_info("--- 多进程测试结束 ---")
    return map_duration, overall_elapsed_time, [res for res in all_formatted_results if res]

# --- 主函数 ---

def main():
    """主函数，执行并对比三种测试模式"""
    log_info("==========================================")
    log_info("  PaddleOCR 三模式性能对比测试 (Enhanced)")
    log_info("==========================================")
    log_info(f"测试平台: {os.name}, Python: {multiprocessing.get_start_method()}")
    log_info(f"待识别图片数量: {len(IMAGE_PATHS)}")
    log_info("------------------------------------------")

    # 执行GPU批处理测试
    log_info("🚀 第一阶段：GPU批处理模式")
    b_init_t, b_ocr_t, b_total_t, b_results = test_gpu_batch_processing()
    log_info(f"GPU批处理模式总耗时: {b_total_t:.4f} 秒")
    append_results_to_file("GPU批处理识别", b_results, is_first_write=True)
    log_info("------------------------------------------")

    # 执行单实例测试
    log_info("🔄 第二阶段：单实例循环模式")
    s_init_t, s_ocr_t, s_total_t, s_results = test_single_instance_loop()
    log_info(f"单实例模式总耗时: {s_total_t:.4f} 秒")
    append_results_to_file("单实例循环识别", s_results)
    log_info("------------------------------------------")
    
    # 执行多进程测试
    log_info("⚡ 第三阶段：多进程并发模式")
    m_ocr_t, m_total_t, m_results = test_multiprocess_concurrent()
    log_info(f"多进程并发总耗时: {m_total_t:.4f} 秒")
    append_results_to_file("多进程并发识别", m_results)
    log_info("------------------------------------------")

    # 三模式详细对比分析
    log_info("================== 三模式性能对比分析 ==================")
    if all(t > 0.01 for t in [b_total_t, s_total_t, m_total_t]):
        # 估算多进程的初始化时间
        m_init_t = m_total_t - m_ocr_t
        
        log_info("【🔧 引擎初始化耗时对比】")
        log_info(f"  GPU批处理: {b_init_t:.4f} 秒")
        log_info(f"  单进程:     {s_init_t:.4f} 秒")
        log_info(f"  多进程:     {m_init_t:.4f} 秒 (估算值，包含进程创建开销)")
        
        log_info("【⚡ 纯OCR识别耗时对比】")
        log_info(f"  GPU批处理: {b_ocr_t:.4f} 秒")
        log_info(f"  单进程:     {s_ocr_t:.4f} 秒")
        log_info(f"  多进程:     {m_ocr_t:.4f} 秒")
        
        log_info("【📊 总耗时对比】")
        log_info(f"  GPU批处理: {b_total_t:.4f} 秒")
        log_info(f"  单进程:     {s_total_t:.4f} 秒")
        log_info(f"  多进程:     {m_total_t:.4f} 秒")
        
        log_info("【🏆 性能加速比分析】")
        if b_ocr_t > 0 and s_ocr_t > 0 and m_ocr_t > 0:
            # 以单进程为基准计算加速比
            batch_speedup_ocr = s_ocr_t / b_ocr_t
            multi_speedup_ocr = s_ocr_t / m_ocr_t
            
            batch_speedup_total = s_total_t / b_total_t
            multi_speedup_total = s_total_t / m_total_t
            
            # 批处理与多进程的对比
            batch_vs_multi_ocr = m_ocr_t / b_ocr_t
            batch_vs_multi_total = m_total_t / b_total_t
            
            log_info(f"  纯OCR识别加速比：")
            log_info(f"    - GPU批处理 vs 单进程: {batch_speedup_ocr:.2f}x 倍加速")
            log_info(f"    - 多进程 vs 单进程:     {multi_speedup_ocr:.2f}x 倍加速")
            log_info(f"    - GPU批处理 vs 多进程: {batch_vs_multi_ocr:.2f}x {'倍加速' if batch_vs_multi_ocr < 1 else '倍优势'}")
            
            log_info(f"  总耗时加速比：")
            log_info(f"    - GPU批处理 vs 单进程: {batch_speedup_total:.2f}x 倍加速")
            log_info(f"    - 多进程 vs 单进程:     {multi_speedup_total:.2f}x 倍加速")
            log_info(f"    - GPU批处理 vs 多进程: {batch_vs_multi_total:.2f}x {'倍加速' if batch_vs_multi_total < 1 else '倍优势'}")
        
        log_info("【📈 结论与建议】")
        best_method = "GPU批处理"
        best_time = b_total_t
        
        if s_total_t < best_time:
            best_method = "单进程"
            best_time = s_total_t
        if m_total_t < best_time:
            best_method = "多进程"
            best_time = m_total_t
        
        log_info(f"  🥇 最佳性能: {best_method} (总耗时: {best_time:.4f} 秒)")
        
        # 根据结果给出使用建议
        if batch_speedup_total > multi_speedup_total and batch_speedup_total > 1.2:
            log_info(f"  💡 建议: GPU批处理是最优选择，特别适用于大批量图片处理")
        elif multi_speedup_total > 1.5:
            log_info(f"  💡 建议: 多进程并发适用于CPU密集型场景或GPU资源受限时")
        else:
            log_info(f"  💡 建议: 单进程模式简单可靠，适用于小批量处理或调试场景")
        
        log_info("【🔍 性能分析】")
        log_info("  GPU批处理优势: 减少模型加载开销，充分利用GPU并行计算能力")
        log_info("  多进程优势: 充分利用多核CPU，避免Python GIL限制") 
        log_info("  单进程优势: 内存占用低，逻辑简单，便于调试和维护")
        
    else:
        log_info("测试未能成功完成或耗时过短，无法进行有效比较。")
    
    log_info("=======================================================")

    # 输出测试数据统计
    log_info("【📋 测试数据统计】")
    log_info(f"  GPU批处理结果数: {len(b_results)}")
    log_info(f"  单进程结果数:     {len(s_results)}")
    log_info(f"  多进程结果数:     {len(m_results)}")
    log_info("=======================================================")


if __name__ == '__main__':
    if multiprocessing.get_start_method(allow_none=True) != 'spawn':
        multiprocessing.set_start_method("spawn", force=True)
    multiprocessing.freeze_support()
    main()
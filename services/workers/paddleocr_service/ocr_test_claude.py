#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PaddleOCR 3.x 版本模型对比测试脚本

目的：排查OCR识别准确率低的问题
- 分别测试 PP-OCRv5、PP-OCRv4、PP-OCRv3 模型
- 测试不同参数配置
- 对比识别效果，找出最佳配置

作者: Claude
日期: 2025-09-08
"""

import os
import time
import json
import sys
from pathlib import Path
import cv2
import numpy as np

# 添加项目路径到系统路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from paddleocr import PaddleOCR
    print("✅ PaddleOCR 导入成功")
except ImportError as e:
    print(f"❌ PaddleOCR 导入失败: {e}")
    sys.exit(1)

# 测试图像路径
TEST_IMAGES = {
    "full_frame": "./pics/full_frame_608.jpg",  # 字幕帧截图
    "cropped_subtitle": "./pics/cropped_subtitle_area.jpg"  # 字幕条
}

# PaddleOCR 3.x 支持的模型版本
OCR_VERSIONS = ["PP-OCRv5", "PP-OCRv4", "PP-OCRv3"]

# 在线测试的参考参数配置（从用户提供的信息中获取）
ONLINE_TEST_CONFIG = {
    "use_doc_orientation_classify": False,    # 不使用文档图像方向分类模块
    "use_doc_unwarping": False,              # 不使用文档扭曲矫正模块  
    "use_textline_orientation": False,       # 不使用文本行方向分类模块
    "text_det_limit_side_len": 736,         # 文本检测的图像边长限制
    "text_det_thresh": 0.30,                # 文本检测像素阈值
    "text_det_box_thresh": 0.60,            # 文本检测框阈值
    "text_det_unclip_ratio": 1.50,          # 文本检测扩张系数
    "text_rec_score_thresh": 0              # 文本识别阈值
}

def log_info(message):
    """打印带时间戳的日志"""
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}")

def load_test_images():
    """加载测试图像，检查文件是否存在"""
    images = {}
    for name, path in TEST_IMAGES.items():
        if os.path.exists(path):
            images[name] = path
            log_info(f"✅ 找到测试图像: {name} -> {path}")
        else:
            log_info(f"❌ 测试图像不存在: {name} -> {path}")
    
    if not images:
        log_info("❌ 没有找到任何测试图像，请检查路径")
        return None
    
    return images

def format_ocr_results(image_name, ocr_output):
    """格式化PaddleOCR 3.x的输出结果"""
    if not ocr_output or not isinstance(ocr_output, list) or len(ocr_output) == 0:
        return {"image": image_name, "texts": [], "scores": [], "boxes": []}
    
    result = ocr_output[0]  # 获取第一个结果
    
    if isinstance(result, dict):
        # PaddleOCR 3.x predict方法返回字典格式
        texts = result.get('rec_texts', [])
        scores = result.get('rec_scores', [])
        boxes = result.get('rec_polys', [])
        
        # 转换boxes为可序列化格式
        serializable_boxes = []
        for box in boxes:
            if hasattr(box, 'tolist'):
                serializable_boxes.append(box.tolist())
            else:
                serializable_boxes.append(box)
        
        return {
            "image": image_name,
            "texts": texts,
            "scores": scores,
            "boxes": serializable_boxes
        }
    else:
        # 兼容旧格式（如果还有的话）
        texts = []
        scores = []
        boxes = []
        
        for line in result:
            if len(line) >= 2:
                # line[0] 是边界框，line[1] 是文本信息
                if line[1] and len(line[1]) >= 2:
                    texts.append(line[1][0])  # 文本内容
                    scores.append(line[1][1])  # 置信度
                    
                    # 处理边界框
                    if line[0] is not None:
                        if hasattr(line[0], 'tolist'):
                            boxes.append(line[0].tolist())
                        else:
                            boxes.append(line[0])
        
        return {
            "image": image_name,
            "texts": texts,
            "scores": scores,
            "boxes": boxes
        }

def test_ocr_model(ocr_version, images, lang="ch"):
    """测试指定版本的OCR模型"""
    log_info(f"🔍 开始测试 {ocr_version} 模型 (语言: {lang})")
    
    # 基础配置
    ocr_config = {
        "lang": lang,
        "ocr_version": ocr_version
    }
    
    # 添加在线测试参考配置
    ocr_config.update(ONLINE_TEST_CONFIG)
    
    try:
        # 初始化OCR引擎
        log_info(f"  📦 初始化 {ocr_version} 引擎...")
        init_start = time.time()
        ocr_engine = PaddleOCR(**ocr_config)
        init_time = time.time() - init_start
        log_info(f"  ✅ {ocr_version} 引擎初始化完成 (耗时: {init_time:.2f}s)")
        
        # 测试每个图像
        results = {}
        for image_name, image_path in images.items():
            log_info(f"  🖼️  识别图像: {image_name}")
            
            try:
                ocr_start = time.time()
                ocr_output = ocr_engine.predict(image_path)
                ocr_time = time.time() - ocr_start
                
                # 格式化结果
                formatted_result = format_ocr_results(image_name, ocr_output)
                formatted_result["ocr_time"] = ocr_time
                formatted_result["model_version"] = ocr_version
                
                results[image_name] = formatted_result
                
                # 打印识别结果
                texts = formatted_result["texts"]
                scores = formatted_result["scores"]
                
                log_info(f"    ⏱️  识别耗时: {ocr_time:.3f}s")
                log_info(f"    📝 检测到文本数量: {len(texts)}")
                
                for i, (text, score) in enumerate(zip(texts, scores)):
                    log_info(f"      [{i+1}] \"{text}\" (置信度: {score:.3f})")
                
                # 如果没有识别到文本
                if not texts:
                    log_info(f"    ⚠️  {ocr_version} 未识别到任何文本")
                
            except Exception as e:
                log_info(f"    ❌ {ocr_version} 识别 {image_name} 失败: {e}")
                results[image_name] = {
                    "image": image_name,
                    "error": str(e),
                    "model_version": ocr_version
                }
        
        return results
        
    except Exception as e:
        log_info(f"  ❌ {ocr_version} 引擎初始化失败: {e}")
        return None

def test_different_languages():
    """测试不同语言设置的效果"""
    log_info("🌍 测试不同语言设置")
    
    languages = [
        ("ch", "中文"),
        ("en", "英文"), 
        ("chinese_cht", "繁体中文")
    ]
    
    images = load_test_images()
    if not images:
        return {}
    
    results = {}
    
    # 只用PP-OCRv5测试不同语言
    for lang_code, lang_name in languages:
        log_info(f"  🔤 测试语言: {lang_name} ({lang_code})")
        try:
            lang_result = test_ocr_model("PP-OCRv5", images, lang=lang_code)
            if lang_result:
                results[f"PP-OCRv5_{lang_code}"] = lang_result
        except Exception as e:
            log_info(f"    ❌ 语言 {lang_name} 测试失败: {e}")
    
    return results

def save_results_to_file(all_results, filename="ocr_test_results_claude.json"):
    """保存测试结果到JSON文件"""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)
        log_info(f"📄 测试结果已保存到: {filename}")
    except Exception as e:
        log_info(f"❌ 保存结果文件失败: {e}")

def compare_results(all_results):
    """对比不同模型的识别结果"""
    log_info("📊 ===== 识别结果对比分析 =====")
    
    # 统计每个模型的识别效果
    for model_config, model_results in all_results.items():
        log_info(f"\n🔹 {model_config} 结果统计:")
        
        for image_name, result in model_results.items():
            if "error" in result:
                log_info(f"  {image_name}: ❌ 识别失败 - {result['error']}")
                continue
                
            texts = result.get("texts", [])
            scores = result.get("scores", [])
            ocr_time = result.get("ocr_time", 0)
            
            if texts:
                combined_text = " ".join(texts)
                avg_confidence = sum(scores) / len(scores) if scores else 0
                log_info(f"  {image_name}: ✅ 识别成功")
                log_info(f"    📝 文本: \"{combined_text}\"")
                log_info(f"    📈 平均置信度: {avg_confidence:.3f}")
                log_info(f"    ⏱️  耗时: {ocr_time:.3f}s")
            else:
                log_info(f"  {image_name}: ⚠️  未识别到文本")

def main():
    """主函数"""
    log_info("🚀 ===== PaddleOCR 3.x 模型对比测试开始 =====")
    log_info(f"📍 工作目录: {os.getcwd()}")
    
    # 检查测试图像
    images = load_test_images()
    if not images:
        log_info("❌ 没有可用的测试图像，退出测试")
        return
    
    all_results = {}
    
    # 1. 测试所有OCR版本（使用中文）
    log_info("\n🔍 ===== 第一阶段：测试所有OCR版本 =====")
    for version in OCR_VERSIONS:
        result = test_ocr_model(version, images, lang="ch")
        if result:
            all_results[f"{version}_ch"] = result
    
    # 2. 测试不同语言设置
    log_info("\n🌍 ===== 第二阶段：测试不同语言设置 =====")
    lang_results = test_different_languages()
    all_results.update(lang_results)
    
    # 3. 测试优化参数配置（基于PP-OCRv5）
    log_info("\n⚙️ ===== 第三阶段：测试优化参数配置 =====")
    
    # 测试更宽松的阈值配置（可能提高召回率）
    relaxed_config = ONLINE_TEST_CONFIG.copy()
    relaxed_config.update({
        "text_det_thresh": 0.20,      # 降低检测阈值
        "text_det_box_thresh": 0.50,  # 降低边界框阈值
        "text_rec_score_thresh": 0,   # 保持识别阈值为0
        "text_det_unclip_ratio": 2.0  # 增大扩张系数
    })
    
    log_info("  🔧 测试宽松参数配置（PP-OCRv5）")
    try:
        ocr_relaxed = PaddleOCR(lang="ch", ocr_version="PP-OCRv5", **relaxed_config)
        relaxed_results = {}
        
        for image_name, image_path in images.items():
            log_info(f"    🖼️  识别图像: {image_name} (宽松配置)")
            try:
                ocr_start = time.time()
                ocr_output = ocr_relaxed.predict(image_path)
                ocr_time = time.time() - ocr_start
                
                formatted_result = format_ocr_results(image_name, ocr_output)
                formatted_result["ocr_time"] = ocr_time
                formatted_result["model_version"] = "PP-OCRv5_relaxed"
                
                relaxed_results[image_name] = formatted_result
                
                texts = formatted_result["texts"]
                scores = formatted_result["scores"]
                
                log_info(f"      ⏱️  识别耗时: {ocr_time:.3f}s")
                log_info(f"      📝 检测到文本数量: {len(texts)}")
                
                for i, (text, score) in enumerate(zip(texts, scores)):
                    log_info(f"        [{i+1}] \"{text}\" (置信度: {score:.3f})")
                    
            except Exception as e:
                log_info(f"      ❌ 宽松配置识别失败: {e}")
                relaxed_results[image_name] = {
                    "image": image_name,
                    "error": str(e),
                    "model_version": "PP-OCRv5_relaxed"
                }
        
        all_results["PP-OCRv5_relaxed"] = relaxed_results
        
    except Exception as e:
        log_info(f"  ❌ 宽松参数配置测试失败: {e}")
    
    # 4. 保存和分析结果
    log_info("\n📊 ===== 结果保存和分析 =====")
    save_results_to_file(all_results)
    compare_results(all_results)
    
    # 5. 给出建议
    log_info("\n💡 ===== 优化建议 =====")
    log_info("1. 检查测试结果JSON文件以获取详细数据")
    log_info("2. 对比不同模型版本的识别准确率")
    log_info("3. 关注置信度分数，低置信度可能表示识别不准确")
    log_info("4. 如果某个模型版本效果更好，请考虑在生产环境中切换")
    log_info("5. 参数调优：根据测试结果调整检测和识别阈值")
    
    log_info("\n✅ ===== 测试完成 =====")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log_info("\n⚠️  用户中断测试")
    except Exception as e:
        log_info(f"\n❌ 测试过程中发生未预期错误: {e}")
        import traceback
        traceback.print_exc()
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
独立的PaddleOCR图片识别脚本
使用PP-OCRv5_server_rec模型识别指定图片，并以Markdown格式输出识别结果
"""

import logging
import os
import sys
from typing import Any
from typing import Dict
from typing import List

from paddleocr import PaddleOCR

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class XinlanOCR:
    """
    独立的OCR识别类，使用PaddleOCR进行图片文字识别
    """
    
    def __init__(self, text_recognition_model_name: str = "PP-OCRv5_server_rec"):
        """
        初始化OCR引擎
        
        Args:
            text_recognition_model_name: 识别模型名称，默认为PP-OCRv5_server_rec
        """
        self.text_recognition_model_name = text_recognition_model_name
        # logger.info(f"初始化PaddleOCR引擎，使用模型: {text_recognition_model_name}")
        
        try:
            # 完全按照现有OCR模块的成功方式，最简化初始化
            ocr_kwargs = {'lang': 'ch'}  # 只保留最基本的语言参数
            
            # logger.info(f"PaddleOCR初始化参数: {ocr_kwargs}")
            self.ocr = PaddleOCR(**ocr_kwargs)
            # logger.info("PaddleOCR引擎初始化成功")
        except Exception as e:
            logger.error(f"PaddleOCR引擎初始化失败: {e}")
            raise
    
    def recognize_image(self, image_path: str) -> List[Dict[str, Any]]:
        """
        识别单张图片中的文字
        
        Args:
            image_path: 图片文件路径
            
        Returns:
            包含识别结果的列表，每个元素包含文字内容、位置坐标和置信度
        """
        if not os.path.exists(image_path):
            logger.error(f"图片文件不存在: {image_path}")
            return []
        
        try:
            # logger.info(f"开始识别图片: {image_path}")
            # 使用PaddleOCR进行文字识别
            results = self.ocr.predict(image_path)
            
            if not results or len(results) == 0:
                # logger.warning(f"图片中未识别到文字: {image_path}")
                return []
            
            # 解析predict()方法返回的结果结构
            result_data = results[0]  # 取第一个结果（通常只有一个）
            
            # 从结果中提取文字、置信度和坐标
            texts = result_data.get('rec_texts', [])
            scores = result_data.get('rec_scores', [])
            polys = result_data.get('rec_polys', [])
            
            if not texts:
                # logger.warning(f"图片中未识别到文字内容: {image_path}")
                return []
            
            # 构建解析结果
            parsed_results = []
            for i, text in enumerate(texts):
                if text and text.strip():
                    # 获取对应的置信度
                    confidence = scores[i] if i < len(scores) else 0.0
                    
                    # 获取对应的坐标框
                    box = polys[i].tolist() if i < len(polys) else None
                    
                    parsed_results.append({
                        'text': text.strip(),
                        'confidence': confidence,
                        'box': box
                    })
            
            # logger.info(f"识别完成，共识别到 {len(parsed_results)} 条文字")
            return parsed_results
            
        except Exception as e:
            logger.error(f"图片识别失败 {image_path}: {e}")
            return []
    
    def format_to_markdown(self, results: List[Dict[str, Any]], image_path: str) -> str:
        """
        将识别结果格式化为Markdown格式
        
        Args:
            results: 识别结果列表
            image_path: 图片路径（用于标题）
            
        Returns:
            Markdown格式的文字内容
        """
        if not results:
            return f"## {os.path.basename(image_path)}\n\n*未识别到文字内容*\n\n"
        
        # 构建Markdown内容
        markdown_content = []
        markdown_content.append(f"## {os.path.basename(image_path)}")
        markdown_content.append("")  # 空行
        
        # 按置信度降序排列文字内容
        sorted_results = sorted(results, key=lambda x: x['confidence'], reverse=True)
        
        # 添加识别统计信息
        total_texts = len(sorted_results)
        avg_confidence = sum(r['confidence'] for r in sorted_results) / total_texts
        markdown_content.append(f"**识别统计:** 共识别到 {total_texts} 条文字，平均置信度: {avg_confidence:.2f}")
        markdown_content.append("")
        
        # 添加识别的文字内容
        markdown_content.append("### 识别内容")
        markdown_content.append("")
        
        for i, result in enumerate(sorted_results, 1):
            text = result['text']
            confidence = result['confidence']
            # 格式化为有序列表，包含置信度信息
            markdown_content.append(f"{i}. **{text}** *(置信度: {confidence:.3f})*")
        
        markdown_content.append("")  # 结尾空行
        
        return "\n".join(markdown_content)
    
    def process_images(self, image_paths: List[str]) -> str:
        """
        批量处理图片并生成Markdown报告
        
        Args:
            image_paths: 图片文件路径列表
            
        Returns:
            完整的Markdown格式报告
        """
        # logger.info(f"开始批量处理 {len(image_paths)} 张图片")
        
        # Markdown文档头部
        markdown_parts = []
        markdown_parts.append("# PaddleOCR 图片文字识别报告")
        markdown_parts.append("")
        markdown_parts.append(f"**识别模型:** {self.text_recognition_model_name}")
        markdown_parts.append(f"**处理图片数量:** {len(image_paths)}")
        markdown_parts.append("")
        markdown_parts.append("---")
        markdown_parts.append("")
        
        # 处理每张图片
        successful_count = 0
        for image_path in image_paths:
            try:
                # 识别图片
                results = self.recognize_image(image_path)
                
                # 格式化为Markdown
                image_markdown = self.format_to_markdown(results, image_path)
                markdown_parts.append(image_markdown)
                
                if results:
                    successful_count += 1
                    
            except Exception as e:
                logger.error(f"处理图片失败 {image_path}: {e}")
                # 添加错误信息到Markdown
                error_markdown = f"## {os.path.basename(image_path)}\n\n*❌ 处理失败: {str(e)}*\n\n"
                markdown_parts.append(error_markdown)
        
        # 添加处理总结
        markdown_parts.append("---")
        markdown_parts.append("")
        markdown_parts.append("## 处理总结")
        markdown_parts.append("")
        markdown_parts.append(f"- **总图片数:** {len(image_paths)}")
        markdown_parts.append(f"- **成功识别:** {successful_count}")
        markdown_parts.append(f"- **识别失败:** {len(image_paths) - successful_count}")
        
        final_markdown = "\n".join(markdown_parts)
        # logger.info(f"批量处理完成，成功识别 {successful_count}/{len(image_paths)} 张图片")
        
        return final_markdown


def main():
    """
    主函数：处理指定的图片文件
    """
    # 指定要识别的图片路径
    image_paths = [
        "/app/videos/1.jpg",
        "/app/videos/2.jpg"
    ]
    
    try:
        # 初始化OCR引擎
        ocr_engine = XinlanOCR(text_recognition_model_name="PP-OCRv5_server_rec")
        
        # 验证图片文件存在性
        valid_paths = []
        for path in image_paths:
            if os.path.exists(path):
                valid_paths.append(path)
                # logger.info(f"找到图片文件: {path}")
            else:
                pass  # logger.warning(f"图片文件不存在: {path}")
        
        if not valid_paths:
            logger.error("没有找到有效的图片文件")
            return
        
        # 批量处理图片
        markdown_result = ocr_engine.process_images(valid_paths)
        
        # 输出Markdown结果
        print("\n" + "="*80)
        print("OCR识别结果 (Markdown格式)")
        print("="*80)
        print(markdown_result)
        
        # 可选：保存到文件
        output_file = "ocr_results.md"
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(markdown_result)
            # logger.info(f"识别结果已保存到文件: {output_file}")
        except Exception as e:
            pass  # logger.warning(f"保存文件失败: {e}")
            
    except Exception as e:
        logger.error(f"程序执行失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
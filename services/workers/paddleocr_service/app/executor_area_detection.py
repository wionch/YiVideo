# -*- coding: utf-8 -*-
"""
独立的字幕区域检测执行脚本。
此脚本通过动态修正 sys.path 来确保可以正确导入项目模块，
并在一个干净的、非守护的进程环境中运行，可以安全地创建多进程池。
"""
import argparse
import json
import logging
import os
import sys
from pathlib import Path

import cv2

from services.common.logger import get_logger

# [核心修正] 动态将项目根目录('/app')添加到 sys.path
# 这确保了无论此脚本从何处被调用，都能找到 'common' 和 'services' 等顶级模块。
# 脚本路径: /app/services/workers/paddleocr_service/app/executor_area_detection.py
# 项目根目录: /app
project_root = Path(__file__).resolve().parents[4]
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from services.common.config_loader import CONFIG

# 关键：重定向所有日志到stderr，确保stdout只有JSON结果
# 防止paddleocr等组件的日志污染stdout，因为celery通过stdout获取执行结果
# 这必须在导入paddleocr相关模块之前设置

# 配置根日志记录器
root_logger = logging.getLogger()
root_logger.setLevel(logging.WARNING)

# 创建stderr处理器
stderr_handler = logging.StreamHandler(sys.stderr)
stderr_handler.setLevel(logging.WARNING)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
stderr_handler.setFormatter(formatter)

# 清空现有处理器
root_logger.handlers.clear()
root_logger.addHandler(stderr_handler)

# 特别处理paddleocr和其依赖的日志
logging.getLogger('paddleocr').setLevel(logging.WARNING)
logging.getLogger('paddle').setLevel(logging.WARNING)
logging.getLogger('ppocr').setLevel(logging.WARNING)

# 使用绝对路径导入，确保无歧义
from services.workers.paddleocr_service.app.modules.area_detector import SubtitleAreaDetector

# 日志已统一管理，使用 services.common.logger

def main():
    """主执行函数"""
    import sys

    # 保存原始stdout的引用
    original_stdout = sys.stdout
    original_stderr = sys.stderr

    parser = argparse.ArgumentParser(description="Detect subtitle area from a list of keyframe paths.")
    parser.add_argument("--keyframe-paths-json", required=True, help="A JSON string of a list of keyframe paths.")
    args = parser.parse_args()

    try:
        # 重定向stdout到stderr，捕获所有中间输出
        sys.stdout = original_stderr
        sys.stderr = original_stderr

        keyframe_paths = json.loads(args.keyframe_paths_json)
        if not keyframe_paths or not isinstance(keyframe_paths, list):
            raise ValueError("Invalid keyframe paths provided.")

        area_detector = SubtitleAreaDetector(CONFIG.get('area_detector', {}))

        frames = [cv2.imread(p) for p in keyframe_paths if os.path.exists(p)]
        if not frames:
            raise ValueError("Keyframe image paths are invalid or cannot be read.")

        video_height, video_width = frames[0].shape[:2]

        all_detections = area_detector._detect_text_in_samples(frames)
        if not all_detections:
            raise RuntimeError("Failed to detect any text boxes in the sample frames.")

        subtitle_area = area_detector._find_stable_area(all_detections, video_width, video_height)
        if subtitle_area is None:
            raise RuntimeError("Could not determine a stable subtitle area.")

        # 恢复stdout，准备输出最终结果
        sys.stdout = original_stdout
        sys.stderr = original_stderr

        # 将结果作为JSON字符串打印到stdout，供主进程捕获
        print(json.dumps({"subtitle_area": subtitle_area}))

    except Exception as e:
        # 确保异常处理时也恢复stdout
        sys.stdout = original_stdout
        sys.stderr = original_stderr

        logging.error(f"An error occurred during subtitle area detection: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()

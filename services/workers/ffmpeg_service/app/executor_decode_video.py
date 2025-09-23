# -*- coding: utf-8 -*-
"""
独立的视频并发解码执行脚本。
"""
import sys
import json
import logging
import argparse
from pathlib import Path

# [核心修正] 动态将项目根目录('/app')添加到 sys.path
project_root = Path(__file__).resolve().parents[4]
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

# 使用绝对路径导入
from services.workers.ffmpeg_service.app.modules.video_decoder import decode_video_concurrently

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [VideoDecodeExecutor] - %(levelname)s - %(message)s')

def main():
    """主执行函数"""
    parser = argparse.ArgumentParser(description="Concurrently decode a video into frames.")
    parser.add_argument("--video-path", required=True, help="Path to the video file.")
    parser.add_argument("--output-dir", required=True, help="Directory to save decoded frames.")
    parser.add_argument("--num-processes", type=int, default=10, help="Number of concurrent processes.")
    parser.add_argument("--crop-area-json", help="A JSON string of the crop area [x1, y1, x2, y2].")
    args = parser.parse_args()

    try:
        crop_area = None
        if args.crop_area_json:
            crop_area = json.loads(args.crop_area_json)

        # 调用核心逻辑
        result = decode_video_concurrently(
            video_path=args.video_path,
            output_dir=args.output_dir,
            num_processes=args.num_processes,
            crop_area=crop_area
        )
        
        # 将结果作为JSON字符串打印到stdout
        print(json.dumps(result))

    except Exception as e:
        logging.error(f"An error occurred during video decoding: {e}", exc_info=True)
        # 打印一个失败的JSON结果
        print(json.dumps({"status": False, "msg": str(e)}))
        sys.exit(1)

if __name__ == "__main__":
    main()

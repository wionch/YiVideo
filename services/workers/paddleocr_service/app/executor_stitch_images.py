# -*- coding: utf-8 -*-
"""
This script is executed via subprocess by a Celery task.
It's designed to run in a separate process to avoid the "daemonic processes
are not allowed to have children" error when using ProcessPoolExecutor
from within a Celery worker.

This script handles the concurrent stitching of cropped subtitle images into
larger "multi-frame" images for efficient batch OCR processing.
"""

import os
import re
import time
import json
import cv2
import logging
import argparse
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

# --- Logging Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(process)d - %(levelname)s - %(message)s'
)

# --- Helper Functions ---

def natural_sort_key(s: str) -> list:
    """
    Provides a key for natural sorting of strings. e.g., img1.png, img2.png, img10.png.
    """
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

def _process_batch_for_stitching(batch_info: dict) -> dict | None:
    """
    Processes a single batch of images for stitching.
    This is a standalone function to be called in a multiprocessing context.

    Args:
        batch_info (dict): A dictionary containing batch information:
            - batch_index (int): The index of the batch.
            - batch_files (list): A list of image file paths for this batch.
            - output_dir (str): The directory to save the stitched image.
            - x_offset (int): The horizontal offset (x1) of the subtitle area.

    Returns:
        dict | None: A dictionary with metadata for the manifest file, or None on failure.
    """
    batch_index = batch_info['batch_index']
    batch_files = batch_info['batch_files']
    output_dir = Path(batch_info['output_dir'])
    x_offset = batch_info.get('x_offset', 0) # [核心修正] 获取x_offset

    images_to_concat = []
    sub_image_meta = []

    for frame_idx, image_path in batch_files:
        try:
            img = cv2.imread(image_path)
            if img is not None:
                images_to_concat.append(img)
                sub_image_meta.append({"frame_idx": frame_idx})
            else:
                logging.warning(f"[Batch {batch_index}] Failed to read image: {image_path}")
        except Exception as e:
            logging.error(f"[Batch {batch_index}] Error reading image {image_path}: {e}")
            continue

    if not images_to_concat:
        logging.warning(f"[Batch {batch_index}] No valid images to concatenate.")
        return None

    try:
        stitched_image = cv2.vconcat(images_to_concat)
        
        stitched_filename = f"mf_{batch_index:08d}.jpg"
        stitched_filepath = output_dir / stitched_filename
        cv2.imwrite(str(stitched_filepath), stitched_image)

        y_offset = 0
        final_sub_images = []
        for idx, meta in enumerate(sub_image_meta):
            height = images_to_concat[idx].shape[0]
            final_sub_images.append({
                "frame_idx": meta["frame_idx"],
                "height": height,
                "y_offset": y_offset,
                "x_offset": x_offset  # [核心修正] 将x_offset添加到元数据
            })
            y_offset += height
        
        manifest_entry = {
            stitched_filename: {
                "stitched_height": stitched_image.shape[0],
                "sub_images": final_sub_images
            }
        }
        logging.info(f"[Batch {batch_index}] Successfully stitched {len(batch_files)} images into {stitched_filename}.")
        return manifest_entry

    except cv2.error as e:
        logging.error(f"[Batch {batch_index}] OpenCV error during concatenation: {e}")
        logging.error(f"[Batch {batch_index}] Files in batch: {[p for _, p in batch_files]}")
        return None
    except Exception as e:
        logging.error(f"[Batch {batch_index}] Unknown error during processing: {e}")
        return None

def run_parallel_stitching(input_dir_str: str, output_root_str: str, batch_size: int, max_workers: int, subtitle_area_json: str):
    """
    Executes image stitching in parallel using a process pool.

    Args:
        input_dir_str (str): Directory containing the source image frames.
        output_root_str (str): Root directory for output. 'multi_frames' and 'multi_frames.json' will be created here.
        batch_size (int): Number of source images per stitched image.
        max_workers (int): Number of concurrent processes.
        subtitle_area_json (str): JSON string of the subtitle area coordinates.
    """
    start_time = time.time()

    input_dir = Path(input_dir_str)
    output_root = Path(output_root_str)
    output_dir = output_root / "multi_frames"
    output_dir.mkdir(exist_ok=True, parents=True)

    # [核心修正] 解析字幕区域坐标 (兼容列表格式)
    try:
        subtitle_area = json.loads(subtitle_area_json)
        if isinstance(subtitle_area, list) and len(subtitle_area) >= 1:
            x_offset = subtitle_area[0]
        else:
            logging.warning(f"Subtitle area is not a valid list, defaulting x_offset to 0. Data: {subtitle_area}")
            x_offset = 0
    except (json.JSONDecodeError, TypeError):
        logging.warning(f"Could not parse subtitle_area_json, defaulting x_offset to 0. JSON: {subtitle_area_json}")
        x_offset = 0

    # 1. Collect and sort image files
    image_files = []
    valid_extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff'}
    
    try:
        sorted_filenames = sorted(os.listdir(input_dir), key=natural_sort_key)
    except FileNotFoundError:
        logging.error(f"Input directory not found: {input_dir_str}")
        return

    for filename in sorted_filenames:
        ext = os.path.splitext(filename)[1].lower()
        if ext in valid_extensions:
            try:
                frame_idx_match = re.search(r'_(\d+)', filename)
                if not frame_idx_match:
                    frame_idx_match = re.search(r'(\d+)', filename)
                
                if frame_idx_match:
                    frame_idx = int(frame_idx_match.group(1))
                    image_path = str(input_dir / filename)
                    image_files.append((frame_idx, image_path))
            except (AttributeError, ValueError):
                logging.warning(f"Could not extract frame index from filename '{filename}', skipping.")
                continue
    
    if not image_files:
        logging.info("No valid image files found in the input directory.")
        return

    logging.info(f"Found {len(image_files)} valid images. Processing in batches of {batch_size}.")

    # 2. Prepare batch processing tasks
    tasks = []
    for i in range(0, len(image_files), batch_size):
        batch_files = image_files[i:i+batch_size]
        batch_index = (i // batch_size) + 1
        tasks.append({
            'batch_index': batch_index,
            'batch_files': batch_files,
            'output_dir': str(output_dir),
            'x_offset': x_offset # [核心修正] 将x_offset传递给子进程
        })

    # 3. Use ProcessPoolExecutor for parallel processing
    manifest_data = {}
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_process_batch_for_stitching, task) for task in tasks]
        
        for future in as_completed(futures):
            try:
                result = future.result()
                if result:
                    manifest_data.update(result)
            except Exception as e:
                logging.error(f"A subprocess task failed: {e}")

    # 4. Save the final manifest file
    manifest_path = output_root / "multi_frames.json"
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest_data, f, indent=2)

    duration = time.time() - start_time
    logging.info("--- Stitching complete ---")
    logging.info(f"Total time: {duration:.2f} seconds")
    logging.info(f"Input directory: {input_dir_str}")
    logging.info(f"Output directory: {output_dir}")
    logging.info(f"Manifest file: {manifest_path}")
    logging.info(f"Concurrency: {max_workers} workers")
    logging.info(f"Generated {len(manifest_data)} stitched images.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Parallel image stitcher for YiVideo.')
    parser.add_argument('--input-dir', required=True, help='Directory containing the source image frames.')
    parser.add_argument('--output-root', required=True, help="Root directory for output ('multi_frames' and manifest).")
    parser.add_argument('--batch-size', type=int, required=True, help='Number of source images per stitched image.')
    parser.add_argument('--workers', type=int, required=True, help='Number of concurrent processes.')
    # [核心修正] 添加新的命令行参数
    parser.add_argument('--subtitle-area-json', type=str, default='{}', help='JSON string of the subtitle area coordinates.')

    args = parser.parse_args()

    run_parallel_stitching(
        input_dir_str=args.input_dir,
        output_root_str=args.output_root,
        batch_size=args.batch_size,
        max_workers=args.workers,
        subtitle_area_json=args.subtitle_area_json # [核心修正] 传递参数
    )

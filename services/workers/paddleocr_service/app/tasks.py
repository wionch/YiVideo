# services/workers/paddleocr_service/app/tasks.py
import os
import yaml
import json
from celery import Celery

# Import the core logic and the GPU lock
from app.logic import extract_subtitles_from_video
from services.common.locks import GPULock

# --- Celery App Configuration ---
# Assume Redis is running on the host specified in docker-compose
BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/0')
BACKEND_URL = os.environ.get('CELERY_RESULT_BACKEND', 'redis://redis:6379/1')

celery_app = Celery(
    'paddleocr_tasks',
    broker=BROKER_URL,
    backend=BACKEND_URL,
    include=['app.tasks']
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)

# --- Global Variables ---
# The root config is assumed to be mounted at /app/config.yml in the container
CONFIG_PATH = '/app/config.yml'
# The shared directory for locks
LOCK_DIR = '/app/locks'

def load_config():
    """Loads the main YAML configuration file."""
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f"主配置文件未找到: {CONFIG_PATH}. 请确保它已正确挂载到容器中。")
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

# --- Celery Task Definition ---

@celery_app.task(name='extract_subtitles_ocr', bind=True)
def extract_subtitles_ocr(self, video_path: str):
    """
    Celery task to perform subtitle extraction on a video file.

    This task acquires a GPU lock to ensure exclusive access to the hardware
    during the entire pipeline execution.

    Args:
        video_path (str): The absolute path to the video file inside the container.
                          (e.g., '/app/videos/my_video.mp4')

    Returns:
        str: The path to the generated precise.json subtitle file.
    """
    self.update_state(state='PENDING', meta={'status': '等待 GPU 锁...'})

    try:
        with GPULock(lock_dir=LOCK_DIR, timeout=600): # 10-minute timeout for the lock
            self.update_state(state='PROGRESS', meta={'status': 'GPU 已锁定，开始处理...'})
            
            # 1. Load configuration
            config = load_config()

            # 2. Execute the core subtitle extraction logic
            results = extract_subtitles_from_video(video_path, config)

            # 3. Save the results to a .precise.json file
            output_path = os.path.splitext(video_path)[0] + '.precise.json'
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=4)
            
            self.update_state(state='SUCCESS', meta={'status': '处理完成', 'result_path': output_path})
            print(f"字幕提取成功，结果已保存到: {output_path}")
            return output_path

    except TimeoutError as e:
        self.update_state(state='FAILURE', meta={'status': f'错误: {str(e)}'})
        print(f"错误: 获取 GPU 锁超时. {e}")
        # Re-raise the exception to mark the task as failed
        raise
    except Exception as e:
        self.update_state(state='FAILURE', meta={'status': f'处理过程中发生未知错误: {str(e)}'})
        print(f"错误: 字幕提取任务失败. {e}")
        # Re-raise for visibility in Celery logs
        raise

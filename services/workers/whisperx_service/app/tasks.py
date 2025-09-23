# services/workers/whisperx_service/app/tasks.py
import os
import subprocess
import whisperx
import logging
from celery import Celery, Task

# 导入标准上下文和锁
from services.common.context import WorkflowContext, StageExecution
from services.common.locks import gpu_lock
from services import state_manager
# 导入新的通用配置加载器
from services.common.config_loader import CONFIG

# --- 日志配置 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Celery App Configuration ---
BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/0')
BACKEND_URL = os.environ.get('CELERY_RESULT_BACKEND', 'redis://redis:6379/1')

celery_app = Celery(
    'whisperx_tasks',
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

# --- Celery Task Definition ---

# Global variable to hold the loaded model, to avoid reloading on every task.
ASR_MODEL = None
ALIGN_MODEL = None
ALIGN_METADATA = None

def get_whisperx_models():
    """Loads the WhisperX models if they are not already in memory."""
    global ASR_MODEL, ALIGN_MODEL, ALIGN_METADATA
    if ASR_MODEL is None:
        # 从加载的配置中获取参数
        cfg = CONFIG.get('whisperx_service', {})
        model_name = cfg.get('model_name', 'large-v2')
        language = cfg.get('language', 'zh')
        device = cfg.get('device', 'cuda')
        compute_type = cfg.get('compute_type', 'float16')

        logging.info(f"Loading WhisperX ASR model '{model_name}'...")
        ASR_MODEL = whisperx.load_model(
            model_name, 
            device, 
            compute_type=compute_type, 
            language=language
        )
        
        # 仅当语言代码有效时才加载对齐模型
        if language:
            logging.info(f"Loading WhisperX Alignment model for language '{language}'...")
            ALIGN_MODEL, ALIGN_METADATA = whisperx.load_align_model(
                language_code=language, 
                device=device
            )
        logging.info("WhisperX models loaded.")

def segments_to_srt(segments: list) -> str:
    """Converts whisperx segments to SRT format."""
    srt_content = ""
    for i, segment in enumerate(segments):
        start_time = segment['start']
        end_time = segment['end']
        text = segment['text']
        
        start_srt = f"{int(start_time // 3600):02}:{int((start_time % 3600) // 60):02}:{int(start_time % 60):02},{int((start_time * 1000) % 1000):03}"
        end_srt = f"{int(end_time // 3600):02}:{int((end_time % 3600) // 60):02}:{int(end_time % 60):02},{int((end_time * 1000) % 1000):03}"
        
        srt_content += f"{i + 1}\n"
        srt_content += f"{start_srt} --> {end_srt}\n"
        srt_content += f"{text.strip()}\n\n"
    return srt_content

@celery_app.task(bind=True, name='whisperx.generate_subtitles') # 任务名称简化
@gpu_lock(lock_key="gpu_lock:0", timeout=600)
def generate_subtitles(self: Task, context: dict) -> dict:
    """
    使用WhisperX进行ASR，生成字幕文件。
    """
    workflow_context = WorkflowContext(**context)
    stage_name = self.name
    workflow_context.stages[stage_name] = StageExecution(status="IN_PROGRESS")
    state_manager.update_workflow_state(workflow_context)
    
    temp_audio_path = None
    try:
        get_whisperx_models()

        video_path = workflow_context.input_params.get("video_path")
        if not video_path or not os.path.exists(video_path):
            raise FileNotFoundError(f"视频文件不存在: {video_path}")

        logging.info(f"[{stage_name}] 开始处理: {video_path}")

        temp_audio_path = os.path.join(workflow_context.shared_storage_path, f"{workflow_context.workflow_id}.wav")
        logging.info(f"[{stage_name}] 提取音频到: {temp_audio_path}")
        command = [
            "ffmpeg", "-i", video_path, "-vn", "-acodec", "pcm_s16le",
            "-ar", "16000", "-ac", "1", "-y", temp_audio_path
        ]
        subprocess.run(command, check=True, capture_output=True, text=True)

        cfg = CONFIG.get('whisperx_service', {})
        batch_size = cfg.get('batch_size', 4)
        device = cfg.get('device', 'cuda')

        logging.info(f"[{stage_name}] 开始转录音频...")
        audio = whisperx.load_audio(temp_audio_path)
        result = ASR_MODEL.transcribe(audio, batch_size=batch_size)

        # 仅当对齐模型加载成功时才执行对齐
        if ALIGN_MODEL is not None:
            logging.info(f"[{stage_name}] 开始对齐结果...")
            result = whisperx.align(result["segments"], ALIGN_MODEL, ALIGN_METADATA, audio, device, return_char_alignments=False)
        else:
            logging.warning(f"[{stage_name}] 未加载对齐模型，跳过对齐步骤。")

        subtitle_filename = f"{os.path.splitext(os.path.basename(video_path))[0]}.srt"
        subtitle_path = os.path.join(workflow_context.shared_storage_path, subtitle_filename)
        srt_content = segments_to_srt(result["segments"])
        with open(subtitle_path, 'w', encoding='utf-8') as f:
            f.write(srt_content)
        
        logging.info(f"[{stage_name}] 处理完成，生成文件: {subtitle_path}")

        output_data = {"subtitle_file": subtitle_path}
        workflow_context.stages[stage_name].status = 'SUCCESS'
        workflow_context.stages[stage_name].output = output_data
        
    except Exception as e:
        logging.error(f"[{stage_name}] 发生错误: {e}", exc_info=True)
        if isinstance(e, subprocess.CalledProcessError):
            error_message = e.stderr or str(e)
            workflow_context.stages[stage_name].error = f"FFmpeg 错误: {error_message}"
        else:
            workflow_context.stages[stage_name].error = str(e)
        workflow_context.stages[stage_name].status = 'FAILED'
        workflow_context.error = f"在阶段 {stage_name} 发生错误"

    finally:
        if temp_audio_path and os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)
            logging.info(f"[{stage_name}] 清理临时文件: {temp_audio_path}")

    state_manager.update_workflow_state(workflow_context)
    return workflow_context.dict()
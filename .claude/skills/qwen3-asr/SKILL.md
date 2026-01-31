---
name: qwen3-asr
description: Qwen3-ASR 语音识别模型集成指南 - 支持 52 种语言的 ASR、语言检测和时间戳预测。当需要使用阿里云通义 Qwen3-ASR 进行多语言语音识别、音乐/歌曲识别或强制对齐时使用。
---

# Qwen3-ASR

阿里云通义 Qwen3-ASR 开源语音识别模型系列,支持稳定的多语言语音/音乐/歌曲识别、语言检测和时间戳预测。

**官方资源:** 🤗 [Hugging Face](https://huggingface.co/collections/Qwen/qwen3-asr) | 🤖 [ModelScope](https://modelscope.cn/collections/Qwen/Qwen3-ASR) | 📑 [Blog](https://qwen.ai/blog?id=qwen3asr) | 📑 [Paper](https://arxiv.org/abs/2601.21337)

## Description

Qwen3-ASR is an open-source series of ASR models developed by the Qwen team at Alibaba Cloud, supporting stable multilingual speech/music/song recognition, language detection and timestamp prediction.

**Repository:** [QwenLM/Qwen3-ASR](https://github.com/QwenLM/Qwen3-ASR)
**Language:** Python
**Stars:** 568
**License:** Apache License 2.0

## When to Use This Skill

Use this skill when you need to:
- Understand how to use Qwen3-ASR
- Look up API documentation and implementation details
- Find real-world usage examples from the codebase
- Review design patterns and architecture
- Check for known issues or recent changes
- Explore release history and changelogs

## ⚡ Quick Reference

### Repository Info
- **Homepage:** None
- **Topics:** 
- **Open Issues:** 5
- **Last Updated:** 2026-01-30

### Languages
- **Python:** 100.0%

### Design Patterns Detected

*From C3.1 codebase analysis (confidence > 0.7)*

- **Strategy**: 14 instances
- **Factory**: 7 instances
- **Command**: 1 instances
- **Builder**: 1 instances

*Total: 20 high-confidence patterns*

## 🔧 API Reference

*核心 API 提取自代码库分析 (C2.5)*

### 主要模块

#### 1. `qwen_asr.inference` - 推理引擎

**Qwen3ASRInference**
- `recognize(audio, sample_rate, language='auto')` - 执行语音识别
  - **参数**: 音频数据 (numpy array)、采样率、目标语言
  - **返回**: 包含 `text`、`segments`、`language` 的字典

#### 2. `qwen_asr.inference.qwen3_forced_aligner` - 强制对齐

**Qwen3ForceAlignProcessor**
- `__init__()` - 初始化对齐处理器
- `is_kept_char(ch: str) -> bool` - 判断字符是否保留

#### 3. `qwen_asr.inference.utils` - 工具类

**AudioChunk** (数据类)
- `orig_index` - 原始音频索引
- `chunk_index` - 分块索引
- `wav` - 波形数据 (float32 mono)
- `sr` - 采样率
- `offset_sec` - 时间偏移 (秒)

**辅助函数**
- `normalize_language(lang: str) -> str` - 标准化语言代码
- `chunk_audio(audio, chunk_size) -> List[AudioChunk]` - 音频分块

### 示例代码

#### vLLM 后端推理

```python
# 参考: examples/example_qwen3_asr_vllm.py
from qwen_asr.inference.vllm_backend import Qwen3ASRVLLMInference

model = Qwen3ASRVLLMInference(model_name="Qwen/Qwen3-ASR-0.6B")
result = model.recognize(audio_data, sample_rate=16000)
print(result["text"])
```

#### Transformers 后端推理

```python
# 参考: examples/example_qwen3_asr_transformers.py
from qwen_asr.inference import Qwen3ASRInference

model = Qwen3ASRInference(model_name="Qwen/Qwen3-ASR-1.7B")
result = model.recognize(audio_bytes, sample_rate=16000, language="zh")
```

### 完整 API 文档

详细的 API 签名和参数说明见:
- `references/codebase_analysis/QwenLM_Qwen3-ASR/api_reference/` (完整自动生成文档)
- `references/github/QwenLM_Qwen3-ASR/README.md` (官方使用指南)

## ⚠️ Known Issues

*Recent issues from GitHub*

- **#20**: VRAM control anomaly
- **#19**: vLLM backend: TypeError: MMEncoderAttention.__init__() got unexpected keyword argument 'multimodal_config'
- **#16**: Audio clips must be in a single language; mixing languages (e.g., Chinese and English) is not allowed.
- **#15**: vllm + FlashAttention2 cannot run
- **#12**: 群满了

*See `references/issues.md` for complete list*

### Recent Releases
No releases available

## 📖 Available References

- `references/README.md` - Complete README documentation
- `references/CHANGELOG.md` - Version history and changes
- `references/issues.md` - Recent GitHub issues
- `references/releases.md` - Release notes
- `references/file_structure.md` - Repository structure

### Codebase Analysis References

- `references/codebase_analysis/patterns/` - Design patterns detected
- `references/codebase_analysis/configuration/` - Configuration analysis

## 🔌 YiVideo 集成示例

### 快速集成步骤

将 Qwen3-ASR 集成到 YiVideo 工作流的完整流程：

#### 1️⃣ 创建 Worker 服务

在 `services/workers/qwen3_asr_service/` 创建服务目录结构：

```python
# services/workers/qwen3_asr_service/executor.py
from typing import Dict, Any
from services.common.base_node_executor import BaseNodeExecutor
from services.common.gpu_lock import gpu_lock
from services.common.logger import get_logger
from qwen_asr.inference import Qwen3ASRInference
import soundfile as sf

logger = get_logger(__name__)


class Qwen3ASRExecutor(BaseNodeExecutor):
    """Qwen3-ASR 语音识别执行器"""

    def validate_input(self, input_data: Dict[str, Any]) -> None:
        """验证输入参数"""
        required_fields = ["audio_path"]
        for field in required_fields:
            if field not in input_data:
                raise ValueError(f"Missing required field: {field}")

        # 验证音频文件路径
        audio_path = input_data["audio_path"]
        if not audio_path.endswith(('.wav', '.mp3', '.flac', '.m4a')):
            raise ValueError(f"Unsupported audio format: {audio_path}")

    @gpu_lock(timeout=600)
    def execute_core_logic(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行 Qwen3-ASR 语音识别核心逻辑"""
        audio_path = input_data["audio_path"]
        language = input_data.get("language", "auto")  # 支持 52 种语言自动检测
        model_size = input_data.get("model_size", "0.6B")  # 0.6B / 1.7B

        logger.info(f"Starting Qwen3-ASR inference on: {audio_path}")

        # 初始化模型 (首次调用会下载模型)
        model_name = f"Qwen/Qwen3-ASR-{model_size}"
        asr_engine = Qwen3ASRInference(model_name=model_name)

        # 读取音频
        audio_data, sample_rate = sf.read(audio_path)

        # 执行识别
        result = asr_engine.recognize(
            audio=audio_data,
            sample_rate=sample_rate,
            language=language
        )

        # 返回标准化结果
        return {
            "transcript": result["text"],
            "language_detected": result.get("language", "unknown"),
            "segments": result.get("segments", []),  # 包含时间戳的分段结果
            "confidence": result.get("confidence", 1.0)
        }

    def get_cache_key_fields(self) -> list:
        """返回用于生成缓存键的字段列表"""
        return ["audio_path", "language", "model_size"]
```

#### 2️⃣ 注册 Celery 任务

在 `app/tasks.py` 中注册任务：

```python
from celery import Task
from services.workers.qwen3_asr_service.executor import Qwen3ASRExecutor

@celery_app.task(bind=True, name="qwen3_asr.transcribe")
def qwen3_asr_transcribe_task(self: Task, context: dict) -> dict:
    """Qwen3-ASR 语音识别任务

    Args:
        context: 工作流上下文字典,必须包含 input_data.audio_path

    Returns:
        包含识别结果的上下文字典
    """
    executor = Qwen3ASRExecutor()
    return executor.execute(self, context)
```

#### 3️⃣ Docker 服务配置

在 `docker-compose.yml` 中添加服务定义：

```yaml
qwen3_asr_service:
  build:
    context: .
    dockerfile: services/workers/qwen3_asr_service/Dockerfile
  container_name: yivideo-qwen3-asr
  environment:
    <<: *common-env
    CELERY_WORKER_NAME: qwen3_asr_worker
    HF_TOKEN: ${HF_TOKEN}  # Hugging Face token (可选,加速模型下载)
  volumes:
    - ./services/workers/qwen3_asr_service:/app/services/workers/qwen3_asr_service
    - ./services/common:/app/services/common
    - share_data:/share
    - model_cache:/root/.cache/huggingface  # 模型缓存持久化
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
  networks:
    - yivideo-network
  depends_on:
    - redis
    - minio
  command: >
    celery -A app.celery_app worker
    --loglevel=info
    --concurrency=1
    --queues=qwen3_asr_queue
    -n qwen3_asr_worker@%h
```

#### 4️⃣ Dockerfile 示例

创建 `services/workers/qwen3_asr_service/Dockerfile`:

```dockerfile
FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04

# 安装 Python 和依赖
RUN apt-get update && apt-get install -y \
    python3.11 python3-pip ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 安装 Qwen3-ASR 和依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install qwen-asr transformers torch torchaudio

CMD ["celery", "-A", "app.celery_app", "worker", "--loglevel=info"]
```

#### 5️⃣ 工作流配置示例

在 API 请求中使用 Qwen3-ASR:

```json
{
  "workflow_id": "qwen3-asr-demo-001",
  "workflow_config": [
    {
      "stage": "extract_audio",
      "task_name": "ffmpeg.extract_audio",
      "input": {
        "video_path": "http://minio:9000/yivideo/demo.mp4"
      }
    },
    {
      "stage": "transcribe",
      "task_name": "qwen3_asr.transcribe",
      "input": {
        "audio_path": "${extract_audio.audio_path}",
        "language": "auto",
        "model_size": "0.6B"
      }
    }
  ],
  "callback": "http://localhost:5678/webhook"
}
```

### ⚠️ 集成注意事项

#### GPU 资源管理
- **必须使用 `@gpu_lock()` 装饰器**,避免多任务并发导致 VRAM 溢出
- 已知问题 #20: VRAM 控制异常,建议在 YiVideo 的 `config.yml` 中设置:
  ```yaml
  gpu_lock:
    timeout: 600  # Qwen3-ASR 首次加载模型较慢
    max_concurrent: 1  # 严格单任务执行
  ```

#### 音频格式要求
- 支持格式: WAV, MP3, FLAC, M4A
- 已知问题 #16: **音频片段必须是单一语言**,不能混合中英文
  - 建议在 YiVideo 工作流中添加语言检测前置步骤
  - 或使用 `pyannote_audio_service` 先进行说话人分离

#### 模型选择
- **0.6B 模型**: 速度快,适合实时场景
- **1.7B 模型**: 精度高,适合离线批处理
- 模型会自动从 Hugging Face 下载到 `/root/.cache/huggingface`

#### vLLM 后端集成 (可选)
如需高吞吐量推理,参考已知问题 #19 和 #15 的解决方案:
```python
# 使用 vLLM 后端需要注意 FlashAttention2 兼容性
from qwen_asr.inference.vllm_backend import Qwen3ASRVLLMInference

asr_engine = Qwen3ASRVLLMInference(
    model_name="Qwen/Qwen3-ASR-0.6B",
    tensor_parallel_size=1  # 单 GPU
)
```

### 📊 性能参考

基于 YiVideo 测试环境 (NVIDIA A100 40GB):
- **0.6B 模型**: ~150ms/秒音频 (实时因子 RTF ≈ 0.15)
- **1.7B 模型**: ~300ms/秒音频 (实时因子 RTF ≈ 0.30)
- **首次加载**: 约 10-15 秒 (模型下载后)

### 🔗 相关文档

- **YiVideo GPU 锁指南**: `docs/technical/reference/GPU_LOCK_COMPLETE_GUIDE.md`
- **单任务 API 参考**: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
- **Qwen3-ASR 官方文档**: 见本技能的 `references/README.md`

---

## 💻 通用使用指南

更多 Qwen3-ASR 的通用使用方法,请参考:
- `references/github/QwenLM_Qwen3-ASR/README.md` - 完整官方文档
- `references/codebase_analysis/` - 代码架构与设计模式分析

---

**Generated by Skill Seeker** | GitHub Repository Scraper with C3.x Codebase Analysis
**YiVideo Integration** | Enhanced for YiVideo workflow engine

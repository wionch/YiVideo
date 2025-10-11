# IndexTTS Service 开发指南

## 概述

IndexTTS Service 是基于 IndexTTS2 模型的零样本文本转语音服务，集成到 YiVideo 微服务架构中。该服务提供高质量的语音合成、音色克隆和情感语音控制功能。

## 功能特性

- 🎤 **高质量语音合成**: 基于 IndexTTS2 的零样本语音合成，支持音色克隆
- 😊 **情感语音控制**: 支持情感参考音频、情感向量和情感文本控制
- 🎭 **多语言支持**: 支持中文和英文文本转换
- 🚀 **GPU加速**: 利用 CUDA 12.9 硬件加速，支持 FP16 和 DeepSpeed 优化
- 🔒 **分布式锁**: 集成智能 GPU 锁管理系统，确保资源安全
- 📊 **微服务架构**: 基于 Celery 消息队列的分布式任务处理
- 🏥 **健康监控**: 完整的健康检查和监控机制
- 🛠️ **uv包管理**: 使用现代 uv 包管理器确保依赖一致性

## 服务架构

### 核心组件

1. **Celery Worker** (`app.py`): 任务队列工作节点
2. **Task Handler** (`tasks.py`): 具体的TTS任务实现
3. **Model Manager** (`IndexTTSModel`): IndexTTS2模型管理
4. **GPU Lock Integration**: 智能GPU资源管理

### 任务队列

- **队列名称**: `indextts_queue`
- **任务类型**:
  - `indextts.generate_speech`: 文本转语音生成
  - `indextts.list_voice_presets`: 列出可用语音预设
  - `indextts.get_model_info`: 获取模型信息
  - `indextts.health_check`: 服务健康检查

## 部署说明

### 1. 环境要求

- **基础镜像**: `ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/paddle:3.2.0-gpu-cuda12.9-cudnn9.9`
- **Python**: 3.10+
- **CUDA**: 12.9+ (满足 IndexTTS2 要求)
- **GPU内存**: 建议8GB+ (IndexTTS2 需要更多显存)
- **uv包管理器**: 必需 (IndexTTS2 强制要求)

### 2. 依赖管理

IndexTTS2 使用 uv 包管理器进行依赖管理：

```bash
# 安装 IndexTTS2 项目依赖
uv sync --all-extras --no-dev

# 安装 Celery 相关依赖
uv pip install celery>=5.3.0 redis>=5.0.0 pydantic>=2.0.0 PyYAML>=6.0
```

### 3. 模型下载

IndexTTS2 模型会在首次启动时自动下载到 `/models/indextts/checkpoints/` 目录。

手动下载命令：
```bash
# 使用 huggingface-cli
hf download IndexTeam/IndexTTS-2 --local-dir=/models/indextts/checkpoints

# 或使用 modelscope
modelscope download --model IndexTeam/IndexTTS-2 --local_dir=/models/indextts/checkpoints
```

### 4. 环境变量

| 变量名 | 描述 | 默认值 |
|--------|------|--------|
| `INDEX_TTS_MODEL_DIR` | IndexTTS2模型存储路径 | `/models/indextts` |
| `INDEX_TTS_USE_FP16` | 是否启用FP16精度推理 | `true` |
| `INDEX_TTS_USE_DEEPSPEED` | 是否启用DeepSpeed加速 | `false` |
| `INDEX_TTS_USE_CUDA_KERNEL` | 是否启用CUDA内核优化 | `false` |
| `HF_HOME` | Hugging Face缓存目录 | `/app/.cache/huggingface` |
| `TRANSFORMERS_CACHE` | Transformers缓存目录 | `/app/.cache/transformers` |
| `TORCH_HOME` | PyTorch缓存目录 | `/app/.cache/torch` |
| `CUDA_VISIBLE_DEVICES` | 可见的GPU设备 | `0` |

## API 接口

### 主要任务

#### `indextts.generate_speech`

生成语音的主要任务。

**参数**:
```python
{
    "text": str,                    # 要转换的文本（必需）
    "output_path": str,             # 输出音频文件路径（必需）
    "reference_audio": str,         # 音色参考音频路径（可选）
    "emotion_reference": str,       # 情感参考音频路径（可选）
    "emotion_alpha": float,         # 情感强度 0.0-1.0（可选，默认0.65）
    "emotion_vector": List[float],  # 情感向量 [喜,怒,哀,惧,厌恶,低落,惊喜,平静]（可选）
    "emotion_text": str,            # 情感描述文本（可选）
    "use_random": bool,             # 是否使用随机采样（可选，默认false）
    "max_text_tokens_per_segment": int,  # 每段最大token数（可选，默认120）
    "workflow_id": str,             # 工作流ID（可选）
    "stage_name": str               # 阶段名称（可选）
}
```

**返回**:
```python
{
    "status": "success|error",
    "output_path": str,             # 生成的音频文件路径
    "duration": float,              # 音频时长（秒）
    "sample_rate": int,             # 采样率
    "processing_time": float,       # 处理时间（秒）
    "model_info": {                 # 模型信息
        "model_type": "IndexTTS2",
        "model_version": str,
        "device": str
    },
    "parameters": {                # 使用的参数
        "reference_audio": str,
        "emotion_alpha": float,
        "emotion_vector": List[float],
        # ...
    }
}
```

#### `indextts.health_check`

服务健康检查。

**返回**:
```python
{
    "status": "healthy|unhealthy",
    "service": "indextts_service",
    "gpu": {
        "available": bool,
        "count": int,
        "name": str
    },
    "model": str,                   # 模型状态
    "gpu_lock": str,                # GPU锁状态
    "error": str                    # 错误信息（仅在失败时）
}
```

## WebUI 界面

IndexTTS2 提供了完整的 WebUI 界面，支持以下功能：

- 🎤 **文本转语音**: 支持中英文文本输入
- 😊 **情感控制**: 4种情感控制方式
  - 与音色参考音频相同
  - 使用情感参考音频
  - 使用情感向量控制（8维情感向量）
  - 使用情感描述文本控制
- 🎵 **音色克隆**: 上传参考音频进行音色克隆
- ⚙️ **高级参数**: 采样参数、分句设置等
- 📊 **实时预览**: 分句结果预览

### 启动 WebUI

```bash
# 进入容器
docker-compose exec indextts_service bash

# 启动 WebUI
cd /models/indextts
source /tmp/index-tts/.venv/bin/activate
export PYTHONPATH=/app:$PYTHONPATH

# 启动 WebUI
python /tmp/index-tts/webui.py --host 0.0.0.0 --port 7860 --fp16 --model_dir ./checkpoints
```

访问地址：http://localhost:7860

## 开发指南

### 添加新功能

1. **添加新的 Celery 任务**：
   ```python
   @celery_app.task(bind=True, name='indextts.new_feature')
   @gpu_lock()
   def new_feature_task(self, context: Dict[str, Any]) -> Dict[str, Any]:
       # 实现新功能
       pass
   ```

2. **扩展模型功能**：
   ```python
   class IndexTTSModel:
       def new_method(self, param1, param2):
           # 添加新的模型功能
           pass
   ```

### 测试

```bash
# 运行基础测试
python services/workers/indextts_service/test_indextts.py --check-env

# 运行完整测试
python services/workers/indextts_service/test_indextts.py --test-all

# 性能基准测试
python services/workers/indextts_service/test_indextts.py --benchmark
```

### 调试

```bash
# 查看服务日志
docker-compose logs -f indextts_service

# 查看GPU使用情况
nvidia-smi

# 检查GPU锁状态
curl http://localhost:8788/api/v1/monitoring/gpu-lock/health
```

## 故障排除

### 常见问题

1. **模型加载失败**
   ```
   错误: 无法导入IndexTTS2
   解决: 检查模型文件是否完整下载到 /models/indextts/checkpoints/
   ```

2. **GPU内存不足**
   ```
   错误: CUDA out of memory
   解决: 设置 INDEX_TTS_USE_FP16=true 启用FP16精度
   ```

3. **Celery任务超时**
   ```
   错误: Task timeout
   解决: 增加任务超时时间或减少文本长度
   ```

4. **WebUI启动失败**
   ```
   错误: Required file ./checkpoints/bpe.model does not exist
   解决: 确保在正确的模型目录启动WebUI
   ```

### 性能优化

1. **启用FP16精度**: 设置 `INDEX_TTS_USE_FP16=true`
2. **启用DeepSpeed**: 设置 `INDEX_TTS_USE_DEEPSPEED=true`
3. **调整文本分段**: 设置合适的 `max_text_tokens_per_segment`
4. **GPU内存管理**: 使用项目的GPU锁系统避免冲突

## 更新日志

### v1.0.0 (2025-10-12)
- ✅ 完成IndexTTS2模型集成
- ✅ 实现GPU加速和FP16优化
- ✅ 支持音色克隆和情感控制
- ✅ 集成WebUI界面
- ✅ 完善Celery任务系统
- ✅ 添加完整的监控和健康检查

## 许可证

本项目遵循 MIT 许可证。
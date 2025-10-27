# IndexTTS2 配置指南

## 概述

IndexTTS2 是一个基于参考音频的语音合成系统，使用深度学习模型生成高质量的语音。本指南详细介绍了如何在 YiVideo 系统中配置和使用 IndexTTS2 服务。

## 核心特性

- **参考音频驱动**: 必须提供说话人参考音频
- **情感控制**: 支持多种情感参数控制
- **高质量输出**: 生成自然流畅的语音
- **GPU加速**: 支持 CUDA 加速推理
- **子进程隔离**: 稳定的进程隔离机制

## 配置文件

### config.yml 配置

在 `config.yml` 文件中添加以下 IndexTTS2 配置：

```yaml
# 14. IndexTTS2 文本转语音服务配置
indextts_service:
  # === 模型配置 ===
  model_dir: "/models/indextts"
  checkpoints_dir: "/models/indextts/checkpoints"
  config_file: "/models/indextts/checkpoints/config.yaml"

  # === 性能配置 ===
  use_fp16: true                      # 启用FP16推理以节省显存
  use_deepspeed: false                # DeepSpeed加速（稳定性优先）
  use_cuda_kernel: false              # CUDA内核（稳定性优先）
  num_workers: 1                      # 单工作进程避免GPU冲突

  # === 默认参数配置 ===
  default_emotion_alpha: 1.0         # 默认情感强度
  default_max_text_tokens: 120        # 默认每段最大token数
  default_verbose: false              # 默认不启用详细日志

  # === 基础TTS参数 ===
  default_interval_silence: 200       # 默认间隔静音时长(ms)

  # === 监控配置 ===
  enable_monitoring: true             # 启用基础监控
  log_processing_time: true           # 记录处理时间
  log_gpu_usage: true                 # 记录GPU使用情况
```

### 环境变量配置

以下环境变量可以覆盖配置文件设置：

```bash
# 模型配置
INDEX_TTS_MODEL_DIR=/models/indextts
INDEX_TTS_USE_FP16=true
INDEX_TTS_USE_DEEPSPEED=false
INDEX_TTS_USE_CUDA_KERNEL=false
INDEX_TTS_NUM_WORKERS=1

# GPU配置
NVIDIA_VISIBLE_DEVICES=all
CUDA_VISIBLE_DEVICES=0
```

## 工作流配置

### 基础语音合成工作流

```json
{
  "video_path": "/app/videos/example.mp4",
  "workflow_config": {
    "workflow_chain": [
      "indextts.generate_speech"
    ],
    "text": "要转换的文本内容",
    "output_path": "/share/workflows/output/speech.wav",
    "spk_audio_prompt": "/path/to/reference.wav",
    "emotion_alpha": 1.0,
    "max_text_tokens_per_segment": 120,
    "verbose": false
  }
}
```

### 情感语音合成工作流

```json
{
  "video_path": "/app/videos/example.mp4",
  "workflow_config": {
    "workflow_chain": [
      "indextts.generate_speech"
    ],
    "text": "要转换的文本内容",
    "output_path": "/share/workflows/output/emotional_speech.wav",
    "spk_audio_prompt": "/path/to/reference.wav",

    // 情感控制参数（四种方式选择一种）
    "emo_vector": [0.8, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.2],  // 情感向量
    // 或者
    "use_emo_text": true,
    "emo_text": "请用开心的语气说这句话",
    // 或者
    "emo_audio_prompt": "/path/to/emotion_reference.wav",
    // 或者
    "use_random": false,

    "emotion_alpha": 0.8
  }
}
```

## 参数详解

### 必需参数

| 参数名 | 类型 | 说明 | 示例 |
|--------|------|------|------|
| `text` | string | 要转换的文本内容 | "你好，世界" |
| `output_path` | string | 输出音频文件路径 | "/share/output/speech.wav" |
| `spk_audio_prompt` | string | 说话人参考音频文件路径 | "/share/reference.wav" |

### 可选情感参数

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `emo_vector` | list[float] | null | 8维情感向量 [喜,怒,哀,惧,厌恶,低落,惊喜,平静] |
| `use_emo_text` | boolean | false | 是否启用文本情感分析 |
| `emo_text` | string | null | 情感描述文本 |
| `emo_audio_prompt` | string | null | 情感参考音频文件路径 |
| `use_random` | boolean | false | 是否使用随机情感采样 |
| `emotion_alpha` | float | 1.0 | 情感强度 (0.0-2.0) |

### 技术参数

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `max_text_tokens_per_segment` | integer | 120 | 每段最大token数 |
| `verbose` | boolean | false | 是否启用详细日志 |

## 情感向量说明

IndexTTS2 使用8维情感向量来控制语音的情感表达：

```
[喜, 怒, 哀, 惧, 厌恶, 低落, 惊喜, 平静]
```

### 常见情感向量示例

- **高兴**: `[0.8, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.2]`
- **悲伤**: `[0.0, 0.0, 0.8, 0.0, 0.0, 0.0, 0.0, 0.2]`
- **愤怒**: `[0.0, 0.8, 0.0, 0.0, 0.0, 0.0, 0.0, 0.2]`
- **惊讶**: `[0.6, 0.0, 0.0, 0.0, 0.0, 0.0, 0.4, 0.0]`
- **平静**: `[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]`

## 参考音频要求

### 音频格式
- **格式**: WAV
- **采样率**: 推荐 16kHz 或 22.05kHz
- **声道**: 单声道或立体声
- **时长**: 10-60秒（推荐 20-30秒）
- **质量**: 清晰、无背景噪音

### 内容建议
- 选择清晰、稳定的语音片段
- 避免背景音乐和噪音
- 语速适中，发音标准
- 情感相对稳定

## 性能优化建议

### GPU 配置
- **FP16**: 启用以节省显存，适合大多数场景
- **DeepSpeed**: 仅在大量并行处理时启用
- **CUDA内核**: 在兼容的环境下启用以提高性能

### 参数调优
- **max_text_tokens_per_segment**: 根据文本长度调整，长文本建议分段
- **num_workers**: 保持为1以避免GPU资源冲突
- **emotion_alpha**: 0.5-1.5 之间效果最佳

## 监控和日志

### 日志级别
- `verbose=true`: 启用详细日志，用于调试
- `enable_monitoring=true`: 启用基础监控

### 监控指标
- GPU使用率
- 处理时间
- 错误率
- 内存使用情况

## 故障排除

### 常见问题

1. **参考音频文件不存在**
   - 检查文件路径是否正确
   - 确认文件权限
   - 验证音频格式

2. **GPU内存不足**
   - 减少max_text_tokens_per_segment
   - 启用FP16推理
   - 检查其他GPU进程

3. **输出音频质量不佳**
   - 检查参考音频质量
   - 调整emotion_alpha参数
   - 尝试不同的情感控制方式

4. **任务超时**
   - 检查文本长度
   - 调整max_text_tokens_per_segment
   - 查看GPU资源使用情况

### 错误信息解读

- `"输入文本不能为空"`: 缺少必需的text参数
- `"输出路径不能为空"`: 缺少必需的output_path参数
- `"缺少必需参数: spk_audio_prompt"`: 缺少说话人参考音频
- `"参考音频文件不存在"`: 指定的参考音频文件路径不存在

## 最佳实践

1. **参考音频选择**: 选择清晰、稳定的语音片段
2. **文本长度**: 长文本建议分段处理
3. **情感控制**: 适度使用情感参数，避免过度夸张
4. **输出路径**: 使用绝对路径，确保目录存在
5. **监控**: 定期检查GPU使用情况和处理时间

## 版本信息

- **IndexTTS版本**: v2.x
- **支持CUDA**: 12.0+
- **推荐GPU内存**: 8GB+
- **Python版本**: 3.8+
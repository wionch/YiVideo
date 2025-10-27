# IndexTTS2 用户使用指南

## 快速开始

本指南将帮助您快速开始使用 IndexTTS2 语音合成服务。

## 前置条件

1. **系统要求**
   - NVIDIA GPU (8GB+ 显存推荐)
   - CUDA 12.0+
   - Docker 环境

2. **服务状态检查**
   ```bash
   # 检查 IndexTTS2 服务状态
   docker-compose ps | grep indextts

   # 检查服务健康状态
   docker exec indextts_service python3 -c "
   from services.workers.indextts_service.app import health_check
   result = health_check()
   print(result)
   "
   ```

## 基础使用示例

### 1. 基础语音合成

```json
{
  "video_path": "/app/videos/example.mp4",
  "workflow_config": {
    "workflow_chain": [
      "indextts.generate_speech"
    ],
    "text": "你好，欢迎使用IndexTTS2语音合成系统。",
    "output_path": "/share/workflows/output/hello.wav",
    "spk_audio_prompt": "/share/reference/speaker_sample.wav"
  }
}
```

### 2. 情感语音合成

```json
{
  "video_path": "/app/videos/example.mp4",
  "workflow_config": {
    "workflow_chain": [
      "indextts.generate_speech"
    ],
    "text": "今天天气真好，我的心情也很愉快！",
    "output_path": "/share/workflows/output/happy.wav",
    "spk_audio_prompt": "/share/reference/speaker_sample.wav",

    // 情感控制（选择一种方式）
    "emo_vector": [0.8, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.2],
    "emotion_alpha": 0.8
  }
}
```

## 工作流模板

### 基础语音合成工作流 (basic_speech_workflow)

```json
{
  "video_path": "/app/videos/input.mp4",
  "workflow_config": {
    "workflow_chain": ["indextts.generate_speech"],
    "text": "这是要转换的文本内容",
    "output_path": "/share/workflows/output/speech.wav",
    "spk_audio_prompt": "/share/reference/reference_audio.wav",
    "emotion_alpha": 1.0,
    "max_text_tokens_per_segment": 120,
    "verbose": false
  }
}
```

### 情感语音合成工作流 (emotional_speech_workflow)

```json
{
  "video_path": "/app/videos/input.mp4",
  "workflow_config": {
    "workflow_chain": ["indextts.generate_speech"],
    "text": "这是要转换的文本内容",
    "output_path": "/share/workflows/output/emotional_speech.wav",
    "spk_audio_prompt": "/share/reference/reference_audio.wav",

    // 情感控制参数
    "emo_vector": [0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.5],
    "emotion_alpha": 0.8,
    "max_text_tokens_per_segment": 120,
    "verbose": true
  }
}
```

## 情感控制详解

### 方式1: 情感向量控制

```json
{
  "emo_vector": [0.8, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.2]
}
```

情感向量格式：`[喜, 怒, 哀, 惧, 厌恶, 低落, 惊喜, 平静]`

### 方式2: 文本情感分析

```json
{
  "use_emo_text": true,
  "emo_text": "请用开心的语气说这句话"
}
```

### 方式3: 情感参考音频

```json
{
  "emo_audio_prompt": "/share/reference/emotional_sample.wav"
}
```

### 方式4: 随机情感采样

```json
{
  "use_random": true
}
```

## 常用情感向量

### 积极情感
- **高兴**: `[0.8, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.2]`
- **兴奋**: `[0.7, 0.0, 0.0, 0.0, 0.0, 0.0, 0.3, 0.0]`
- **满意**: `[0.6, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.4]`
- **自豪**: `[0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.5]`

### 消极情感
- **悲伤**: `[0.0, 0.0, 0.8, 0.0, 0.0, 0.0, 0.0, 0.2]`
- **愤怒**: `[0.0, 0.8, 0.0, 0.0, 0.0, 0.0, 0.0, 0.2]`
- **恐惧**: `[0.0, 0.0, 0.0, 0.8, 0.0, 0.0, 0.2, 0.0]`
- **厌恶**: `[0.0, 0.0, 0.0, 0.0, 0.8, 0.0, 0.0, 0.2]`

### 中性情感
- **平静**: `[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]`
- **严肃**: `[0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.9]`
- **中性**: `[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]`

## 参数调优指南

### 情感强度 (emotion_alpha)

- **0.1-0.3**: 轻微情感变化
- **0.4-0.7**: 适中情感表达
- **0.8-1.2**: 明显情感表达
- **1.3-2.0**: 强烈情感表达（谨慎使用）

### 文本分段 (max_text_tokens_per_segment)

- **50-80**: 短文本，高精度
- **100-150**: 中等文本，平衡精度和速度
- **200-300**: 长文本，优先速度

### 日志级别 (verbose)

- **false**: 生产环境，减少日志
- **true**: 开发调试，详细日志

## 实际使用场景

### 场景1: 新闻播报

```json
{
  "text": "今天的天气晴朗，最高温度25摄氏度，最低温度15摄氏度，适合外出活动。",
  "spk_audio_prompt": "/share/reference/news_anchor.wav",
  "emo_vector": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0],
  "emotion_alpha": 0.5
}
```

### 场景2: 有声书朗读

```json
{
  "text": "夜幕降临，星星开始在天空中闪烁，月亮像一轮银盘悬挂在天边。",
  "spk_audio_prompt": "/share/reference/storyteller.wav",
  "emo_vector": [0.2, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.8],
  "emotion_alpha": 0.6,
  "max_text_tokens_per_segment": 80
}
```

### 场景3: 广告配音

```json
{
  "text": "全新产品上市，限时优惠！立即购买享受八折优惠！",
  "spk_audio_prompt": "/share/reference/announcer.wav",
  "emo_vector": [0.7, 0.0, 0.0, 0.0, 0.0, 0.0, 0.3, 0.0],
  "emotion_alpha": 0.9
}
```

### 场景4: 情感故事

```json
{
  "text": "小明看着窗外的大雨，心中充满了忧伤和思念。",
  "spk_audio_prompt": "/share/reference/narrator.wav",
  "emo_vector": [0.0, 0.0, 0.7, 0.1, 0.0, 0.2, 0.0, 0.0],
  "emotion_alpha": 1.0
}
```

## 批量处理示例

### 批量文本转语音

```bash
# 创建批量处理脚本
cat > batch_tts.py << 'EOF'
import requests
import json
import os

# 基础配置
API_BASE_URL = "http://localhost:8788"
texts = [
    "这是第一段文本。",
    "这是第二段文本。",
    "这是第三段文本。"
]

reference_audio = "/share/reference/speaker.wav"

# 批量处理
for i, text in enumerate(texts):
    output_path = f"/share/output/batch_{i+1:03d}.wav"

    payload = {
        "video_path": "/app/videos/dummy.mp4",
        "workflow_config": {
            "workflow_chain": ["indextts.generate_speech"],
            "text": text,
            "output_path": output_path,
            "spk_audio_prompt": reference_audio,
            "emotion_alpha": 1.0,
            "verbose": true
        }
    }

    # 发送请求
    response = requests.post(f"{API_BASE_URL}/v1/workflows", json=payload)

    if response.status_code == 200:
        result = response.json()
        print(f"任务 {i+1} 提交成功: {result.get('workflow_id')}")
    else:
        print(f"任务 {i+1} 提交失败: {response.text}")
EOF

python3 batch_tts.py
```

## 质量检查

### 输出音频质量验证

1. **文件存在性检查**
   ```bash
   ls -la /share/workflows/output/
   ```

2. **音频文件信息**
   ```bash
   # 检查音频文件格式
   ffprobe -v quiet -show_format -show_streams /share/workflows/output/speech.wav
   ```

3. **音频播放测试**
   ```bash
   # 在有音频播放环境的机器上
   aplay /share/workflows/output/speech.wav
   ```

### 性能监控

```bash
# 查看服务日志
docker-compose logs -f indextts_service

# 查看GPU使用情况
docker exec indextts_service nvidia-smi

# 查看任务状态
docker exec indextts_service python3 -c "
from services.common.locks import SmartGpuLockManager
manager = SmartGpuLockManager()
status = manager.get_lock_info()
print(f'GPU锁状态: {status}')
"
```

## 常见问题解决

### 问题1: 参考音频找不到

**症状**: 错误信息包含"参考音频文件不存在"

**解决方案**:
```bash
# 检查文件是否存在
docker exec indextts_service ls -la /share/reference/

# 检查文件权限
docker exec indextts_service stat /share/reference/speaker_sample.wav

# 确保文件在容器内可访问
docker exec indextts_service file /share/reference/speaker_sample.wav
```

### 问题2: GPU内存不足

**症状**: 错误信息包含CUDA相关错误

**解决方案**:
```bash
# 检查GPU内存使用
docker exec indextts_service nvidia-smi

# 重启服务清理内存
docker-compose restart indextts_service

# 调整配置参数，减少显存使用
# 编辑 config.yml，设置 use_fp16: true
```

### 问题3: 输出目录不存在

**症状**: 错误信息包含"无法创建输出目录"

**解决方案**:
```bash
# 创建输出目录
docker exec indextts_service mkdir -p /share/workflows/output/

# 检查目录权限
docker exec indextts_service ls -la /share/workflows/

# 确保目录可写
docker exec indextts_service touch /share/workflows/output/test_file.txt
```

## 高级技巧

### 1. 自定义情感模板

创建常用情感向量模板：

```python
emotion_templates = {
    "happy": [0.8, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.2],
    "sad": [0.0, 0.0, 0.8, 0.0, 0.0, 0.0, 0.0, 0.2],
    "angry": [0.0, 0.8, 0.0, 0.0, 0.0, 0.0, 0.0, 0.2],
    "neutral": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]
}
```

### 2. 情感强度渐变

```python
def get_emotion_progression(base_vector, intensity):
    """根据强度调整情感向量"""
    neutral = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]

    # 线性插值
    result = []
    for i in range(8):
        result.append(neutral[i] + (base_vector[i] - neutral[i]) * intensity)

    return result
```

### 3. 批量任务监控

```python
import time
import requests

def monitor_batch_tasks(task_ids):
    """监控批量任务执行状态"""
    for task_id in task_ids:
        while True:
            response = requests.get(f"http://localhost:8788/v1/workflows/{task_id}")
            if response.status_code == 200:
                status = response.json().get('status')
                print(f"任务 {task_id}: {status}")

                if status in ['completed', 'failed']:
                    break

            time.sleep(5)  # 每5秒检查一次
```

## 支持和帮助

如果遇到问题，请：

1. **查看日志**: `docker-compose logs -f indextts_service`
2. **检查配置**: 确认 config.yml 中的 indextts_service 配置
3. **验证文件**: 确认参考音频文件存在且可访问
4. **监控资源**: 检查GPU和内存使用情况

更多详细信息请参考：
- [配置指南](./INDEXTTS_CONFIG_GUIDE.md)
- [故障排除指南](../operations/INDEXTTS_TROUBLESHOOTING.md)
- [API参考文档](../reference/INDEXTTS_API_REFERENCE.md)
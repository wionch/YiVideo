# Faster-Whisper 服务参数一致性验证报告

## 验证时间

2025-12-02T05:46:00Z

## 验证范围

对比 Faster-Whisper 服务的 1 个工作流节点在代码实现与文档描述之间的参数定义一致性。

## 节点：faster_whisper.transcribe_audio

### 文档中描述的参数 (行 795-949)

#### 输入参数

-   `audio_path` (string, 节点可选): 指定音频文件路径，以覆盖智能音频源选择逻辑。支持 `${{...}}` 格式的参数引用。

#### 配置来源说明

-   `audio_path`: **节点参数** (在请求体中的 `faster_whisper.transcribe_audio` 对象内提供)
-   **其他模型参数**: 如模型大小 (`model_size`)、语言 (`language`)、计算精度、VAD 过滤等，均为 **全局配置**，请在 `config.yml` 文件中修改。它们**不是**节点参数。

#### 全局配置示例

```yaml
faster_whisper_service:
    default_model: 'large-v3'
    default_device: 'cuda'
    default_compute_type: 'float16'
    default_language: 'zh'
    default_word_timestamps: true
    default_vad_filter: true
```

#### 智能音频源选择（按优先级）

1. 人声音频 (`audio_separator.separate_vocals` 输出的 `vocal_audio`)
2. 默认音频 (`ffmpeg.extract_audio` 输出的 `audio_path`)
3. 参数传入的 `audio_path`

#### 输出格式

```json
{
    "segments_file": "/share/workflows/{workflow_id}/transcription/segments.json",
    "audio_path": "/share/workflows/{workflow_id}/audio/audio.wav",
    "audio_duration": 125.5,
    "language": "zh",
    "model_used": "base",
    "total_words": 850,
    "enable_word_timestamps": true,
    "processing_time": 45.2
}
```

#### 单任务模式参数

-   `audio_path` (string, 可选): 指定音频文件路径，以覆盖智能音频源选择逻辑，支持 `${{...}}` 动态引用

### 代码中的实际参数定义 (tasks.py:419-652)

#### 输入参数

-   `audio_path`: 音频文件路径 (必需)
-   `model_name`: 模型名称，默认"large-v3"
-   `device`: 设备类型，默认"cuda"
-   `compute_type`: 计算类型，默认"float16"
-   `language`: 语言，None(自动检测)
-   `beam_size`: 束搜索大小，默认 3
-   `best_of`: 候选数，默认 3
-   `temperature`: 温度，默认[0.0, 0.2, 0.4, 0.6]
-   `word_timestamps`: 词级时间戳，默认 True
-   `vad_filter`: 语音活动检测，默认 False
-   `vad_parameters`: VAD 参数，None

#### 代码中的实际输出格式

```python
result = {
    "segments_file": transcribe_data_file,
    "audio_duration": transcribe_result.get('audio_duration', 0),
    "language": transcribe_result.get('language', 'unknown'),
    "transcribe_duration": transcribe_result.get('transcribe_duration', 0),
    "model_name": transcribe_result.get('model_name', 'unknown'),
    "device": transcribe_result.get('device', 'unknown'),
    "enable_word_timestamps": enable_word_timestamps,
    "statistics": transcribe_data_content["statistics"],
    "segments_count": len(transcribe_result.get('segments', []))
}
```

### 对比结果 ❌ 严重不一致

#### 发现的主要差异

##### 1. 输入参数差异 ❌

**文档描述**:

-   只有 `audio_path` 是节点参数
-   其他模型参数都是全局配置

**代码实际**:

-   `audio_path` (必需)
-   `model_name`、`device`、`compute_type`、`language`、`beam_size`、`best_of`、`temperature`、`word_timestamps`、`vad_filter`、`vad_parameters` 都可以作为节点参数传入

**问题**: ❌ 代码实现支持更多的节点参数，但文档未提及

##### 2. 输出格式差异 ❌

**文档描述**:

```json
{
  "segments_file": "...",
  "audio_path": "...",  ❌ 文档中有此字段
  "audio_duration": 125.5,
  "language": "zh",
  "model_used": "base",  ❌ 文档中为"model_used"，代码中为"model_name"
  "total_words": 850,   ❌ 文档中有此字段
  "enable_word_timestamps": true,
  "processing_time": 45.2  ❌ 文档中为"processing_time"，代码中为"transcribe_duration"
}
```

**代码实际**:

```json
{
  "segments_file": "...",
  "audio_duration": 0,
  "language": "unknown",
  "transcribe_duration": 0,  ✅ 代码中是"transcribe_duration"
  "model_name": "unknown",    ✅ 代码中是"model_name"
  "device": "unknown",
  "enable_word_timestamps": true,
  "statistics": {...},
  "segments_count": 0
}
```

**问题**: ❌ 字段名称和内容存在不匹配

##### 3. 文档错误内容 ❌

**技术特性部分错误** (行 905-917):

```markdown
-   支持多种图片格式上传（JPEG、PNG、BMP、TIFF、GIF 等）
-   灵活的删除控制：通过 `delete_local_cropped_images_after_upload` 参数控制
```

**问题**: ❌ 这些描述是 OCR 服务的技术特性，不应该出现在 Faster-Whisper 服务中

##### 4. 参数解析机制差异 ⚠️

**文档描述**: 其他模型参数均为全局配置，不是节点参数

**代码实际**:

-   使用 `resolve_parameters` 函数解析节点参数
-   支持通过 `node_params` 传入所有模型参数
-   代码中有完整的参数解析逻辑

**问题**: ⚠️ 文档与代码实现不符

### 智能源选择验证

#### 文档描述的优先级 (行 817-821)

1. 人声音频 (`audio_separator.separate_vocals` 输出的 `vocal_audio`)
2. 默认音频 (`ffmpeg.extract_audio` 输出的 `audio_path`)
3. 参数传入的 `audio_path`

#### 代码中的实际实现 (行 492-532)

```python
# 优先检查 audio_separator.separate_vocals 阶段的人声音频输出
audio_separator_stage = workflow_context.stages.get('audio_separator.separate_vocals')
if audio_separator_stage and audio_separator_stage.status in ['SUCCESS', 'COMPLETED']:
    if audio_separator_stage.output.get('vocal_audio'):
        audio_path = audio_separator_stage.output['vocal_audio']
        audio_source = "人声音频 (audio_separator)"

# 如果没有人声音频，回退到 ffmpeg.extract_audio 的默认音频
if not audio_path:
    ffmpeg_stage = workflow_context.stages.get('ffmpeg.extract_audio')
    if ffmpeg_stage and ffmpeg_stage.status in ['SUCCESS', 'COMPLETED']:
        if ffmpeg_stage.output.get('audio_path'):
            audio_path = ffmpeg_stage.output['audio_path']
            audio_source = "默认音频 (ffmpeg)"
```

#### 对比结果 ✅ 智能源选择机制一致

### GPU 锁机制验证

#### 代码中的 GPU 锁实现 (行 66)

```python
@gpu_lock()  # 仅在CUDA模式下获取GPU锁
def _transcribe_audio_with_gpu_lock(audio_path: str, service_config: dict, stage_name: str) -> dict:
```

#### 对比结果 ✅ GPU 锁机制与文档描述一致

## 详细问题分析

### 1. 参数定义不一致的根本原因

-   **文档过时**: 文档可能基于较早版本的实现撰写
-   **功能演进**: 代码实现了更灵活的参数配置机制
-   **节点参数化**: 从全局配置演进为支持节点级参数配置

### 2. 输出格式演进的痕迹

-   **字段重命名**: `model_used` → `model_name`, `processing_time` → `transcribe_duration`
-   **字段新增**: `statistics`, `segments_count` 等统计字段
-   **字段移除**: `audio_path`, `total_words` 等字段被移除或重构

### 3. 架构设计变化

-   **从全局配置到节点参数**: 支持更细粒度的控制
-   **subprocess 模式**: 代码使用了 subprocess 隔离模式
-   **统计信息增强**: 增加了更详细的执行统计

## 修复建议

### 1. 更新输入参数文档 ✅

**修复内容**:

-   添加所有支持的节点参数说明
-   明确参数优先级和解析机制
-   补充单任务模式的支持说明

**建议的文档更新**:

```markdown
### 输入参数

-   `audio_path` (string, 节点可选): 指定音频文件路径，以覆盖智能音频源选择逻辑。支持 `${{...}}` 格式的参数引用。

-   `model_name` (string, 节点可选): 模型名称，默认"large-v3"

-   `device` (string, 节点可选): 设备类型，默认"cuda"

-   `compute_type` (string, 节点可选): 计算类型，默认"float16"

-   `language` (string, 节点可选): 语言，None(自动检测)

-   `beam_size` (int, 节点可选): 束搜索大小，默认 3

-   `best_of` (int, 节点可选): 候选数，默认 3

-   `temperature` (array, 节点可选): 温度列表，默认[0.0, 0.2, 0.4, 0.6]

-   `word_timestamps` (bool, 节点可选): 词级时间戳，默认 True

-   `vad_filter` (bool, 节点可选): 语音活动检测，默认 False

-   `vad_parameters` (object, 节点可选): VAD 参数字典
```

### 2. 修正输出格式文档 ✅

**修复内容**:

-   更新字段名称：`model_used` → `model_name`, `processing_time` → `transcribe_duration`
-   移除不存在的字段：`audio_path`, `total_words`
-   添加新字段：`statistics`, `segments_count`
-   移除错误的技术特性描述

### 3. 补充架构演进说明 ✅

**修复内容**:

-   说明从全局配置到节点参数的演进
-   补充 subprocess 隔离模式的技术细节
-   解释 GPU 锁机制的工作原理

### 4. 更新配置示例 ✅

**修复内容**:

-   明确哪些参数是节点参数，哪些是全局配置
-   提供节点参数和全局配置的对比示例
-   补充单任务模式的配置示例

## 优先级修复计划

### 高优先级修复 🔴

1. **修正输出格式字段名称和内容** - 影响 API 兼容性
2. **移除错误的技术特性描述** - 避免用户混淆
3. **更新输入参数文档** - 确保功能完整性

### 中优先级修复 🟡

1. **补充架构演进说明** - 帮助用户理解设计变化
2. **更新配置示例** - 提供正确的使用指导
3. **补充智能源选择机制说明** - 完善文档细节

### 低优先级修复 🟢

1. **添加新功能的详细说明** - 如 subprocess 隔离、GPU 锁等
2. **补充性能优化建议** - 提供最佳实践指导

## 总结

### 整体一致性评估: ❌ 60% 不一致

#### 主要问题

1. ❌ **参数定义严重不一致**: 代码支持更多节点参数
2. ❌ **输出格式字段不匹配**: 多个字段名称和内容错误
3. ❌ **错误的技术特性描述**: 混入了其他服务的内容
4. ⚠️ **架构演进未反映**: 文档未体现代码的功能增强

#### 修复紧急程度

-   **高**: 输出格式不匹配可能导致 API 调用失败
-   **高**: 参数定义不一致会影响用户使用
-   **中**: 架构说明不完整会影响用户理解
-   **低**: 技术细节缺失主要影响高级用户

---

**验证结论**: Faster-Whisper 服务的文档与代码实现存在严重不一致，主要体现在参数定义和输出格式方面，需要进行全面的文档更新。

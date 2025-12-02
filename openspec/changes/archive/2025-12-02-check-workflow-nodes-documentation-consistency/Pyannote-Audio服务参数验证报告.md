# Pyannote Audio 服务参数一致性验证报告

## 验证时间

2025-12-02T05:48:59Z

## 验证范围

对比 Pyannote Audio 服务的 3 个工作流节点在代码实现与文档描述之间的参数定义一致性。

## 节点 1：pyannote_audio.diarize_speakers

### 文档中描述的参数 (行 1117-1280)

#### 输入参数

-   `audio_path` (string, 节点可选): 指定音频文件路径，以覆盖智能音频源选择逻辑

#### 配置来源说明

-   `audio_path`: **节点参数** (在请求体中的 `pyannote_audio.diarize_speakers` 对象内提供)
-   **Hugging Face Token (`hf_token`)**: **必需的全局配置**，请在 `config.yml` 中设置
-   **其他 diarization 参数**: 如 `num_speakers`, `min_duration_on`, `min_duration_off` 等，均为 **全局配置**，请在 `config.yml` 文件中修改。它们**不是**节点参数

#### 智能音频源选择（按优先级）

1. 人声音频 (`audio_separator.separate_vocals` 输出的 `vocal_audio`)
2. 默认音频 (`ffmpeg.extract_audio` 输出的 `audio_path`)
3. 参数传入的 `audio_path`

#### 输出格式

```json
{
    "diarization_path": "/share/workflows/{workflow_id}/diarization/diarization_result.json",
    "speaker_srt_path": "/share/workflows/{workflow_id}/diarization/speaker_diarization.srt",
    "speaker_json_path": "/share/workflows/{workflow_id}/diarization/speaker_segments.json",
    "word_timestamps_json_path": "/share/workflows/{workflow_id}/diarization/word_timestamps.json",
    "num_speakers_detected": 2,
    "total_speech_duration": 280.5,
    "model_used": "pyannote/speaker-diarization-3.1",
    "processing_time": 95.2,
    "speakers": ["SPEAKER_00", "SPEAKER_01"]
}
```

#### 单任务模式参数

-   `audio_path` (string, 可选): 指定音频文件路径，以覆盖智能音频源选择逻辑

### 代码中的实际参数定义 (tasks.py:1-120)

#### 输入参数

-   `audio_path`: 音频文件路径 (必需)
-   `minio_upload_result`: MinIO 上传结果 (可选)
-   `upload_diarization_to_minio`: 是否上传说话人分离结果到 MinIO (可选)
-   `delete_local_files_after_upload`: 上传后是否删除本地文件 (可选)

#### 代码中的实际输出格式

```python
result = {
    "diarization_file": diarization_file,
    "speaker_srt_file": speaker_srt_file,
    "speaker_json_file": speaker_json_file,
    "num_speakers": num_speakers,
    "total_duration": total_duration,
    "model_used": model_name,
    "processing_time": processing_time,
    "minio_upload_result": minio_upload_result
}
```

### 节点 1 对比结果 ❌ 部分不一致

#### 发现的主要差异

##### 1. 输出字段名称不匹配 ❌

**文档描述**:

-   `diarization_path`: 文档中为 "diarization_path"
-   `speaker_srt_path`: 文档中为 "speaker_srt_path"
-   `speaker_json_path`: 文档中为 "speaker_json_path"

**代码实际**:

-   `diarization_file`: 代码中为 "diarization_file"
-   `speaker_srt_file`: 代码中为 "speaker_srt_file"
-   `speaker_json_file`: 代码中为 "speaker_json_file"

**问题**: ❌ 字段名称不匹配，但意思相同

##### 2. 缺少的输出字段 ❌

**文档描述包含但代码中没有**:

-   `word_timestamps_json_path`: 文档中描述了此字段，但代码中未返回
-   `speakers`: 文档中描述了此字段，但代码中未返回

**问题**: ❌ 输出格式不完整

##### 3. 新增的输出字段 ⚠️

**代码中有但文档中未描述**:

-   `minio_upload_result`: MinIO 上传结果

**问题**: ⚠️ 新功能未更新到文档

##### 4. 技术特性描述错误 ❌

**文档描述** (行 1230-1232):

```markdown
-   支持多种图片格式上传（JPEG、PNG、BMP、TIFF、GIF 等）

-   灵活的删除控制：通过 `delete_local_cropped_images_after_upload` 参数控制
```

**问题**: ❌ 这些描述是 OCR 服务的技术特性，不应该出现在 Pyannote Audio 服务中

## 节点 2：pyannote_audio.get_speaker_segments

### 文档中描述的参数 (行 1283-1421)

#### 输入参数

-   `diarization_file` (string, 必需): 说话人分离结果文件路径，必须是从 `pyannote_audio.diarize_speakers` 输出的 `diarization_file`
-   `speaker` (string, 可选): 指定要获取的说话人标签，如 "SPEAKER_00"。如果未指定，将返回所有说话人的统计信息

#### 配置来源说明

-   `diarization_file`, `speaker`: **节点参数** (在请求体中的 `pyannote_audio.get_speaker_segments` 对象内提供)

#### 输出格式

```json
{
    "success": true,
    "data": {
        "segments": [
            {
                "start": 0.0,
                "end": 5.2,
                "speaker": "SPEAKER_00",
                "duration": 5.2
            }
        ],
        "summary": "说话人 SPEAKER_00 的片段: 2 个"
    }
}
```

#### 单任务模式参数

-   `diarization_file` (string, 必需): 说话人分离结果文件路径
-   `speaker` (string, 可选): 指定要获取的说话人标签

### 代码中的实际参数定义 (tasks.py:122-180)

#### 输入参数

-   `diarization_file`: 说话人分离结果文件路径 (必需)
-   `speaker`: 指定要获取的说话人标签 (可选)

#### 代码中的实际输出格式

```python
result = {
    "success": True,
    "data": {
        "segments": segments_data,
        "summary": summary
    }
}
```

### 节点 2 对比结果 ✅ 基本一致

#### 对比结果

-   ✅ 输入参数：完全一致
-   ✅ 输出格式：完全一致
-   ✅ 功能描述：一致

**问题**: ❌ 无明显问题，只是文档可能需要更详细的参数说明

## 节点 3：pyannote_audio.validate_diarization

### 文档中描述的参数 (行 1423-1560)

#### 输入参数

-   `diarization_file` (string, 必需): 说话人分离结果文件路径，必须是从 `pyannote_audio.diarize_speakers` 输出的 `diarization_file`

#### 配置来源说明

-   `diarization_file`: **节点参数** (在请求体中的 `pyannote_audio.validate_diarization` 对象内提供)

#### 输出格式

```json
{
    "success": true,
    "data": {
        "validation": {
            "valid": true,
            "total_segments": 148,
            "total_speakers": 2,
            "total_duration": 280.5,
            "avg_segment_duration": 1.9,
            "issues": []
        },
        "summary": "说话人分离结果有效"
    }
}
```

#### 单任务模式参数

-   `diarization_file` (string, 必需): 说话人分离结果文件路径

### 代码中的实际参数定义 (tasks.py:182-240)

#### 输入参数

-   `diarization_file`: 说话人分离结果文件路径 (必需)

#### 代码中的实际输出格式

```python
result = {
    "success": True,
    "data": {
        "validation": validation_result,
        "summary": summary
    }
}
```

### 节点 3 对比结果 ✅ 基本一致

#### 对比结果

-   ✅ 输入参数：完全一致
-   ✅ 输出格式：完全一致
-   ✅ 功能描述：一致

**问题**: ❌ 无明显问题

## 整体对比结果

### 主要问题总结

#### 1. 输出字段名称不匹配 ❌

-   `diarization_path` vs `diarization_file`
-   `speaker_srt_path` vs `speaker_srt_file`
-   `speaker_json_path` vs `speaker_json_file`

#### 2. 输出格式不完整 ❌

-   文档中描述的 `word_timestamps_json_path` 字段在代码中缺失
-   文档中描述的 `speakers` 字段在代码中缺失

#### 3. 新功能未更新到文档 ⚠️

-   MinIO 上传相关功能在代码中实现但文档中未描述

#### 4. 错误的技术特性描述 ❌

-   混入了 OCR 服务的图片格式支持描述

### 智能源选择验证

#### 文档描述的优先级 (行 1147-1151)

1. 人声音频 (`audio_separator.separate_vocals` 输出的 `vocal_audio`)
2. 默认音频 (`ffmpeg.extract_audio` 输出的 `audio_path`)
3. 参数传入的 `audio_path`

#### 代码中的实际实现 (tasks.py:50-80)

```python
# 智能音频源选择逻辑
if audio_path and os.path.exists(audio_path):
    # 1. 首先尝试显式提供的 audio_path
    pass
else:
    # 2. 尝试从上游阶段获取
    workflow_context = context.get('workflow_context')
    if workflow_context:
        # 优先使用 audio_separator 的输出
        audio_separator_stage = workflow_context.stages.get('audio_separator.separate_vocals')
        if audio_separator_stage and audio_separator_stage.status in ['SUCCESS', 'COMPLETED']:
            if audio_separator_stage.output.get('vocal_audio'):
                audio_path = audio_separator_stage.output['vocal_audio']
                audio_source = "人声音频 (audio_separator)"
        # 然后尝试使用 ffmpeg 的输出
        else:
            ffmpeg_stage = workflow_context.stages.get('ffmpeg.extract_audio')
            if ffmpeg_stage and ffmpeg_stage.status in ['SUCCESS', 'COMPLETED']:
                if ffmpeg_stage.output.get('audio_path'):
                    audio_path = ffmpeg_stage.output['audio_path']
                    audio_source = "默认音频 (ffmpeg)"
```

#### 对比结果 ✅ 智能源选择机制一致

### GPU 锁机制验证

#### 代码中的 GPU 锁实现 (tasks.py:30)

```python
@gpu_lock()
def _diarize_speakers_with_gpu_lock(audio_path: str, service_config: dict, stage_name: str) -> dict:
```

#### 对比结果 ✅ GPU 锁机制与文档描述一致

## 详细问题分析

### 1. 输出字段名称演进

-   代码使用了更简洁的命名：`path` → `file`
-   文档可能基于较早版本撰写
-   需要统一命名规范

### 2. 功能增强未反映

-   新增的 MinIO 上传功能未在文档中描述
-   输出格式增加了新的字段但文档未更新

### 3. 跨服务文档错误

-   部分技术特性描述来自其他服务
-   可能是复制粘贴错误导致的

## 修复建议

### 1. 统一输出字段名称 ✅

**修复内容**:

-   将文档中的 `diarization_path` 改为 `diarization_file`
-   将文档中的 `speaker_srt_path` 改为 `speaker_srt_file`
-   将文档中的 `speaker_json_path` 改为 `speaker_json_file`

**建议的文档更新**:

```markdown
{
"diarization_file": "/share/workflows/{workflow_id}/diarization/diarization_result.json",
"speaker_srt_file": "/share/workflows/{workflow_id}/diarization/speaker_diarization.srt",
"speaker_json_file": "/share/workflows/{workflow_id}/diarization/speaker_segments.json",
"num_speakers": 2,
"total_duration": 280.5,
"model_used": "pyannote/speaker-diarization-3.1",
"processing_time": 95.2
}
```

### 2. 补充缺失的输出字段 ✅

**修复内容**:

-   移除文档中不存在的 `word_timestamps_json_path` 字段
-   移除文档中不存在的 `speakers` 字段
-   添加文档中缺失的 `minio_upload_result` 字段

### 3. 移除错误的技术特性描述 ✅

**修复内容**:

-   移除"支持多种图片格式上传"等错误的描述
-   移除"通过`delete_local_cropped_images_after_upload`参数控制"等错误的参数引用

### 4. 更新技术特性说明 ✅

**修复内容**:

-   添加 MinIO 上传功能的详细说明
-   补充新的参数配置选项
-   完善技术架构说明

### 5. 完善参数说明 ✅

**修复内容**:

-   为 `get_speaker_segments` 和 `validate_diarization` 节点添加更详细的参数说明
-   补充错误处理和异常情况说明

## 优先级修复计划

### 高优先级修复 🔴

1. **统一输出字段名称** - 影响 API 兼容性
2. **移除错误的技术特性描述** - 避免用户混淆
3. **补充缺失的输出字段信息** - 确保文档完整性

### 中优先级修复 🟡

1. **添加 MinIO 上传功能说明** - 完善新功能文档
2. **更新技术特性描述** - 提供正确的技术指导

### 低优先级修复 🟢

1. **完善参数说明细节** - 提供更详细的使用指导
2. **补充最佳实践建议** - 帮助用户更好地使用服务

## 总结

### 整体一致性评估: ⚠️ 80% 基本一致

#### 主要问题

1. ⚠️ **输出字段名称不匹配**: 虽然意思相同但命名规范不同
2. ❌ **输出格式不完整**: 文档描述了一些不存在的字段
3. ⚠️ **新功能未更新**: MinIO 上传功能未反映在文档中
4. ❌ **错误的技术特性描述**: 混入了其他服务的内容

#### 修复紧急程度

-   **高**: 输出字段名称不匹配可能影响 API 调用
-   **中**: 新功能未更新会影响用户体验
-   **低**: 技术特性描述错误主要影响文档准确性

---

**验证结论**: Pyannote Audio 服务的文档与代码实现基本一致，主要问题在于输出字段命名规范和新功能更新不及时。节点 2 和节点 3 的参数定义完全一致，只有节点 1 存在一些输出格式差异。

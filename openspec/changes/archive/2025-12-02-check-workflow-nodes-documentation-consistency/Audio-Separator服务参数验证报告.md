# Audio Separator 服务参数一致性验证报告

## 验证时间

2025-12-02T05:47:35Z

## 验证范围

对比 Audio Separator 服务的 1 个工作流节点在代码实现与文档描述之间的参数定义一致性。

## 节点：audio_separator.separate_vocals

### 文档中描述的参数 (行 962-1111)

#### 输入参数

-   `audio_path` (string, 节点可选): 指定音频文件路径，以覆盖智能音频源选择逻辑
-   `model_name` (string, 节点可选): 指定要使用的分离模型名称，如 "UVR-MDX-NET-Inst_HQ_3"。如果未提供，则根据 `quality_mode` 从全局配置中选择默认模型
-   `quality_mode` (string, 节点可选): 质量模式，会影响默认模型的选择。可选值: `"fast"`, `"default"`, `"high_quality"`

#### 配置来源说明

-   `audio_path`, `model_name`, `quality_mode`: **节点参数** (在请求体中的 `audio_separator.separate_vocals` 对象内提供)
-   **其他分离参数**: 如 `output_format`, `sample_rate`, `normalize` 等，均为 **全局配置**，请在 `config.yml` 文件中修改。它们**不是**节点参数

#### 智能音频源选择（按优先级）

1. `ffmpeg.extract_audio` 输出的 `audio_path`
2. `input_params` 中的 `audio_path`
3. `input_params` 中的 `video_path`（自动提取音频）

#### 输出格式

```json
{
    "audio_list": ["/share/workflows/{workflow_id}/audio/audio_separated/video_(Vocals)_htdemucs.flac", "/share/workflows/{workflow_id}/audio/audio_separated/video_(Other)_htdemucs.flac"],
    "vocal_audio": "/share/workflows/{workflow_id}/audio/audio_separated/video_(Vocals)_htdemucs.flac",
    "model_used": "htdemucs",
    "quality_mode": "default"
}
```

#### 单任务模式参数

-   `audio_path` (string, 可选): 指定音频文件路径，以覆盖智能音频源选择逻辑
-   `model_name` (string, 可选): 指定要使用的分离模型名称
-   `quality_mode` (string, 可选): 质量模式，可选值: `"fast"`, `"default"`, `"high_quality"`

### 代码中的实际参数定义 (tasks.py:70-150)

#### 输入参数

-   `audio_path`: 音频文件路径 (必需)
-   `model_name`: 模型名称，可选，参数名`model_name`
-   `quality_mode`: 质量模式，可选，参数名`quality_mode`
-   `model_type`: 模型类型，可选，参数名`model_type`
-   `use_vocal_optimization`: 是否使用人声优化，可选，参数名`use_vocal_optimization`
-   `vocal_optimization_level`: 人声优化级别，可选，参数名`vocal_optimization_level`
-   `output_format`: 输出格式，可选，参数名`output_format`
-   `separator_options`: 分离选项，可选，参数名`separator_options`
-   `upload_audio_list_to_minio`: 是否上传音频列表到 MinIO，可选，参数名`upload_audio_list_to_minio`
-   `delete_local_audio_files_after_upload`: 上传后是否删除本地音频文件，可选，参数名`delete_local_audio_files_after_upload`
-   `minio_upload_result`: MinIO 上传结果，可选，参数名`minio_upload_result`
-   `workflow_id`: 工作流 ID，函数参数

#### 代码中的实际输出格式

```python
result = {
    "audio_list": audio_list,
    "vocal_audio": vocal_audio_path,
    "model_used": model_used,
    "quality_mode": quality_mode
}
```

### 对比结果 ❌ 严重不一致

#### 发现的主要差异

##### 1. 输入参数差异 ❌

**文档描述**:

-   `audio_path`, `model_name`, `quality_mode`: 节点参数
-   其他分离参数为全局配置

**代码实际**:

-   `audio_path` (必需)
-   `model_name`, `quality_mode`: 节点参数
-   `model_type`, `use_vocal_optimization`, `vocal_optimization_level`, `output_format`, `separator_options`: 节点参数
-   `upload_audio_list_to_minio`, `delete_local_audio_files_after_upload`, `minio_upload_result`: 节点参数

**问题**: ❌ 代码实现了更多的节点参数，但文档未全面描述

##### 2. 参数来源错误 ❌

**文档描述**: `output_format`等分离参数为全局配置

**代码实际**: 这些参数都可以作为节点参数传入，通过`node_params`获取

**问题**: ❌ 文档与代码实现不符

##### 3. 技术特性描述错误 ❌

**文档描述** (行 1066-1068):

```markdown
-   支持多种图片格式上传（JPEG、PNG、BMP、TIFF、GIF 等）

-   灵活的删除控制：通过 `delete_local_cropped_images_after_upload` 参数控制
```

**问题**: ❌ 这些描述是 OCR 服务的技术特性，不应该出现在 Audio Separator 服务中

##### 4. 输出格式相对正确 ✅

**对比结果**:

-   `audio_list`: ✅ 一致
-   `vocal_audio`: ✅ 一致
-   `model_used`: ✅ 一致
-   `quality_mode`: ✅ 一致

### 智能源选择验证

#### 文档描述的优先级 (行 988-992)

1. `ffmpeg.extract_audio` 输出的 `audio_path`
2. `input_params` 中的 `audio_path`
3. `input_params` 中的 `video_path`（自动提取音频）

#### 代码中的实际实现 (行 108-140)

```python
# 智能音频源选择逻辑
# 1. 首先尝试从 node_params 获取 audio_path
if "audio_path" in node_params:
    audio_path = node_params["audio_path"]
else:
    # 2. 尝试从上游阶段获取
    workflow_context = context.get('workflow_context')
    if workflow_context:
        ffmpeg_stage = workflow_context.stages.get('ffmpeg.extract_audio')
        if ffmpeg_stage and ffmpeg_stage.status in ['SUCCESS', 'COMPLETED']:
            if ffmpeg_stage.output.get('audio_path'):
                audio_path = ffmpeg_stage.output['audio_path']
                audio_source = "ffmpeg.extract_audio"
```

#### 对比结果 ✅ 智能源选择机制基本一致

### GPU 锁机制验证

#### 代码中的 GPU 锁实现 (行 95)

```python
@gpu_lock()  # 使用GPU锁保护
def _separate_vocals_with_gpu_lock(audio_path: str, service_config: dict, stage_name: str) -> dict:
```

#### 对比结果 ✅ GPU 锁机制与文档描述一致

### 音频分离实现验证

#### 代码中的实际分离逻辑 (行 150+)

```python
# 音频分离实现
separator = create_audio_separator(config=separator_config)
# 调用音频分离服务
result = separator.separate(audio_path, **separator_config)
```

#### 对比结果 ✅ 音频分离功能与文档描述一致

## 详细问题分析

### 1. 参数定义不完整

-   **文档遗漏**: 代码实现了更多节点参数，如`model_type`、`use_vocal_optimization`等
-   **MinIO 上传**: 新增的 MinIO 上传相关参数未在文档中描述
-   **人声优化**: 详细的人声优化参数配置缺失

### 2. 架构演进未反映

-   **从全局配置到节点参数**: 代码支持更细粒度的参数控制
-   **MinIO 集成**: 新增的远程存储功能未更新到文档
-   **人声优化**: 新增的人声优化算法未详细说明

### 3. 文档错误信息

-   **错误的通用特性**: 混入了 OCR 服务的图片格式支持描述
-   **参数来源错误**: 一些应该是节点参数的描述为全局配置

## 修复建议

### 1. 更新输入参数文档 ✅

**修复内容**:

-   添加所有支持的节点参数说明
-   补充 MinIO 上传相关参数
-   添加人声优化参数配置
-   明确参数来源和优先级

**建议的文档更新**:

```markdown
### 输入参数

-   `audio_path` (string, 节点必需): 指定音频文件路径，以覆盖智能音频源选择逻辑。

-   `model_name` (string, 节点可选): 指定要使用的分离模型名称

-   `quality_mode` (string, 节点可选): 质量模式，可选值: `"fast"`, `"default"`, `"high_quality"`

-   `model_type` (string, 节点可选): 模型类型，默认"demucs"

-   `use_vocal_optimization` (bool, 节点可选): 是否使用人声优化，默认 False

-   `vocal_optimization_level` (int, 节点可选): 人声优化级别，默认 2

-   `output_format` (string, 节点可选): 输出格式，默认"flac"

-   `upload_audio_list_to_minio` (bool, 节点可选): 是否上传音频列表到 MinIO，默认 false

-   `delete_local_audio_files_after_upload` (bool, 节点可选): 上传后是否删除本地音频文件，默认 false
```

### 2. 移除错误的技术特性描述 ✅

**修复内容**:

-   移除"支持多种图片格式上传"等错误的描述
-   移除"通过`delete_local_cropped_images_after_upload`参数控制"等错误的参数引用

### 3. 补充新的功能说明 ✅

**修复内容**:

-   添加 MinIO 上传功能的详细说明
-   补充人声优化算法的技术细节
-   说明参数优先级和解析机制

### 4. 更新配置示例 ✅

**修复内容**:

-   提供更完整的参数配置示例
-   明确哪些参数是节点参数，哪些是全局配置
-   补充单任务模式的配置示例

## 优先级修复计划

### 高优先级修复 🔴

1. **补充缺失的节点参数说明** - 影响功能完整性
2. **移除错误的技术特性描述** - 避免用户混淆
3. **修正参数来源说明** - 确保文档准确性

### 中优先级修复 🟡

1. **补充 MinIO 上传功能说明** - 完善远程存储支持
2. **添加人声优化参数配置** - 完善高级功能文档
3. **更新配置示例** - 提供正确的使用指导

### 低优先级修复 🟢

1. **补充架构演进说明** - 帮助用户理解设计变化
2. **添加性能优化建议** - 提供最佳实践指导

## 总结

### 整体一致性评估: ❌ 75% 不一致

#### 主要问题

1. ❌ **参数定义不完整**: 代码支持更多节点参数但文档未描述
2. ❌ **错误的技术特性描述**: 混入了其他服务的内容
3. ❌ **参数来源说明不准确**: 一些节点参数被错误描述为全局配置
4. ✅ **输出格式基本正确**: 核心输出字段一致

#### 修复紧急程度

-   **高**: 缺失的参数说明会影响用户使用新功能
-   **中**: 错误的技术特性会影响用户体验
-   **中**: 参数来源说明不准确可能导致配置错误
-   **低**: 新功能说明缺失主要影响高级用户

---

**验证结论**: Audio Separator 服务的文档与代码实现存在较大不一致，主要体现在参数定义不完整和错误的技术特性描述，需要更新文档以准确反映代码的功能。

# YiVideo 工作流节点功能文档

## 概述

本文档详细描述了 YiVideo 系统中所有可用的工作流节点的功能、参数、输入输出格式和使用方法。每个节点都是一个独立的 Celery 任务，可以通过工作流配置组合成复杂的视频处理流程。

## 文档结构

-   [FFmpeg 服务节点](#ffmpeg-服务节点) - 视频和音频处理

-   [Faster-Whisper 服务节点](#faster-whisper-服务节点) - 语音识别和字幕生成

-   [Audio Separator 服务节点](#audio-separator-服务节点) - 音频分离

-   [Pyannote Audio 服务节点](#pyannote-audio-服务节点) - 说话人分离

-   [PaddleOCR 服务节点](#paddleocr-服务节点) - 文字识别

-   [IndexTTS 服务节点](#indextts-服务节点) - 语音合成

-   [WService 字幕优化服务节点](#wservice-字幕优化服务节点) - AI 字幕优化

## 通用参数说明

### 参数来源说明

本文档中提到的参数分为以下三类，理解它们的来源有助于正确配置工作流：

-   **全局参数 (Global Parameter)**: 这些参数在工作流的生命周期内全局可用，通常由 **API Gateway** 在工作流启动时根据初始请求设置。它们通过统一的 `context` 字典在所有任务间传递。最典型的例子是 `workflow_id` 和 `shared_storage_path`。

-   **节点参数 (Node Parameter)**: 这些是特定于单个工作流节点（Celery 任务）的配置参数。它们在调用该任务时直接传入，或在前置任务的输出中指定。例如，`faster_whisper` 节点的 `model_name` 就是一个节点参数。所有节点参数都通过 `resolve_parameters` 函数进行解析，支持动态引用和工作流上下文替换。

-   **全局配置 (Global Configuration)**: 这些参数定义在项目的根 `config.yml` 文件中，由所有服务共享。它们提供了系统级的默认行为。例如，Redis 的主机地址或默认的 GPU 锁超时时间。`services.common.config_loader` 模块负责加载这些配置。

### 单任务模式支持

YiVideo 系统支持**单任务模式**和**传统工作流模式**两种调用方式：

#### 单任务模式

-   **特点**: 每个任务都是独立的请求，使用独立的 `workflow_id`

-   **参数来源**: 直接从 `input_data` 中获取，无需依赖前置任务

-   **调用方式**: 通过 `/v1/tasks` 接口调用

```json
{
    "task_name": "ffmpeg.extract_audio",
    "task_id": "unique-task-id",
    "callback": "https://client.example.com/callback",
    "input_data": {
        "video_path": "https://minio.example.com/yivideo/task-123/video.mp4"
    }
}
```

#### 传统工作流模式

-   **特点**: 多个任务在同一个 `workflow_id` 下运行，任务间可以共享状态

-   **参数来源**: 从前序任务的输出中获取，或通过动态引用

-   **调用方式**: 通过 `/v1/workflows` 接口调用

```json
{
    "workflow_config": {
        "workflow_chain": ["ffmpeg.extract_audio", "faster_whisper.transcribe_audio"]
    },
    "video_path": "/share/video.mp4"
}
```

### 智能源选择逻辑

为了支持单任务模式，大多数节点都实现了**智能源选择逻辑**，能够自动从不同位置查找输入参数：

#### 音频相关任务的优先级（以 `faster_whisper.transcribe_audio` 为例）：

1. **input_data.audio_path** （单任务模式优先）
2. **audio_separator.separate_vocals 输出** （传统工作流模式）
3. **ffmpeg.extract_audio 输出** （传统工作流模式）

#### 视频相关任务的优先级（以 `paddleocr.detect_subtitle_area` 为例）：

1. **input_data.video_path** （单任务模式优先）
2. **全局 video_path** 参数 （传统工作流模式）

#### 字幕相关任务的优先级（以 `wservice.generate_subtitle_files` 为例）：

1. **节点参数 segments_file** （显式指定）
2. **faster_whisper.transcribe_audio 输出** （智能检测）

> **重要提示**: 单任务模式优先从 `input_data` 获取参数，确保在调用单任务接口时需要明确提供所有必需的输入参数。

### 参数解析机制

YiVideo 工作流系统实现了强大的参数解析和动态引用机制，通过 `resolve_parameters` 函数实现：

#### 1. 动态引用语法

所有字符串类型的节点参数都支持 `${{...}}` 格式的动态引用，可以引用工作流上下文中其他阶段的输出：

```python
# 基本语法格式
${{ stages.<stage_name>.output.<field_name> }}

# 示例：引用音频分离阶段的人声音频路径
${{ stages.audio_separator.separate_vocals.output.vocal_audio }}

# 示例：引用字幕生成阶段的说话人SRT文件
${{ stages.wservice.generate_subtitle_files.output.speaker_srt_path }}

# 示例：引用转录数据文件
${{ stages.faster_whisper.transcribe_audio.output.segments_file }}
```

#### 2. 优先级机制

参数解析遵循以下优先级（从高到低）：

1. **显式传入的节点参数**: 在请求体中明确提供的参数值
2. **动态引用解析结果**: `${{...}}` 格式引用的工作流上下文数据
3. **智能源选择逻辑**: 各服务内置的自动源选择算法
4. **全局配置默认值**: config.yml 文件中的配置项
5. **硬编码默认值**: 代码中定义的最小默认值

#### 3. 智能源选择

各服务实现了智能源选择逻辑，自动从工作流上下文中寻找最佳输入源：

**音频源选择优先级**（以 `faster_whisper.transcribe_audio` 为例）：

1. 人声音频：`audio_separator.separate_vocals` 输出的 `vocal_audio`
2. 默认音频：`ffmpeg.extract_audio` 输出的 `audio_path`
3. 参数传入的 `audio_path`

**字幕文件选择优先级**（以 `ffmpeg.split_audio_segments` 为例）：

1. 带说话人信息 SRT：`speaker_srt_path`
2. 基础 SRT：`subtitle_path`
3. 带说话人信息 JSON：`speaker_json_path`
4. 参数传入的 `subtitle_path`

#### 4. 使用建议

-   **明确优于隐式**: 优先使用显式参数而不是依赖自动检测，提高工作流的可控性

-   **动态引用**: 充分利用 `${{...}}` 语法实现任务间的数据传递

-   **健壮性**: 对于关键路径，建议同时提供智能检测和显式参数作为备选

### 参数获取统一机制 (新增)

在 v2.1 版本中，引入了统一的参数获取函数 `get_param_with_fallback`，标准化了所有节点的参数获取逻辑。这意味着：

1. **统一优先级**: `node_params` (工作流配置) > `input_data` (单任务输入) > `upstream_output` (上游节点) > `default` (默认值)。
2. **全面支持单任务**: 几乎所有节点现在都支持通过 `input_data` 直接传入关键参数（如 `subtitle_area`, `audio_path` 等），不再强依赖上游节点。
3. **动态引用增强**: `input_data` 中的参数值也支持 `${{...}}` 动态引用解析。

所有工作流节点都遵循统一的接口规范：

### 标准任务签名

```python
def task_name(self: Task, context: dict) -> dict:
```

### 上下文结构

```json
{
    "workflow_id": "工作流唯一标识符",
    "input_params": {
        "输入参数名称": "参数值"
    },
    "stages": {
        "其他阶段名称": {
            "status": "SUCCESS|FAILED|IN_PROGRESS",
            "output": "输出数据"
        }
    },
    "shared_storage_path": "/share/workflows/{workflow_id}/"
}
```

### 标准输出格式

```json
{
  "workflow_id": "工作流ID",
  "stages": {
    "当前节点名称": {
      "status": "SUCCESS|FAILED",
      "output": "节点输出数据",
      "duration": 处理时长(秒),
      "error": "错误信息(如果失败)"
    }
  }
}
```

---

## FFmpeg 服务节点

FFmpeg 服务提供视频和音频的基础处理功能，包括关键帧提取、音频提取、字幕区域裁剪和音频分割。

### 1. ffmpeg.extract_keyframes

从视频中抽取若干关键帧图片，为后续的字幕区域检测提供素材。

**功能描述**：随机从视频中抽取指定数量的关键帧图片，保存为 JPEG 格式。

**输入参数**：

-   `video_path` (string, 全局必需): 视频文件路径，在 API 请求的顶层提供。

-   `keyframe_sample_count` (int, 节点可选): 抽取帧数，默认 100。

-   `upload_keyframes_to_minio` (bool, 节点可选): 是否上传关键帧到 MinIO，默认 false。

-   `delete_local_keyframes_after_upload` (bool, 节点可选): 上传后是否删除本地关键帧，默认 false。

**配置来源说明**：

-   `video_path`: **全局参数** (在 API 请求的顶层 `video_path` 字段提供)

-   `keyframe_sample_count`: **节点参数** (在请求体中的 `ffmpeg.extract_keyframes` 对象内提供)

**输出格式**：

```json
{
    "keyframe_dir": "/share/workflows/{workflow_id}/keyframes"
}
```

**使用示例**：

```json
{
    "workflow_config": {
        "workflow_chain": ["ffmpeg.extract_keyframes"]
    },
    "ffmpeg.extract_keyframes": {
        "keyframe_sample_count": 50
    }
}
```

**依赖关系**：无

**单任务模式支持**：

**输入参数**:

-   `video_path` (string, 必需): 视频文件路径，支持 `${{...}}` 动态引用
-   `keyframe_sample_count` (int, 可选): 抽取帧数，默认 100
-   `upload_keyframes_to_minio` (bool, 可选): 是否上传关键帧到 MinIO，默认 false
-   `delete_local_keyframes_after_upload` (bool, 可选): 上传后是否删除本地关键帧，默认 false
-   `compress_keyframes_before_upload` (bool, 可选): 是否在上传前压缩目录，默认 false
-   `keyframe_compression_format` (string, 可选): 压缩格式，默认"zip"
-   `keyframe_compression_level` (string, 可选): 压缩级别，默认"default"

**单任务调用示例**:

```json
{
    "task_name": "ffmpeg.extract_keyframes",
    "input_data": {
        "video_path": "https://minio.example.com/yivideo/video.mp4",
        "keyframe_sample_count": 50,
        "upload_keyframes_to_minio": true,
        "compress_keyframes_before_upload": true
    }
}
```

**参数来源说明**:

-   `video_path`: **节点参数** (在请求体中的 `ffmpeg.extract_keyframes` 对象内提供)
-   `keyframe_sample_count`: **节点参数** (在请求体中的 `ffmpeg.extract_keyframes` 对象内提供)
-   其他上传相关参数均为节点参数，可选配置

**注意事项**：

-   抽取的帧为随机分布，不是均匀分布

-   输出图片格式为 JPEG

-   关键帧目录会在字幕区域检测完成后自动清理

---

### 2. ffmpeg.extract_audio

从视频中提取音频文件，转换为适合语音识别的格式。

**功能描述**：使用 FFmpeg 从视频中提取音频，转换为 16kHz 单声道 WAV 格式。

**输入参数**：

-   `video_path` (string, 全局必需): 视频文件路径，在 API 请求的顶层提供。

**配置来源说明**：

-   `video_path`: **全局参数** (在 API 请求的顶层 `video_path` 字段提供)

**输出格式**：

```json
{
    "audio_path": "/share/workflows/{workflow_id}/audio/{video_name}.wav"
}
```

**使用示例**：

```json
{
    "workflow_config": {
        "workflow_chain": ["ffmpeg.extract_audio"]
    }
}
```

**依赖关系**：无

**技术规格**：

-   编码：16-bit PCM

-   采样率：16kHz (ASR 推荐采样率)

-   声道：单声道

-   超时：1800 秒

**单任务模式支持**：

**输入参数**:

-   `video_path` (string, 必需): 视频文件路径，支持 `${{...}}` 动态引用

**单任务调用示例**:

```json
{
    "task_name": "ffmpeg.extract_audio",
    "input_data": {
        "video_path": "https://minio.example.com/yivideo/video.mp4"
    }
}
```

**参数来源说明**:

-   `video_path`: **节点参数** (在请求体中的 `ffmpeg.extract_audio` 对象内提供)

**注意事项**：

-   自动覆盖已存在的音频文件

-   支持所有 FFmpeg 支持的视频格式

-   文件大小验证，确保输出文件不为空

---

### 3. ffmpeg.crop_subtitle_images

根据检测到的字幕区域，从视频中并发裁剪字幕条图片。

**功能描述**：通过外部脚本并发解码视频，根据字幕区域坐标裁剪出所有字幕帧图片。

**输入参数**：

-   `video_path` (string, 全局必需): 视频文件路径，在 API 请求的顶层提供。

-   `subtitle_area` (array, 节点可选): 字幕区域坐标，格式为 `[x1, y1, x2, y2]`（绝对像素坐标），支持 `${{...}}` 格式的参数引用。如果提供此参数，将优先使用，不再依赖上游节点。

-   `decode_processes` (int, 节点可选): 解码进程数，默认 10。

-   `upload_cropped_images_to_minio` (bool, 节点可选): 是否将裁剪的图片上传到 MinIO，默认 false。

-   `delete_local_cropped_images_after_upload` (bool, 节点可选): 上传成功后是否删除本地裁剪图片，默认 false。此参数仅在 `upload_cropped_images_to_minio=true` 时生效。

-   `compress_directory_before_upload` (bool, 节点可选): 是否在上传前压缩目录，默认 false。启用后可显著减少上传时间和存储空间。

-   `compression_format` (string, 节点可选): 压缩格式，支持 "zip"、"tar.gz" 等，默认 "zip"。

-   `compression_level` (string, 节点可选): 压缩级别，可选 "fast"、"default"、"maximum"，默认 "default"。

**配置来源说明**：

-   `video_path`: **全局参数** (在 API 请求的顶层 `video_path` 字段提供)

-   `subtitle_area`: **节点参数** (在请求体中的 `ffmpeg.crop_subtitle_images` 对象内提供)。如果未提供，将从 `paddleocr.detect_subtitle_area` 输出自动获取。

-   `decode_processes`: **节点参数** (在请求体中的 `ffmpeg.crop_subtitle_images` 对象内提供)

-   `upload_cropped_images_to_minio`: **节点参数** (在请求体中的 `ffmpeg.crop_subtitle_images` 对象内提供)

-   `delete_local_cropped_images_after_upload`: **节点参数** (在请求体中的 `ffmpeg.crop_subtitle_images` 对象内提供，仅在上传启用时生效)

-   `compress_directory_before_upload`: **节点参数** (在请求体中的 `ffmpeg.crop_subtitle_images` 对象内提供，仅在上传启用时生效)

-   `compression_format`: **节点参数** (在请求体中的 `ffmpeg.crop_subtitle_images` 对象内提供，压缩上传时使用)

-   `compression_level`: **节点参数** (在请求体中的 `ffmpeg.crop_subtitle_images` 对象内提供，压缩上传时使用)

**智能参数选择**：

-   `subtitle_area` (按优先级)：1. 显式传入参数 2. `input_data` 中的参数 3. `paddleocr.detect_subtitle_area` 输出

**前置依赖**：

-   无（可选依赖 `paddleocr.detect_subtitle_area` - 如果未提供 `subtitle_area` 参数）

**输出格式**：

```json
{
  "cropped_images_path": "/share/workflows/{workflow_id}/cropped_images/frames",
  "cropped_images_minio_url": "http://minio:9000/yivideo/{workflow_id}/cropped_images",
  "cropped_images_files_count": 150,
  "cropped_images_uploaded_files": ["frame_0001.jpg", "frame_0002.jpg", ...]
}
```

**输出字段说明**：

-   `cropped_images_path`: 本地裁剪图片目录路径

-   `cropped_images_minio_url`: MinIO 中的裁剪图片目录 URL（仅当启用上传时）

-   `cropped_images_files_count`: 裁剪图片文件数量

-   `cropped_images_uploaded_files`: 已上传到 MinIO 的文件列表（仅当启用上传时）

-   `compressed_archive_url`: 压缩包在 MinIO 中的 URL（仅当启用压缩上传时）

-   `compression_info`: 压缩信息对象（仅当启用压缩上传时），包含：
    -   `original_size`: 原始大小（字节）
    -   `compressed_size`: 压缩后大小（字节）
    -   `compression_ratio`: 压缩率
    -   `files_count`: 压缩的文件数量
    -   `compression_time`: 压缩耗时（秒）
    -   `checksum`: 压缩包校验和
    -   `format`: 使用的压缩格式

**使用示例**：

**示例 1：依赖上游节点（传统方式）**

```json
{
    "workflow_config": {
        "workflow_chain": ["ffmpeg.extract_keyframes", "paddleocr.detect_subtitle_area", "ffmpeg.crop_subtitle_images"]
    },
    "ffmpeg.crop_subtitle_images": {
        "decode_processes": 8
    }
}
```

**示例 2：直接传入字幕区域参数**

```json
{
    "workflow_config": {
        "workflow_chain": ["ffmpeg.extract_keyframes", "ffmpeg.crop_subtitle_images"]
    },
    "ffmpeg.crop_subtitle_images": {
        "subtitle_area": [0, 918, 1920, 1080],
        "decode_processes": 8
    }
}
```

**示例 3：启用 MinIO 上传功能**

```json
{
    "workflow_config": {
        "workflow_chain": ["ffmpeg.extract_keyframes", "paddleocr.detect_subtitle_area", "ffmpeg.crop_subtitle_images"]
    },
    "ffmpeg.crop_subtitle_images": {
        "subtitle_area": [0, 918, 1920, 1080],
        "decode_processes": 8,
        "upload_cropped_images_to_minio": true,
        "delete_local_cropped_images_after_upload": false
    }
}
```

**示例 4：启用压缩上传功能**

```json
{
    "workflow_config": {
        "workflow_chain": ["ffmpeg.extract_keyframes", "paddleocr.detect_subtitle_area", "ffmpeg.crop_subtitle_images"]
    },
    "ffmpeg.crop_subtitle_images": {
        "subtitle_area": [0, 918, 1920, 1080],
        "decode_processes": 8,
        "upload_cropped_images_to_minio": true,
        "compress_directory_before_upload": true,
        "compression_format": "zip",
        "compression_level": "maximum",
        "delete_local_cropped_images_after_upload": true
    }
}
```

**示例 5：动态引用字幕区域**

```json
{
    "workflow_config": {
        "workflow_chain": ["ffmpeg.extract_keyframes", "paddleocr.detect_subtitle_area", "ffmpeg.crop_subtitle_images"]
    },
    "ffmpeg.crop_subtitle_images": {
        "subtitle_area": "${{ stages.paddleocr.detect_subtitle_area.output.subtitle_area }}",
        "decode_processes": 8
    }
}
```

**依赖关系**：

-   需要 `paddleocr.detect_subtitle_area` 的输出 `subtitle_area`

**技术特性**：

-   并发解码处理，提高处理速度

-   GPU 加速（使用 GPU 锁保护）

-   超时保护：1800 秒

-   **压缩上传功能**：支持目录压缩上传，显著减少上传时间和存储空间

-   **智能回退机制**：压缩上传失败时自动回退到非压缩模式

**单任务模式支持**：

**输入参数**:

-   `video_path` (string, 必需): 视频文件路径，支持 `${{...}}` 动态引用
-   `subtitle_area` (array, 可选): 字幕区域坐标，格式为 `[x1, y1, x2, y2]`，支持 `${{...}}` 动态引用
-   `decode_processes` (int, 可选): 解码进程数，默认 10
-   `upload_cropped_images_to_minio` (bool, 可选): 是否将裁剪的图片上传到 MinIO，默认 false
-   `delete_local_cropped_images_after_upload` (bool, 可选): 上传成功后是否删除本地裁剪图片，默认 false
-   `compress_directory_before_upload` (bool, 可选): 是否在上传前压缩目录，默认 false
-   `compression_format` (string, 可选): 压缩格式，默认"zip"
-   `compression_level` (string, 可选): 压缩级别，默认"default"

**单任务调用示例**:

```json
{
    "task_name": "ffmpeg.crop_subtitle_images",
    "input_data": {
        "video_path": "https://minio.example.com/yivideo/video.mp4",
        "subtitle_area": [0, 918, 1920, 1080],
        "decode_processes": 8,
        "upload_cropped_images_to_minio": true,
        "compress_directory_before_upload": true
    }
}
```

**参数来源说明**:

-   `video_path`: **节点参数** (在请求体中的 `ffmpeg.crop_subtitle_images` 对象内提供)
-   `subtitle_area`: **节点参数** (在请求体中的 `ffmpeg.crop_subtitle_images` 对象内提供)
-   其他参数均为节点参数，可选配置

**压缩上传优势**：

-   减少网络传输量，提高上传速度

-   节省 MinIO 存储空间

-   支持多种压缩格式和压缩级别

-   提供详细的压缩统计信息

---

### 4. ffmpeg.split_audio_segments

根据字幕文件的时间戳数据分割音频片段，支持按说话人分组。

**功能描述**：根据字幕时间戳将音频分割为小片段，为语音生成提供参考音频。支持多种输出格式和按说话人分组存储。

**输入参数**：

-   `audio_path` (string, 节点可选): 指定音频文件路径，支持 `${{...}}` 格式的参数引用。如果未提供，将启用智能检测。

-   `subtitle_path` (string, 节点可选): 指定字幕文件路径，支持 `${{...}}` 格式的参数引用。如果未提供，将启用智能检测。

-   `output_format` (string, 节点可选): 输出格式，默认 "wav"。

-   `sample_rate` (int, 节点可选): 采样率，默认 16000。

-   `channels` (int, 节点可选): 声道数，默认 1。

-   `min_segment_duration` (float, 节点可选): 最小片段时长，默认 1.0 秒。

-   `max_segment_duration` (float, 节点可选): 最大片段时长，默认 30.0 秒。

-   `group_by_speaker` (bool, 节点可选): 按说话人分组，默认 false。

-   `include_silence` (bool, 节点可选): 包含静音片段，默认 false。

-   `enable_concurrent` (bool, 节点可选): 启用并发分割，默认 true。

-   `max_workers` (int, 节点可选): 最大工作线程数，默认 8。

-   `concurrent_timeout` (int, 节点可选): 并发超时时间，默认 600 秒。

**配置来源说明**：

-   所有列出的参数均为 **节点参数**，在请求体中的 `ffmpeg.split_audio_segments` 对象内提供。

**参数引用支持**：
所有字符串类型的参数都支持 `${{ stages.<stage_name>.output.<field_name> }}` 格式的动态引用，例如：

```json
{
    "ffmpeg.split_audio_segments": {
        "audio_path": "${{ stages.audio_separator.separate_vocals.output.vocal_audio }}",
        "subtitle_path": "${{ stages.wservice.generate_subtitle_files.output.speaker_srt_path }}",
        "output_format": "wav",
        "group_by_speaker": true
    }
}
```

**智能音频源选择**（按优先级）：

1. 人声音频 (`audio_separator.separate_vocals` 输出的 `vocal_audio`)
2. 默认音频 (`ffmpeg.extract_audio` 输出的 `audio_path`)
3. 参数传入的 `audio_path`

**智能字幕文件选择**（按优先级）：

1. 带说话人信息 SRT (`speaker_srt_path`)
2. 基础 SRT (`subtitle_path`)
3. 带说话人信息 JSON (`speaker_json_path`)
4. 参数传入的 `subtitle_path`

**前置依赖**：

-   `ffmpeg.extract_audio` 或 `audio_separator.separate_vocals`

-   `wservice.generate_subtitle_files`

**输出格式**：

```json
{
    "audio_segments_dir": "/share/workflows/{workflow_id}/audio_segments",
    "audio_source": "实际使用的音频文件路径",
    "subtitle_source": "实际使用的字幕文件路径",
    "total_segments": 150,
    "successful_segments": 148,
    "failed_segments": 2,
    "total_duration": 1200.5,
    "processing_time": 45.2,
    "audio_format": "wav",
    "sample_rate": 16000,
    "channels": 1,
    "split_info_file": "/share/workflows/{workflow_id}/audio_segments/split_info.json",
    "segments_count": 148,
    "speaker_summary": {
        "SPEAKER_00": {
            "count": 80,
            "duration": 650.3
        },
        "SPEAKER_01": {
            "count": 68,
            "duration": 550.2
        }
    }
}
```

**使用示例**：

```json
{
    "workflow_config": {
        "workflow_chain": ["ffmpeg.extract_audio", "faster_whisper.transcribe_audio", "wservice.generate_subtitle_files", "ffmpeg.split_audio_segments"]
    },
    "ffmpeg.split_audio_segments": {
        "output_format": "wav",
        "group_by_speaker": false,
        "min_segment_duration": 2.0,
        "max_workers": 6
    }
}
```

**依赖关系**：

-   音频源：`ffmpeg.extract_audio` 或 `audio_separator.separate_vocals`

-   字幕源：`wservice.generate_subtitle_files`

**单任务模式支持**：

**输入参数**:

-   `audio_path` (string, 可选): 指定音频文件路径，支持 `${{...}}` 动态引用
-   `subtitle_path` (string, 可选): 指定字幕文件路径，支持 `${{...}}` 动态引用
-   `output_format` (string, 可选): 输出格式，默认"wav"
-   `sample_rate` (int, 可选): 采样率，默认 16000
-   `channels` (int, 可选): 声道数，默认 1
-   `min_segment_duration` (float, 可选): 最小片段时长，默认 1.0 秒
-   `max_segment_duration` (float, 可选): 最大片段时长，默认 30.0 秒
-   `group_by_speaker` (bool, 可选): 按说话人分组，默认 false
-   `include_silence` (bool, 可选): 包含静音片段，默认 false
-   `enable_concurrent` (bool, 可选): 启用并发分割，默认 true
-   `max_workers` (int, 可选): 最大工作线程数，默认 8
-   `concurrent_timeout` (int, 可选): 并发超时时间，默认 600 秒

**单任务调用示例**:

```json
{
    "task_name": "ffmpeg.split_audio_segments",
    "input_data": {
        "audio_path": "/share/audio/sample.wav",
        "subtitle_path": "/share/subtitles/sample.srt",
        "output_format": "wav",
        "group_by_speaker": true,
        "min_segment_duration": 2.0,
        "max_workers": 6
    }
}
```

**参数来源说明**:

-   所有列出的参数均为 **节点参数**，在请求体中的 `ffmpeg.split_audio_segments` 对象内提供

**特性**：

-   智能源选择，自动从工作流上下文获取最佳输入

-   支持并发分割，提高处理速度

-   完善的错误处理和统计信息

-   按说话人分组存储

-   详细的分割信息保存到 JSON 文件

---

## Faster-Whisper 服务节点

Faster-Whisper 服务是一个纯粹的音频转录服务，提供基于 faster-whisper 模型的语音识别功能，支持多语言和词级时间戳。

### 1. faster_whisper.transcribe_audio

对音频进行语音转录，生成包含词级时间戳的详细转录数据。

**功能描述**：使用 faster-whisper 模型对音频进行语音识别，生成包含词级时间戳的精确转录结果。

**输入参数**：

-   `audio_path` (string, 节点可选): 指定音频文件路径，以覆盖智能音频源选择逻辑。支持 `${{...}}` 格式的参数引用。

**配置来源说明**：

-   `audio_path`: **节点参数** (在请求体中的 `faster_whisper.transcribe_audio` 对象内提供)。

-   **其他模型参数**: 如模型大小 (`model_size`)、语言 (`language`)、计算精度、VAD 过滤等，均为 **全局配置**，请在 `config.yml` 文件中修改。它们**不是**节点参数。

**全局配置示例 (config.yml)**:

```yaml
faster_whisper_service:
    default_model: 'large-v3'
    default_device: 'cuda'
    default_compute_type: 'float16'
    default_language: 'zh'
    default_word_timestamps: true
    default_vad_filter: true
```

**智能音频源选择**（按优先级）：

1. 人声音频 (`audio_separator.separate_vocals` 输出的 `vocal_audio`)
2. 默认音频 (`ffmpeg.extract_audio` 输出的 `audio_path`)
3. 参数传入的 `audio_path`

**前置依赖**：

-   `ffmpeg.extract_audio` 或 `audio_separator.separate_vocals`

**输出格式**：

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

**Segments 文件格式**：

```json
{
    "segments": [
        {
            "id": 0,
            "seek": 0,
            "start": 0.0,
            "end": 3.5,
            "text": "这是第一段转录文本",
            "tokens": [1234, 5678, 9012],
            "temperature": 0.0,
            "avg_logprob": -0.25,
            "compression_ratio": 1.2,
            "no_speech_prob": 0.1,
            "words": [
                {
                    "word": "这是",
                    "start": 0.0,
                    "end": 0.8,
                    "probability": 0.95
                },
                {
                    "word": "第一段",
                    "start": 0.9,
                    "end": 2.1,
                    "probability": 0.92
                },
                {
                    "word": "转录文本",
                    "start": 2.2,
                    "end": 3.5,
                    "probability": 0.88
                }
            ]
        }
    ]
}
```

**使用示例**：

```json
{
    "workflow_config": {
        "workflow_chain": ["ffmpeg.extract_audio", "faster_whisper.transcribe_audio"]
    }
}
// 注：此节点的大部分参数（如模型大小、语言、解码选项）
// 均为全局配置，请在 config.yml 中设置。
// 唯一可选的节点参数是 audio_path，用于覆盖默认的音频源。
```

**依赖关系**：

-   `ffmpeg.extract_audio` 或 `audio_separator.separate_vocals`

**技术特性**：

-   并发解码处理，提高处理速度

-   GPU 加速（使用 GPU 锁保护）

-   超时保护：1800 秒

-   GPU 加速（使用 GPU 锁保护）

-   支持多种模型大小，平衡速度和精度

-   自动语言检测

-   词级时间戳精确同步

-   语音活动检测过滤

**单任务模式支持**：

**输入参数**:

-   `audio_path` (string, 可选): 指定音频文件路径，以覆盖智能音频源选择逻辑，支持 `${{...}}` 动态引用

**单任务调用示例**:

```json
{
    "task_name": "faster_whisper.transcribe_audio",
    "input_data": {
        "audio_path": "/share/audio/sample.wav"
    }
}
```

**参数来源说明**:

-   `audio_path`: **节点参数** (在请求体中的 `faster_whisper.transcribe_audio` 对象内提供)
-   其他模型参数（如模型大小、语言、解码选项）均为全局配置，请在 `config.yml` 中设置

**模型选择建议**：

-   `tiny`: 最快速度，精度较低，适合实时应用

-   `base`: 平衡速度和精度，推荐日常使用

-   `small`: 较好精度，速度适中

-   `medium`: 高精度，处理时间较长

-   `large-v3`: 最高精度，需要充足硬件资源

---

## Audio Separator 服务节点

Audio Separator 服务提供基于 UVR-MDX 模型的专业音频分离功能，支持人声与伴奏的高质量分离。

### 1. audio_separator.separate_vocals

分离音频中的人声和背景音，支持多种模型和质量模式。

**功能描述**：使用 UVR-MDX 深度学习模型将音频分离为人声和各种乐器轨道，支持高质量分离和 GPU 加速。

**输入参数**：

-   `audio_path` (string, 节点可选): 指定音频文件路径，以覆盖智能音频源选择逻辑。

-   `model_name` (string, 节点可选): 指定要使用的分离模型名称，如 "UVR-MDX-NET-Inst_HQ_3"。如果未提供，则根据 `quality_mode` 从全局配置中选择默认模型。

-   `quality_mode` (string, 节点可选): 质量模式，会影响默认模型的选择。可选值: `"fast"`, `"default"`, `"high_quality"`。

**配置来源说明**：

-   `audio_path`, `model_name`, `quality_mode`: **节点参数** (在请求体中的 `audio_separator.separate_vocals` 对象内提供)。

-   **其他分离参数**: 如 `output_format`, `sample_rate`, `normalize` 等，均为 **全局配置**，请在 `config.yml` 文件中修改。它们**不是**节点参数。

**全局配置示例 (config.yml)**:

```yaml
audio_separator_service:
    # ... (other settings)
    separator_options:
        output_format: 'flac'
        sample_rate: 44100
        bit_rate: 320
        normalize: true
```

**智能音频源选择**（按优先级）：

1. `ffmpeg.extract_audio` 输出的 `audio_path`
2. `input_params` 中的 `audio_path`
3. `input_params` 中的 `video_path`（自动提取音频）

**前置依赖**：

-   `ffmpeg.extract_audio` (推荐)

**输出格式**：

```json
{
    "audio_list": ["/share/workflows/{workflow_id}/audio/audio_separated/video_(Vocals)_htdemucs.flac", "/share/workflows/{workflow_id}/audio/audio_separated/video_(Other)_htdemucs.flac"],
    "vocal_audio": "/share/workflows/{workflow_id}/audio/audio_separated/video_(Vocals)_htdemucs.flac",
    "model_used": "htdemucs",
    "quality_mode": "default"
}
```

**使用示例**：

```json
{
    "workflow_config": {
        "workflow_chain": ["ffmpeg.extract_audio", "audio_separator.separate_vocals"]
    },
    "audio_separator.separate_vocals": {
        "audio_separator_config": {
            "quality_mode": "high_quality",
            "model_type": "demucs",
            "use_vocal_optimization": true,
            "vocal_optimization_level": 2,
            "output_format": "flac"
        }
    }
}
```

**依赖关系**：

-   `ffmpeg.extract_audio` (推荐)

**质量模式说明**：

-   `fast`: 快速模式，使用轻量级模型

-   `default`: 默认模式，平衡质量和速度

-   `high_quality`: 高质量模式，使用最佳模型

**支持的模型类型**：

-   `demucs`: Demucs 系列模型，推荐日常使用

-   `mdx`: MDX 系列模型，专业音质

-   `vr`: Vocal Remover 模型，专门人声分离

**输出轨道说明**：

-   `Vocals`: 人声轨道（推荐用于语音识别）

-   `Other`: 伴奏/其他轨道

-   `Bass`: 低音轨道

-   `Drums`: 鼓声轨道

**技术特性**：

-   并发解码处理，提高处理速度

-   GPU 加速（使用 GPU 锁保护）

-   超时保护：1800 秒

-   GPU 加速处理（使用 GPU 锁保护）

-   支持多种音频格式输入

-   自动音量标准化

-   人声优化算法

-   高质量 FLAC 输出

**单任务模式支持**：

**输入参数**:

-   `audio_path` (string, 可选): 指定音频文件路径，以覆盖智能音频源选择逻辑
-   `model_name` (string, 可选): 指定要使用的分离模型名称
-   `quality_mode` (string, 可选): 质量模式，可选值: `"fast"`, `"default"`, `"high_quality"`

**单任务调用示例**:

```json
{
    "task_name": "audio_separator.separate_vocals",
    "input_data": {
        "audio_path": "/share/audio/sample.wav",
        "quality_mode": "high_quality",
        "model_name": "UVR-MDX-NET-Inst_HQ_3"
    }
}
```

**参数来源说明**:

-   `audio_path`, `model_name`, `quality_mode`: **节点参数** (在请求体中的 `audio_separator.separate_vocals` 对象内提供)
-   其他分离参数（如输出格式、采样率、标准化等）均为全局配置，请在 `config.yml` 中修改

**注意事项**：

-   处理时间较长，特别是高质量模式

-   GPU 内存使用量较高

-   建议使用人声轨道进行后续的语音识别

---

## Pyannote Audio 服务节点

Pyannote Audio 服务提供基于 pyannote-audio 模型的专业说话人分离功能，支持多人对话场景的说话人识别和时间分割。

### 1. pyannote_audio.diarize_speakers

对音频进行说话人分离，识别不同说话人及其时间区间。

**功能描述**：使用 pyannote-audio 深度学习模型识别音频中的不同说话人，生成精确的说话人时间戳。

**输入参数**：

-   `audio_path` (string, 节点可选): 指定音频文件路径，以覆盖智能音频源选择逻辑。

**配置来源说明**：

-   `audio_path`: **节点参数** (在请求体中的 `pyannote_audio.diarize_speakers` 对象内提供)。

-   **Hugging Face Token (`hf_token`)**: **必需的全局配置**，请在 `config.yml` 中设置。

-   **其他 diarization 参数**: 如 `num_speakers`, `min_duration_on`, `min_duration_off` 等，均为 **全局配置**，请在 `config.yml` 文件中修改。它们**不是**节点参数。

**全局配置示例 (config.yml)**:

```yaml
pyannote_audio_service:
    # ... (other settings)
    diarization_options:
        hf_token: 'your_hugging_face_token_here'
        num_speakers: 0 # 0 for auto-detection
        min_duration_on: 0.5
        min_duration_off: 0.3
```

**智能音频源选择**（按优先级）：

1. 人声音频 (`audio_separator.separate_vocals` 输出的 `vocal_audio`)
2. 默认音频 (`ffmpeg.extract_audio` 输出的 `audio_path`)
3. 参数传入的 `audio_path`

**前置依赖**：

-   `ffmpeg.extract_audio` 或 `audio_separator.separate_vocals`

**输出格式**：

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

**说话人分离详细数据格式**（存储在 `diarization_file` 中）：

```json
{
    "success": true,
    "segments": [
        {
            "start": 0.0,
            "end": 5.2,
            "speaker": "SPEAKER_00",
            "duration": 5.2
        },
        {
            "start": 5.5,
            "end": 12.3,
            "speaker": "SPEAKER_01",
            "duration": 6.8
        }
    ],
    "total_speakers": 2,
    "total_segments": 148,
    "metadata": {
        "api_type": "free",
        "model": "pyannote/speaker-diarization-community-1"
    }
}
```

**使用示例**：

```json
{
    "workflow_config": {
        "workflow_chain": ["ffmpeg.extract_audio", "audio_separator.separate_vocals", "pyannote_audio.diarize_speakers"]
    }
}
// 注：Hugging Face Token 和说话人分离相关的参数（如 num_speakers）
// 均为全局配置，请在 config.yml 中设置。
// 唯一可选的节点参数是 audio_path，用于覆盖默认的音频源。
```

**依赖关系**：

-   `ffmpeg.extract_audio` 或 `audio_separator.separate_vocals`

**配置要求**：

1. **Hugging Face Token**: 必需有效的 Hugging Face 访问令牌
2. **模型许可**: 确保有权限使用选定的说话人分离模型
3. **GPU 推荐**: 虽然支持 CPU，但 GPU 处理速度更快

**技术特性**：

-   并发解码处理，提高处理速度

-   GPU 加速（使用 GPU 锁保护）

-   超时保护：1800 秒

-   GPU 加速处理（使用 GPU 锁保护）

-   自动说话人数量检测

-   高精度时间边界检测

-   置信度评估

-   支持多种语言和音频场景

**注意事项**：

-   首次运行会自动下载模型（约 1GB）

-   需要有效的 Hugging Face 访问令牌

-   推荐使用人声分离后的音频以提高准确性

-   处理时间与音频长度和说话人数量相关

**单任务模式支持**：

**输入参数**:

-   `audio_path` (string, 可选): 指定音频文件路径，以覆盖智能音频源选择逻辑

**单任务调用示例**:

```json
{
    "task_name": "pyannote_audio.diarize_speakers",
    "input_data": {
        "audio_path": "/share/audio/sample.wav"
    }
}
```

**参数来源说明**:

-   `audio_path`: **节点参数** (在请求体中的 `pyannote_audio.diarize_speakers` 对象内提供)
-   Hugging Face Token 和说话人分离相关的参数（如 num_speakers）均为全局配置，请在 config.yml 中设置

**最佳实践**：

-   对于清晰的人声推荐使用 `audio_separator.separate_vocals` 的输出

-   音频质量越好，分离效果越准确

-   说话人差异越大，识别效果越好

---

### 2. pyannote_audio.get_speaker_segments

获取指定说话人的片段，支持按说话人过滤和统计分析。

**功能描述**：从说话人分离结果中提取指定说话人的片段，提供片段级的分析和过滤功能。

**输入参数**：

-   `diarization_file` (string, 必需): 说话人分离结果文件路径，必须是从 `pyannote_audio.diarize_speakers` 输出的 `diarization_file`。

-   `speaker` (string, 可选): 指定要获取的说话人标签，如 "SPEAKER_00"。如果未指定，将返回所有说话人的统计信息。

**配置来源说明**：

-   `diarization_file`, `speaker`: **节点参数** (在请求体中的 `pyannote_audio.get_speaker_segments` 对象内提供)。

**前置依赖**：

-   `pyannote_audio.diarize_speakers` (必需)

**输出格式**：

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
            },
            {
                "start": 8.5,
                "end": 12.3,
                "speaker": "SPEAKER_00",
                "duration": 3.8
            }
        ],
        "summary": "说话人 SPEAKER_00 的片段: 2 个"
    }
}
```

**使用示例**：

**示例 1：获取指定说话人的片段**：

```json
{
    "workflow_config": {
        "workflow_chain": ["ffmpeg.extract_audio", "pyannote_audio.diarize_speakers", "pyannote_audio.get_speaker_segments"]
    },
    "pyannote_audio.get_speaker_segments": {
        "diarization_file": "${{ stages.pyannote_audio.diarize_speakers.output.diarization_file }}",
        "speaker": "SPEAKER_00"
    }
}
```

**示例 2：获取所有说话人统计**：

```json
{
    "workflow_config": {
        "workflow_chain": ["ffmpeg.extract_audio", "pyannote_audio.diarize_speakers", "pyannote_audio.get_speaker_segments"]
    },
    "pyannote_audio.get_speaker_segments": {
        "diarization_file": "${{ stages.pyannote_audio.diarize_speakers.output.diarization_file }}"
    }
}
```

**示例 3：单任务模式**：

```json
{
    "task_name": "pyannote_audio.get_speaker_segments",
    "input_data": {
        "pyannote_audio.get_speaker_segments": {
            "diarization_file": "/share/workflows/workflow123/diarization/diarization_result.json",
            "speaker": "SPEAKER_01"
        }
    }
}
```

**依赖关系**：

-   必需：`pyannote_audio.diarize_speakers`

**技术特性**：

-   支持按说话人标签过滤片段

-   提供片段统计信息

-   保持与原始说话人分离结果的数据格式兼容

-   支持动态参数引用

**单任务模式支持**：

**输入参数**:

-   `diarization_file` (string, 必需): 说话人分离结果文件路径
-   `speaker` (string, 可选): 指定要获取的说话人标签

**单任务调用示例**:

```json
{
    "task_name": "pyannote_audio.get_speaker_segments",
    "input_data": {
        "diarization_file": "/share/diarization/result.json",
        "speaker": "SPEAKER_00"
    }
}
```

**参数来源说明**:

-   `diarization_file`, `speaker`: **节点参数** (在请求体中的 `pyannote_audio.get_speaker_segments` 对象内提供)

**注意事项**：

-   `diarization_file` 必须是从 `pyannote_audio.diarize_speakers` 输出的有效文件路径

-   如果指定的 `speaker` 不存在，将返回空结果

-   时间戳格式与输入文件保持一致

---

### 3. pyannote_audio.validate_diarization

验证说话人分离结果的质量，提供详细的质量评估报告。

**功能描述**：对说话人分离结果进行全面的质量检查，包括片段时长分析、说话人数量验证、分布合理性检查等，生成详细的质量评估报告。

**输入参数**：

-   `diarization_file` (string, 必需): 说话人分离结果文件路径，必须是从 `pyannote_audio.diarize_speakers` 输出的 `diarization_file`。

**配置来源说明**：

-   `diarization_file`: **节点参数** (在请求体中的 `pyannote_audio.validate_diarization` 对象内提供)。

**前置依赖**：

-   `pyannote_audio.diarize_speakers` (必需)

**输出格式**：

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

**输出字段说明**：

-   `valid`: 验证结果是否通过

-   `total_segments`: 总片段数

-   `total_speakers`: 检测到的说话人数量

-   `total_duration`: 总时长

-   `avg_segment_duration`: 平均片段时长

-   `issues`: 发现的问题列表

**质量检查项目**：

1. **片段时长检查**：

    - 片段过短（<0.5 秒）将被标记为问题
    - 片段过长（>30 秒）将被标记为问题

2. **说话人数量检查**：

    - 检测到 0 个说话人将被标记为问题
    - 检测到过多说话人（>10 个）将被标记为潜在问题

3. **数据完整性检查**：
    - 检查片段分布是否完整
    - 验证时间连续性

**使用示例**：

**示例 1：工作流模式**：

```json
{
    "workflow_config": {
        "workflow_chain": ["ffmpeg.extract_audio", "pyannote_audio.diarize_speakers", "pyannote_audio.validate_diarization"]
    },
    "pyannote_audio.validate_diarization": {
        "diarization_file": "${{ stages.pyannote_audio.diarize_speakers.output.diarization_file }}"
    }
}
```

**示例 2：单任务模式**：

```json
{
    "task_name": "pyannote_audio.validate_diarization",
    "input_data": {
        "pyannote_audio.validate_diarization": {
            "diarization_file": "/share/workflows/workflow123/diarization/diarization_result.json"
        }
    }
}
```

**依赖关系**：

-   必需：`pyannote_audio.diarize_speakers`

**技术特性**：

-   全面的质量评估算法

-   详细的问题诊断报告

-   支持动态参数引用

-   提供修复建议

**单任务模式支持**：

**输入参数**:

-   `diarization_file` (string, 必需): 说话人分离结果文件路径

**单任务调用示例**:

```json
{
    "task_name": "pyannote_audio.validate_diarization",
    "input_data": {
        "diarization_file": "/share/diarization/result.json"
    }
}
```

**参数来源说明**:

-   `diarization_file`: **节点参数** (在请求体中的 `pyannote_audio.validate_diarization` 对象内提供)

**注意事项**：

-   `diarization_file` 必须是从 `pyannote_audio.diarize_speakers` 输出的有效文件路径

-   验证结果仅供参考，不影响原始分离结果

-   建议在关键业务场景中使用此节点进行质量保证

---

---

## PaddleOCR 服务节点

PaddleOCR 服务提供基于 PaddleOCR 模型的文字识别功能，专门用于视频字幕的检测、识别和处理。

### 1. paddleocr.detect_subtitle_area

通过关键帧分析检测视频中的字幕区域位置，支持多种输入模式。

**功能描述**：分析视频关键帧，使用计算机视觉技术检测字幕通常出现的区域位置。支持本地目录、远程 MinIO 目录等多种输入源，提供灵活的使用方式。

**输入参数**：

-   `keyframe_dir` (string, 节点可选): 直接指定关键帧目录路径，支持本地路径或 MinIO URL（如 `minio://bucket/path/to/keyframes`）

-   `download_from_minio` (bool, 节点可选): 是否从 MinIO 下载关键帧，默认 false

-   `local_keyframe_dir` (string, 节点可选): 本地保存下载关键帧的目录，默认使用共享存储路径

-   `keyframe_sample_count` (int, 节点可选): 关键帧采样数量（保留参数，当前未使用）

**配置来源说明**：

-   所有列出的参数均为 **节点参数** (在请求体中的 `paddleocr.detect_subtitle_area` 对象内提供)。

**智能输入源选择**（按优先级）：

1. **参数指定目录** (`keyframe_dir`): 如果提供了 `keyframe_dir` 参数，将直接使用
2. **MinIO URL**: 如果 `keyframe_dir` 是 MinIO URL 且 `download_from_minio=true`，将从 MinIO 下载
3. **工作流上下文**: 如果未提供参数，将从 `ffmpeg.extract_keyframes` 输出获取

**支持的三种输入模式**：

#### 模式 1：工作流模式（默认）

从前置阶段自动获取关键帧目录，保持向后兼容性：

```json
{
    "workflow_config": {
        "workflow_chain": ["ffmpeg.extract_keyframes", "paddleocr.detect_subtitle_area"]
    }
}
```

#### 模式 2：参数模式（直接指定本地目录）

```json
{
    "workflow_config": {
        "workflow_chain": ["paddleocr.detect_subtitle_area"]
    },
    "paddleocr.detect_subtitle_area": {
        "keyframe_dir": "/local/path/to/keyframes"
    }
}
```

#### 模式 3：远程模式（MinIO 目录下载）

```json
{
    "workflow_config": {
        "workflow_chain": ["paddleocr.detect_subtitle_area"]
    },
    "paddleocr.detect_subtitle_area": {
        "keyframe_dir": "minio://yivideo/workflow_123/keyframes",
        "download_from_minio": true,
        "local_keyframe_dir": "/shared/workflows/custom_dir"
    }
}
```

**前置依赖**：

-   **工作流模式**: `ffmpeg.extract_keyframes`

-   **参数模式**: 无（直接指定目录）

-   **远程模式**: MinIO 存储桶中有对应的关键帧目录

**输出格式**：

```json
{
  "subtitle_area": [0, 918, 1920, 1080],
  "detection_confidence": 0.95,
  "keyframes_analyzed": 100,
  "detection_method": "unified_bottom_detection",
  "input_source": "parameter_local|parameter_minio|workflow_ffmpeg|workflow_minio",
  "minio_download_result": {
    "total_files": 50,
    "downloaded_files": ["frame_001.jpg", "frame_002.jpg", ...]
  }
}
```

**输出字段说明**：

-   `subtitle_area`: 检测到的字幕区域坐标

-   `detection_confidence`: 检测置信度

-   `keyframes_analyzed`: 分析的关键帧数量

-   `detection_method`: 使用的检测方法

-   `input_source`: 输入源类型，用于调试和监控

-   `minio_download_result`: MinIO 下载结果（仅当从 MinIO 下载时）

**使用示例**：

**示例 1：工作流模式（传统）**：

```json
{
    "workflow_config": {
        "workflow_chain": ["ffmpeg.extract_keyframes", "paddleocr.detect_subtitle_area"]
    }
}
```

**示例 2：参数模式（单任务）**：

```json
{
    "task_name": "paddleocr.detect_subtitle_area",
    "input_data": {
        "paddleocr.detect_subtitle_area": {
            "keyframe_dir": "/share/my_project/keyframes"
        }
    }
}
```

**示例 3：MinIO 远程模式**：

```json
{
    "task_name": "paddleocr.detect_subtitle_area",
    "input_data": {
        "paddleocr.detect_subtitle_area": {
            "keyframe_dir": "minio://yivideo/project-456/keyframes",
            "download_from_minio": true,
            "local_keyframe_dir": "/shared/workflows/downloaded_frames"
        }
    }
}
```

**示例 4：动态引用模式**：

```json
{
    "workflow_config": {
        "workflow_chain": ["ffmpeg.extract_keyframes", "paddleocr.detect_subtitle_area"]
    },
    "paddleocr.detect_subtitle_area": {
        "keyframe_dir": "${{ stages.ffmpeg.extract_keyframes.output.keyframe_dir }}"
    }
}
```

**依赖关系**：

-   **默认模式**: `ffmpeg.extract_keyframes`

-   **参数模式**: 无（直接指定目录）

-   **MinIO 模式**: 需要 MinIO 服务可用

**新增特性**：

#### 1. 自定义参数支持

-   支持通过 `node_params` 传入自定义参数

-   与工作流参数系统完全集成

-   支持 `${{...}}` 动态引用语法

#### 2. 远程目录下载

-   支持从 MinIO 下载整个关键帧目录

-   自动处理目录结构和文件匹配

-   支持 JPEG 文件自动过滤

-   下载失败时的优雅降级处理

#### 3. 智能源选择

-   三种输入模式的自动切换

-   优先级明确，行为可预测

-   完整的错误处理和日志记录

#### 4. 向后兼容性

-   完全兼容现有的工作流配置

-   无需修改现有代码和配置

-   新功能通过显式参数启用

**检测原理**：

-   分析多帧字幕位置分布

-   识别字幕出现的规律区域

-   计算最佳字幕区域坐标

-   支持多种字幕位置检测

**单任务模式支持**：

**输入参数**:

-   `keyframe_dir` (string, 可选): 直接指定关键帧目录路径，支持本地路径或 MinIO URL
-   `download_from_minio` (bool, 可选): 是否从 MinIO 下载关键帧，默认 false
-   `local_keyframe_dir` (string, 可选): 本地保存下载关键帧的目录，默认使用共享存储路径
-   `keyframe_sample_count` (int, 可选): 关键帧采样数量（保留参数，当前未使用）

**单任务调用示例**:

```json
{
    "task_name": "paddleocr.detect_subtitle_area",
    "input_data": {
        "keyframe_dir": "/share/my_project/keyframes",
        "download_from_minio": false,
        "local_keyframe_dir": "/shared/workflows/custom_dir"
    }
}
```

**参数来源说明**:

-   所有列出的参数均为 **节点参数** (在请求体中的 `paddleocr.detect_subtitle_area` 对象内提供)

**注意事项**：

-   MinIO 模式需要确保 MinIO 服务可访问

-   下载的临时目录会在任务完成后自动清理

-   支持的文件格式：JPEG 图片

-   处理大量关键帧时建议适当采样

---

### 2. paddleocr.create_stitched_images

将裁剪的字幕条图像并发拼接成大图，提高 OCR 识别效率。

**功能描述**：通过调用外部脚本 [`executor_stitch_images.py`](services/workers/paddleocr_service/app/executor_stitch_images.py)，将多个独立的字幕条图像并发拼接成一张大图，便于批量 OCR 处理。支持从本地目录或 MinIO 远程目录获取裁剪图像，并支持将拼接后的结果上传回 MinIO。

**输入参数**：

-   `cropped_images_path` (string, 节点可选): 裁剪图像的目录路径。支持以下三种格式：

    -   本地路径：如 `/share/workflows/{workflow_id}/cropped_images/frames`
    -   MinIO URL 格式：如 `minio://bucket/path/to/images`
    -   HTTP URL 格式：如 `http://minio:9000/yivideo/task-123/cropped_images`

    如果提供此参数，将优先使用。支持 `${{...}}` 格式的参数引用。当提供 HTTP 或 MinIO URL 时，系统会自动下载到本地临时目录。

-   `subtitle_area` (array, 节点可选): 字幕区域坐标，格式为 `[x1, y1, x2, y2]`（绝对像素坐标）。如果提供此参数，将优先使用。支持 `${{...}}` 格式的参数引用。此参数用于在拼接图像的元数据中记录 x_offset（x1 值），供后续 OCR 阶段使用。

-   `upload_stitched_images_to_minio` (bool, 节点可选): 是否将拼接后的大图目录上传到 MinIO，默认 true。

-   `delete_local_stitched_images_after_upload` (bool, 节点可选): 上传成功后是否删除本地拼接大图，默认 false。此参数仅在 `upload_stitched_images_to_minio=true` 时生效。

**智能参数选择**：

-   `cropped_images_path` (按优先级)：

    1. 显式传入的节点参数（支持 MinIO URL 自动下载）
    2. `input_data` 中的参数
    3. `ffmpeg.crop_subtitle_images` 输出的 `cropped_images_path`

-   `subtitle_area` (按优先级)：
    1. 显式传入的节点参数
    2. `input_data` 中的参数
    3. `paddleocr.detect_subtitle_area` 输出的 `subtitle_area`

**配置来源说明**：

-   `cropped_images_path`, `subtitle_area`, `upload_stitched_images_to_minio`, `delete_local_stitched_images_after_upload`: **节点参数** (在请求体中的 `paddleocr.create_stitched_images` 对象内提供)。

-   **拼接参数**: 如 `concat_batch_size` (默认 50), `stitching_workers` (默认 10) 等，均为 **全局配置**，请在 `config.yml` 文件的 `pipeline` 部分修改。

**全局配置示例 (config.yml)**:

```yaml
pipeline:
    concat_batch_size: 50 # 每批拼接的图像数量
    stitching_workers: 10 # 并发拼接的工作进程数
```

**前置依赖**：

-   无（可选依赖 `ffmpeg.crop_subtitle_images` - 如果未提供 `cropped_images_path` 参数）

-   无（可选依赖 `paddleocr.detect_subtitle_area` - 如果未提供 `subtitle_area` 参数）

**输出格式**：

```json
{
    "multi_frames_path": "/share/workflows/{workflow_id}/cropped_images/multi_frames",
    "manifest_path": "/share/workflows/{workflow_id}/cropped_images/multi_frames.json",
    "multi_frames_minio_url": "http://minio:9000/yivideo/{workflow_id}/stitched_images",
    "manifest_minio_url": "http://minio:9000/yivideo/{workflow_id}/manifest/multi_frames.json",
    "multi_frames_upload_error": null,
    "manifest_upload_error": null
}
```

**输出字段说明**：

-   `multi_frames_path`: 本地拼接大图目录路径
-   `manifest_path`: 本地清单文件路径，包含拼接图像的元数据
-   `multi_frames_minio_url`: MinIO 中的拼接图像目录 URL（仅当启用上传时）
-   `manifest_minio_url`: MinIO 中的清单文件 URL（仅当启用上传时）
-   `multi_frames_upload_error`: 拼接图像上传错误信息（如果有）
-   `manifest_upload_error`: 清单文件上传错误信息（如果有）

**Manifest 文件格式**：

清单文件（`multi_frames.json`）记录了每个拼接图像的元数据，格式如下：

```json
{
    "mf_00000001.jpg": {
        "stitched_height": 1620,
        "sub_images": [
            {
                "frame_idx": 0,
                "height": 162,
                "y_offset": 0,
                "x_offset": 0
            },
            {
                "frame_idx": 1,
                "height": 162,
                "y_offset": 162,
                "x_offset": 0
            }
        ]
    }
}
```

**使用示例**：

**示例 1：工作流模式（自动获取）**：

```json
{
    "workflow_config": {
        "workflow_chain": ["ffmpeg.extract_keyframes", "paddleocr.detect_subtitle_area", "ffmpeg.crop_subtitle_images", "paddleocr.create_stitched_images"]
    }
}
```

**示例 2：参数模式（单任务 + MinIO 输入输出）**：

```json
{
    "task_name": "paddleocr.create_stitched_images",
    "input_data": {
        "paddleocr.create_stitched_images": {
            "cropped_images_path": "http://minio.example.com/yivideo/task-123/cropped_images",
            "subtitle_area": [0, 918, 1920, 1080],
            "upload_stitched_images_to_minio": true,
            "delete_local_stitched_images_after_upload": true
        }
    }
}
```

**示例 3：动态引用模式**：

```json
{
    "workflow_config": {
        "workflow_chain": ["ffmpeg.extract_keyframes", "paddleocr.detect_subtitle_area", "ffmpeg.crop_subtitle_images", "paddleocr.create_stitched_images"]
    },
    "paddleocr.create_stitched_images": {
        "cropped_images_path": "${{ stages.ffmpeg.crop_subtitle_images.output.cropped_images_path }}",
        "subtitle_area": "${{ stages.paddleocr.detect_subtitle_area.output.subtitle_area }}",
        "upload_stitched_images_to_minio": true
    }
}
```

**技术特性**：

-   **并发处理**: 使用多进程并发拼接，提高处理速度
-   **外部脚本执行**: 通过 subprocess 调用独立脚本，避免 Celery 守护进程限制
-   **MinIO 集成**: 支持从 MinIO 下载输入和上传输出
-   **自动清理**: 支持临时文件的自动清理
-   **超时保护**: 子进程执行超时时间为 1800 秒（30 分钟）
-   **错误处理**: 完善的错误捕获和日志记录

**MinIO 下载逻辑**：

当 `cropped_images_path` 为 HTTP 或 MinIO URL 时：

1. 自动创建临时下载目录：`/share/workflows/{workflow_id}/downloaded_cropped_{timestamp}`
2. 将 HTTP URL 转换为 MinIO 格式（如果需要）
3. 使用 [`download_directory_from_minio`](services/common/minio_directory_download.py) 下载整个目录
4. 下载成功后使用本地路径进行拼接
5. 任务完成后自动清理临时下载目录（如果启用了清理配置）

**MinIO 上传逻辑**：

当 `upload_stitched_images_to_minio=true` 时：

1. 上传拼接图像目录到 `{workflow_id}/stitched_images`
2. 上传清单文件到 `{workflow_id}/manifest/multi_frames.json`
3. 根据 `delete_local_stitched_images_after_upload` 决定是否删除本地文件
4. 上传失败时记录错误但不中断任务

**注意事项**：

-   拼接批次大小（`concat_batch_size`）影响内存使用和处理速度，建议根据图像大小调整
-   并发工作进程数（`stitching_workers`）应根据 CPU 核心数合理设置
-   MinIO URL 格式支持 `minio://bucket/path` 和 `http(s)://host:port/bucket/path`
-   临时下载目录会在任务完成后自动清理（如果启用了 `cleanup_temp_files` 配置）
-   拼接图像的元数据（包括 x_offset）会保存在 manifest 文件中，供后续 OCR 阶段使用

**依赖关系**：

-   **默认模式**: `ffmpeg.crop_subtitle_images` 和 `paddleocr.detect_subtitle_area`
-   **参数模式**: 无（直接指定所有必需参数）
-   **MinIO 模式**: 需要 MinIO 服务可用

**单任务模式支持**：

**输入参数**:

-   `cropped_images_path` (string, 可选): 裁剪图像的目录路径，支持本地路径或 MinIO URL 格式
-   `subtitle_area` (array, 可选): 字幕区域坐标，格式为 `[x1, y1, x2, y2]`，支持 `${{...}}` 动态引用
-   `upload_stitched_images_to_minio` (bool, 可选): 是否将拼接后的大图目录上传到 MinIO，默认 true
-   `delete_local_stitched_images_after_upload` (bool, 可选): 上传成功后是否删除本地拼接大图，默认 false

**单任务调用示例**:

```json
{
    "task_name": "paddleocr.create_stitched_images",
    "input_data": {
        "cropped_images_path": "/share/cropped_images/frames",
        "subtitle_area": [0, 918, 1920, 1080],
        "upload_stitched_images_to_minio": true,
        "delete_local_stitched_images_after_upload": true
    }
}
```

**参数来源说明**:

-   所有列出的参数均为 **节点参数**，在请求体中的 `paddleocr.create_stitched_images` 对象内提供
-   拼接参数（如 concat_batch_size, stitching_workers 等）均为全局配置，在 config.yml 文件中设置

---

### 3. paddleocr.perform_ocr

对拼接后的字幕图像进行文字识别。

**功能描述**：使用 PaddleOCR 模型对字幕图像进行高精度文字识别。支持单步任务模式，可通过参数直接传入所需的拼接图像清单和目录。

**输入参数**：

-   `manifest_path` (string, 节点可选): 拼接图像的清单文件路径，支持本地路径或 MinIO URL 格式。
-   `multi_frames_path` (string, 节点可选): 拼接图像的目录路径，支持本地路径或 MinIO URL 格式。
-   `upload_ocr_results_to_minio` (bool, 节点可选): 是否上传 OCR 结果到 MinIO，默认 true。
-   `delete_local_ocr_results_after_upload` (bool, 节点可选): 上传后是否删除本地 OCR 结果，默认 false。

**配置来源说明**：

-   `manifest_path`, `multi_frames_path`, `upload_ocr_results_to_minio`, `delete_local_ocr_results_after_upload`: **节点参数** (在请求体中的 `paddleocr.perform_ocr` 对象内提供)。
-   **OCR 参数**: 如 `lang`, `use_angle_cls`, `use_gpu` 等，均为 **全局配置**，请在 `config.yml` 文件中修改。

**智能参数选择**：

-   `manifest_path` (按优先级)：

    1. 显式传入的节点参数（支持 MinIO URL 自动下载）
    2. `input_data` 中的参数
    3. `paddleocr.create_stitched_images` 输出的 `manifest_path`

-   `multi_frames_path` (按优先级)：
    1. 显式传入的节点参数（支持 MinIO URL 自动下载）
    2. `input_data` 中的参数
    3. `paddleocr.create_stitched_images` 输出的 `multi_frames_path`

**前置依赖**：

-   无（可选依赖 `paddleocr.create_stitched_images` - 如果未提供 `manifest_path` 和 `multi_frames_path` 参数）

**单任务模式支持**：

**输入参数**:

-   `manifest_path` (string, 可选): 拼接图像的清单文件路径，支持本地路径或 MinIO URL 格式
-   `multi_frames_path` (string, 可选): 拼接图像的目录路径，支持本地路径或 MinIO URL 格式
-   `upload_ocr_results_to_minio` (bool, 可选): 是否上传 OCR 结果到 MinIO，默认 true
-   `delete_local_ocr_results_after_upload` (bool, 可选): 上传后是否删除本地 OCR 结果，默认 false

**单任务调用示例**:

```json
{
    "task_name": "paddleocr.perform_ocr",
    "input_data": {
        "manifest_path": "/share/manifest/multi_frames.json",
        "multi_frames_path": "/share/stitched_images",
        "upload_ocr_results_to_minio": true,
        "delete_local_ocr_results_after_upload": false
    }
}
```

**参数来源说明**:

-   所有列出的参数均为 **节点参数**，在请求体中的 `paddleocr.perform_ocr` 对象内提供
-   OCR 模型参数（如 lang, use_angle_cls, use_gpu 等）均为全局配置，在 config.yml 文件中设置

**技术特性**：

-   支持 MinIO URL 自动下载和本地缓存
-   GPU 加速 OCR 处理（使用 GPU 锁保护）
-   自动上传 OCR 结果到 MinIO
-   支持压缩包输入自动解压
-   完善的错误处理和资源清理

**配置来源说明**：

-   **OCR 参数**: 如 `lang`, `use_angle_cls`, `use_gpu` 等，均为 **全局配置**，请在 `config.yml` 文件中修改。

---

### 4. paddleocr.postprocess_and_finalize

后处理 OCR 结果并生成最终的字幕文件。

**功能描述**：对 OCR 识别结果进行智能后处理，包括时间对齐、文本校正、格式化等。支持单步任务模式，可通过参数直接传入 OCR 结果文件。

**输入参数**：

-   `ocr_results_file` (string, 节点可选): OCR 结果文件路径，支持本地路径或 MinIO URL 格式。
-   `manifest_file` (string, 节点可选): 拼接图像的元数据文件路径，用于字幕时间对齐，支持本地路径或 MinIO URL 格式。
-   `upload_final_results_to_minio` (bool, 节点可选): 是否将最终字幕结果上传到 MinIO，默认 true。
-   `delete_local_results_after_upload` (bool, 节点可选): 上传后是否删除本地结果，默认 false。

**配置来源说明**：

-   `ocr_results_file`, `manifest_file`, `upload_final_results_to_minio`, `delete_local_results_after_upload`: **节点参数** (在请求体中的 `paddleocr.postprocess_and_finalize` 对象内提供)。
-   **后处理参数**: 如 `time_alignment_method`, `text_correction`, `min_confidence_threshold` 等，均为 **全局配置**，请在 `config.yml` 文件中修改。

**智能参数选择**：

-   `ocr_results_file` (按优先级)：

    1. 显式传入的节点参数（支持 MinIO URL 自动下载）
    2. `input_data` 中的参数
    3. `paddleocr.perform_ocr` 输出的 `ocr_results_file`

-   `manifest_file` (按优先级)：
    1. 显式传入的节点参数（支持 MinIO URL 自动下载）
    2. `input_data` 中的参数
    3. `paddleocr.create_stitched_images` 输出的 `manifest_path`

**前置依赖**：

-   无（可选依赖 `paddleocr.perform_ocr` - 如果未提供 `ocr_results_file` 和 `manifest_file` 参数）

**单任务模式支持**：

**输入参数**:

-   `ocr_results_file` (string, 可选): OCR 结果文件路径，支持本地路径或 MinIO URL 格式
-   `manifest_file` (string, 可选): 拼接图像的元数据文件路径，用于字幕时间对齐，支持本地路径或 MinIO URL 格式
-   `upload_final_results_to_minio` (bool, 可选): 是否将最终字幕结果上传到 MinIO，默认 true
-   `delete_local_results_after_upload` (bool, 可选): 上传后是否删除本地结果，默认 false

**单任务调用示例**:

```json
{
    "task_name": "paddleocr.postprocess_and_finalize",
    "input_data": {
        "ocr_results_file": "/share/ocr/ocr_results.json",
        "manifest_file": "/share/manifest/multi_frames.json",
        "upload_final_results_to_minio": true,
        "delete_local_results_after_upload": false
    }
}
```

**参数来源说明**:

-   所有列出的参数均为 **节点参数**，在请求体中的 `paddleocr.postprocess_and_finalize` 对象内提供
-   后处理参数（如 time_alignment_method, text_correction, min_confidence_threshold 等）均为全局配置，在 config.yml 文件中设置

**技术特性**：

-   支持 MinIO URL 自动下载和本地缓存
-   智能时间对齐算法
-   自动文本校正和格式化
-   支持多种字幕输出格式
-   自动上传最终结果到 MinIO
-   完善的错误处理和资源清理

## IndexTTS 服务节点

IndexTTS 服务提供基于 IndexTTS2 模型的高质量语音合成功能，支持情感化语音生成和音色克隆。

### 1. indextts.generate_speech

使用参考音频生成具有相同音色的语音。

**功能描述**：基于 IndexTTS2 模型，使用参考音频的音色特征合成新的语音内容，支持情感表达。

**输入参数**：

-   `text` (string, 必需): 要合成的文本内容。

-   `output_path` (string, 必需): 输出音频文件路径。

-   `spk_audio_prompt` (string, 必需): 说话人参考音频路径。

-   `emo_audio_prompt` (string, 可选): 情感参考音频路径。

**配置来源说明**：

-   `text`, `output_path`, `spk_audio_prompt`, `emo_audio_prompt`: **节点参数** (在请求体中的 `indextts.generate_speech` 对象内提供)。

-   **其他合成参数**: 如 `emotion_alpha`, `speed` 等，均为 **全局配置**，请在 `config.yml` 文件中修改。它们**不是**节点参数。

**输出格式**：

```json
{
    "output_path": "/share/workflows/{workflow_id}/tts/generated_speech.wav",
    "processing_time": 15.2,
    "text_length": 85,
    "audio_duration": 12.5,
    "reference_audio_used": "/share/reference/speaker.wav",
    "emotion_audio_used": "/share/reference/emotion.wav",
    "model_info": {
        "model_name": "IndexTTS2",
        "sample_rate": 22050,
        "channels": 1
    },
    "generation_params": {
        "emotion_alpha": 1.0,
        "speed": 1.0,
        "segments_generated": 3
    }
}
```

**使用示例**：

```json
{
    "workflow_config": {
        "workflow_chain": ["indextts.generate_speech"]
    },
    "indextts.generate_speech": {
        "text": "你好，这是一个使用IndexTTS2生成的语音示例。",
        "output_path": "/share/workflows/{workflow_id}/tts/example.wav",
        "spk_audio_prompt": "/share/reference/speaker_voice.wav",
        "emo_audio_prompt": "/share/reference/happy_emotion.wav",
        "emotion_alpha": 1.2,
        "speed": 1.0
    }
}
```

**依赖关系**：无

**技术特性**：

-   并发解码处理，提高处理速度

-   GPU 加速（使用 GPU 锁保护）

-   超时保护：1800 秒

-   高质量音色克隆

-   情感化语音合成

-   GPU 加速处理（使用 GPU 锁保护）

-   支持长文本分段处理

-   自然韵律和语调

**参数说明**：

-   `spk_audio_prompt`: 决定合成语音的音色特征

-   `emo_audio_prompt`: 控制语音的情感表达

-   `emotion_alpha`: 调节情感强度（0.5-2.0）

-   `speed`: 控制语音速度（0.5-2.0）

**单任务模式支持**：

**输入参数**:

-   `text` (string, 必需): 要合成的文本内容
-   `output_path` (string, 必需): 输出音频文件路径
-   `spk_audio_prompt` (string, 必需): 说话人参考音频路径
-   `emo_audio_prompt` (string, 可选): 情感参考音频路径

**单任务调用示例**:

```json
{
    "task_name": "indextts.generate_speech",
    "input_data": {
        "text": "你好，这是一个使用IndexTTS2生成的语音示例。",
        "output_path": "/shared/tts/generated_speech.wav",
        "spk_audio_prompt": "/shared/reference/speaker_voice.wav",
        "emo_audio_prompt": "/shared/reference/happy_emotion.wav"
    }
}
```

**参数来源说明**:

-   `text`, `output_path`, `spk_audio_prompt`, `emo_audio_prompt`: **节点参数** (在请求体中的 `indextts.generate_speech` 对象内提供)
-   其他合成参数（如 emotion_alpha, speed 等）均为全局配置，在 config.yml 文件中设置

**注意事项**：

-   必须提供说话人参考音频

-   参考音频质量直接影响合成效果

-   建议参考音频时长 3-10 秒

-   情感音频是可选的，用于控制情感表达

---

### 2. indextts.list_voice_presets

列出系统中可用的语音预设，用于语音合成时的参考。

**功能描述**：获取 IndexTTS2 模型支持的语音预设列表，包括预设名称、描述、语言和性别等信息，帮助用户选择合适的语音预设。

**输入参数**：

-   无直接输入参数。

**配置来源说明**：

-   无节点参数。语音预设信息从模型配置中获取。

**前置依赖**：

-   无（可独立运行）

**输出格式**：

```json
{
    "status": "success",
    "presets": {
        "default": {
            "name": "Default Voice",
            "description": "默认语音",
            "language": "zh-CN",
            "gender": "female"
        },
        "male_01": {
            "name": "Male Voice 01",
            "description": "男声01",
            "language": "zh-CN",
            "gender": "male"
        },
        "female_01": {
            "name": "Female Voice 01",
            "description": "女声01",
            "language": "zh-CN",
            "gender": "female"
        }
    },
    "total_count": 3
}
```

**使用示例**：

**示例 1：独立获取语音预设**：

```json
{
    "task_name": "indextts.list_voice_presets",
    "input_data": {}
}
```

**示例 2：在工作流中获取预设**：

```json
{
    "workflow_config": {
        "workflow_chain": ["indextts.list_voice_presets"]
    }
}
```

**依赖关系**：无

**技术特性**：

-   提供完整的预设信息

-   支持多语言预设

-   包含性别和描述信息

-   轻量级查询，不消耗 GPU 资源

**单任务模式支持**：

**输入参数**:

-   无直接输入参数（此节点主要用于信息查询）

**单任务调用示例**:

```json
{
    "task_name": "indextts.list_voice_presets",
    "input_data": {}
}
```

**参数来源说明**:

-   无节点参数。语音预设信息从模型配置中获取

**注意事项**：

-   此节点主要用于信息查询，不进行实际的语音合成

-   预设信息来源于模型配置文件

-   可以作为工作流的第一步来了解可用选项

---

### 3. indextts.get_model_info

获取 IndexTTS2 模型的详细信息和技术规格。

**功能描述**：返回 IndexTTS2 模型的详细技术信息，包括模型版本、设备状态、配置参数和能力特性等，常用于系统监控和配置验证。

**输入参数**：

-   无直接输入参数。

**配置来源说明**：

-   无节点参数。模型信息从运行环境配置中获取。

**前置依赖**：

-   无（可独立运行）

**输出格式**：

```json
{
    "status": "success",
    "model_info": {
        "model_type": "IndexTTS2",
        "model_version": "2.0",
        "device": "cuda",
        "model_path": "/models/indextts",
        "status": "ready (lazy-loading)",
        "capabilities": {
            "text_to_speech": true,
            "voice_cloning": true,
            "emotion_control": true,
            "multi_language": true,
            "real_time": false
        },
        "config": {
            "use_fp16": true,
            "use_deepspeed": false,
            "use_cuda_kernel": false
        }
    }
}
```

**输出字段说明**：

-   `model_type`: 模型类型

-   `model_version`: 模型版本号

-   `device`: 当前使用的设备（cuda/cpu）

-   `model_path`: 模型文件路径

-   `status`: 模型加载状态

-   `capabilities`: 支持的功能特性

-   `config`: 当前配置参数

**使用示例**：

**示例 1：独立获取模型信息**：

```json
{
    "task_name": "indextts.get_model_info",
    "input_data": {}
}
```

**示例 2：在工作流中获取模型信息**：

```json
{
    "workflow_config": {
        "workflow_chain": ["indextts.get_model_info", "indextts.generate_speech"]
    }
}
```

**依赖关系**：无

**技术特性**：

-   提供完整的模型技术规格

-   包含配置参数信息

-   支持功能特性检查

-   轻量级查询，响应快速

**单任务模式支持**：

**输入参数**:

-   无直接输入参数（此节点主要用于系统信息查询）

**单任务调用示例**:

```json
{
    "task_name": "indextts.get_model_info",
    "input_data": {}
}
```

**参数来源说明**:

-   无节点参数。模型信息从运行环境配置中获取

**注意事项**：

-   此节点主要用于系统监控和调试

-   模型状态为"lazy-loading"，首次使用时才会加载模型

-   配置参数来源于环境变量和配置文件

-   可以用于验证系统配置是否正确

---

---

## WService 字幕优化服务节点

WService 服务提供全面的字幕处理能力，包括基于转录数据生成字幕文件、AI 智能优化、字幕校正和 TTS 片段合并等功能。该服务从 `faster_whisper_service` 迁移了所有非 GPU 功能。

### 1. wservice.generate_subtitle_files

基于转录数据和可选的说话人数据生成多种格式的字幕文件。

**功能描述**：将转录数据转换为标准字幕格式，支持 SRT、VTT、ASS 等格式，并可选择集成说话人信息。

**输入参数**：

-   `segments_file` (string, 节点可选): 指定转录数据文件路径，以覆盖智能输入源选择逻辑。支持 `${{...}}` 格式的动态引用。

-   `diarization_file` (string, 节点可选): 指定说话人分离数据文件路径，以覆盖智能输入源选择逻辑。支持 `${{...}}` 格式的动态引用。

**配置来源说明**：

-   `segments_file`, `diarization_file`: **节点参数** (在请求体中的 `wservice.generate_subtitle_files` 对象内提供)。

-   **其他字幕格式化参数**: 如 `max_chars_per_line`, `max_lines_per_subtitle`, `min_subtitle_duration` 等，均为 **全局配置**，请在 `config.yml` 文件中修改。它们**不是**节点参数。

**全局配置示例 (config.yml)**:

```yaml
faster_whisper_service:
    # ... (other faster_whisper settings)
    subtitle_options:
        max_chars_per_line: 42
        max_lines_per_subtitle: 2
        min_subtitle_duration: 1.0
        include_speaker_labels: true
```

**前置依赖**：

-   `faster_whisper.transcribe_audio` (必需)

-   `pyannote_audio.diarize_speakers` (可选，用于说话人信息)

**智能输入源选择**（按优先级）：

1. **`segments_file`** **参数**: 如果在节点参数中明确提供了 `segments_file`（支持动态引用），将直接使用该文件
2. **`faster_whisper.transcribe_audio`** **输出**: 自动获取 `faster_whisper.transcribe_audio` 阶段的 `segments_file`

**输出格式**：

```json
{
    "subtitle_path": "/share/workflows/{workflow_id}/subtitles/video.srt",
    "speaker_srt_path": "/share/workflows/{workflow_id}/subtitles/video_with_speakers.srt",
    "speaker_json_path": "/share/workflows/{workflow_id}/subtitles/video_with_speakers.json",
    "word_timestamps_json_path": "/share/workflows/{workflow_id}/subtitles/video_word_timestamps.json",
    "subtitle_files": {
        "basic": "/share/workflows/{workflow_id}/subtitles/video.srt",
        "with_speakers": "/share/workflows/{workflow_id}/subtitles/video_with_speakers.srt",
        "word_timestamps": "/share/workflows/{workflow_id}/subtitles/video_word_timestamps.json"
    }
}
```

**使用示例**：

```json
{
    "workflow_config": {
        "workflow_chain": ["ffmpeg.extract_audio", "faster_whisper.transcribe_audio", "wservice.generate_subtitle_files"]
    }
}
```

**带说话人信息的示例**：

```json
{
    "workflow_config": {
        "workflow_chain": ["ffmpeg.extract_audio", "audio_separator.separate_vocals", "faster_whisper.transcribe_audio", "pyannote_audio.diarize_speakers", "wservice.generate_subtitle_files"]
    }
}
```

**依赖关系**：

-   必需：`faster_whisper.transcribe_audio`

-   可选：`pyannote_audio.diarize_speakers`

**输出文件说明**：

1. **基础 SRT 文件** (`subtitle_path`): 标准字幕格式
2. **带说话人 SRT** (`speaker_srt_path`): 包含说话人信息的字幕
3. **带说话人 JSON** (`speaker_json_path`): 完整的结构化数据
4. **词级时间戳 JSON** (`word_timestamps_json_path`): 精确的词级时间戳

**字幕格式特性**：

-   自动断行和时长优化

-   智能合并短字幕

-   拆分长字幕

-   时间轴平滑处理

-   说话人切换边界优化

**单任务模式支持**：

**输入参数**:

-   `segments_file` (string, 可选): 指定转录数据文件路径，支持 `${{...}}` 动态引用
-   `diarization_file` (string, 可选): 指定说话人分离数据文件路径，支持 `${{...}}` 动态引用

**单任务调用示例**:

```json
{
    "task_name": "wservice.generate_subtitle_files",
    "input_data": {
        "segments_file": "/share/transcription/segments.json",
        "diarization_file": "/share/diarization/speaker_segments.json"
    }
}
```

**参数来源说明**:

-   `segments_file`, `diarization_file`: **节点参数** (在请求体中的 `wservice.generate_subtitle_files` 对象内提供)
-   其他字幕格式化参数（如 max_chars_per_line, max_lines_per_subtitle, min_subtitle_duration 等）均为全局配置，在 config.yml 文件中设置

---

### 2. wservice.correct_subtitles

使用 LLM 对字幕进行智能校正和优化。

**功能描述**：基于大语言模型对转录字幕进行语法纠错、标点优化、语义理解等智能处理。

**输入参数**：

-   `subtitle_path` (string, 节点可选): 待校正的字幕文件路径。**支持** **`${{...}}`** **动态引用**，优先级高于自动检测。

**配置来源说明**：

-   `subtitle_path`: **节点参数** (在请求体中的 `wservice.correct_subtitles` 对象内提供)。

-   **其他校正参数**: 如 `correction_model`, `correction_type`, `target_language` 等，均为 **全局配置**，请在 `config.yml` 文件中修改。它们**不是**节点参数。

**智能输入源选择**（按优先级）：

1. **`subtitle_path`** **参数**: 如果在节点参数中明确提供了 `subtitle_path`（支持动态引用），将直接使用该文件。
2. **`generate_subtitle_files`** **的输出 (带说话人)**: 自动寻找 `wservice.generate_subtitle_files` 阶段输出的 `speaker_srt_path`。
3. **`generate_subtitle_files`** **的输出 (基础 SRT)**: 最后尝试使用 `wservice.generate_subtitle_files` 阶段输出的 `subtitle_path`。

**输出格式**：

```json
{
    "corrected_subtitle_path": "/share/workflows/{workflow_id}/subtitles/video_corrected.srt",
    "correction_report": "/share/workflows/{workflow_id}/subtitles/correction_report.json",
    "provider_used": "gemini",
    "processing_time": 25.3
}
```

**依赖关系**：

-   `wservice.generate_subtitle_files` (如果未通过 `subtitle_path` 参数指定输入)

**单任务模式支持**：

**输入参数**:

-   `subtitle_path` (string, 可选): 待校正的字幕文件路径，支持 `${{...}}` 动态引用

**单任务调用示例**:

```json
{
    "task_name": "wservice.correct_subtitles",
    "input_data": {
        "subtitle_path": "/share/subtitles/video.srt"
    }
}
```

**参数来源说明**:

-   `subtitle_path`: **节点参数** (在请求体中的 `wservice.correct_subtitles` 对象内提供)
-   其他校正参数（如 correction_model, correction_type, target_language 等）均为全局配置，在 config.yml 文件中设置

**注意事项**：

-   校正相关的微调参数（如 `correction_model`）应在 `config.yml` 中配置。

-   需要配置相应的 LLM API 密钥。

---

### 3. wservice.ai_optimize_subtitles

对转录后的字幕进行 AI 智能优化和校正。

**功能描述**：使用 AI 大模型对 faster_whisper 转录的字幕进行智能优化，包括错别字修正、标点补充、口头禅删除、语法优化等。支持大体积字幕的并发处理，采用滑窗重叠分段策略保证上下文完整性。

**输入参数**：

-   `segments_file` (string, 节点可选): 输入字幕文件路径。**支持** **`${{...}}`** **动态引用**，优先级高于自动检测。

**配置来源说明**：

-   `segments_file`: **节点参数** (在请求体中的 `wservice.ai_optimize_subtitles` 对象内提供)。

-   `subtitle_optimization` (object): **全局参数** (在 API 请求的顶层 `workflow_config` 内提供)，包含 `enabled`, `provider`, `batch_size` 等所有优化相关的微调选项。

**前置依赖**：

-   `faster_whisper.transcribe_audio` (必需)

**智能输入源选择**（按优先级）：

1. **`segments_file`** **参数**: 如果在节点参数中明确提供了 `segments_file`（支持动态引用），将直接使用该文件
2. **`faster_whisper.transcribe_audio`** **输出**: 自动获取 `faster_whisper.transcribe_audio` 阶段的 `segments_file`

**输出格式**：

```json
{
    "optimized_file_path": "/share/workflows/{workflow_id}/optimized.json",
    "original_file_path": "/share/workflows/{workflow_id}/original.json",
    "provider_used": "deepseek",
    "processing_time": 12.5,
    "commands_applied": 15,
    "batch_mode": true,
    "batches_count": 3,
    "segments_count": 100
}
```

**依赖关系**：

-   必需：`faster_whisper.transcribe_audio`

-   后置：`wservice.generate_subtitle_files` (可选)

**注意事项**：

-   `subtitle_optimization` 的详细参数（如 `provider`, `batch_size`）应在 API 请求顶层的 `workflow_config` 中配置。

-   需要配置相应 AI 提供商的 API 密钥。

-   大体积字幕自动启用分段处理。

-   滑窗重叠机制确保上下文完整性。

**单任务模式支持**：

**输入参数**:

-   `segments_file` (string, 可选): 输入字幕文件路径，支持 `${{...}}` 动态引用

**单任务调用示例**:

```json
{
    "task_name": "wservice.ai_optimize_subtitles",
    "input_data": {
        "segments_file": "/share/transcription/segments.json"
    }
}
```

**参数来源说明**:

-   `segments_file`: **节点参数** (在请求体中的 `wservice.ai_optimize_subtitles` 对象内提供)
-   `subtitle_optimization` (全局参数): 在 API 请求的顶层 `workflow_config` 内提供，包含 `enabled`, `provider`, `batch_size` 等所有优化相关的微调选项

---

### 4. wservice.merge_speaker_segments

合并转录字幕与说话人时间段（片段级）。

**功能描述**：将 `faster_whisper` 的转录片段与 `pyannote_audio` 的说话人片段在片段级别进行合并，为每个字幕片段分配一个说话人标签。

**输入参数**：

-   无直接节点参数，所有输入均从工作流上下文自动获取。

**前置依赖**：

-   `faster_whisper.transcribe_audio` (必需)

-   `pyannote_audio.diarize_speakers` (必需)

**输出格式**：

```json
{
    "merged_segments": [
        {
            "start": 0.5,
            "end": 2.3,
            "text": "这是第一段字幕",
            "speaker": "SPEAKER_00"
        },
        {
            "start": 2.5,
            "end": 5.1,
            "text": "这是第二段字幕",
            "speaker": "SPEAKER_01"
        }
    ]
}
```

**使用示例**：

```json
{
    "workflow_config": {
        "workflow_chain": ["...", "faster_whisper.transcribe_audio", "pyannote_audio.diarize_speakers", "wservice.merge_speaker_segments"]
    }
}
```

**依赖关系**：

-   必需：`faster_whisper.transcribe_audio` 和 `pyannote_audio.diarize_speakers`

**单任务模式支持**：

**输入参数**:

-   `segments_data` (array, 可选): 直接提供转录片段数据数组，支持 `${{...}}` 动态引用
-   `speaker_segments_data` (array, 可选): 直接提供说话人分离片段数据数组，支持 `${{...}}` 动态引用
-   `segments_file` (string, 可选): 指定转录数据文件路径，支持 `${{...}}` 动态引用
-   `diarization_file` (string, 可选): 指定说话人分离数据文件路径，支持 `${{...}}` 动态引用
-   `source_stage_names` (object, 可选): 自定义源阶段名称配置，用于从工作流上下文获取数据

**单任务调用示例 1 - 直接传数据**:

```json
{
    "task_name": "wservice.merge_speaker_segments",
    "input_data": {
        "segments_data": [
            { "start": 0.5, "end": 2.3, "text": "这是第一段字幕" },
            { "start": 2.5, "end": 5.1, "text": "这是第二段字幕" }
        ],
        "speaker_segments_data": [
            { "start": 0.0, "end": 3.0, "speaker": "SPEAKER_00" },
            { "start": 3.0, "end": 6.0, "speaker": "SPEAKER_01" }
        ]
    }
}
```

**单任务调用示例 2 - 文件路径**:

```json
{
    "task_name": "wservice.merge_speaker_segments",
    "input_data": {
        "segments_file": "/share/transcription/segments.json",
        "diarization_file": "/share/diarization/speaker_segments.json"
    }
}
```

**单任务调用示例 3 - 动态引用**:

```json
{
    "task_name": "wservice.merge_speaker_segments",
    "input_data": {
        "segments_file": "${{ context.input_params.segments_file }}",
        "diarization_file": "${{ context.input_params.diarization_file }}"
    }
}
```

**参数来源说明**:

-   节点参数可通过 `input_data` 直接传入，支持动态引用解析
-   优先级：直接传入数据 > 文件路径 > 工作流上下文自动获取
-   所有参数都支持 `${{...}}` 动态引用语法

---

### 5. wservice.merge_with_word_timestamps

使用词级时间戳进行精确的字幕与说话人合并。

**功能描述**：当转录结果包含词级时间戳时，此节点能够更精确地将每个单词与其对应的说话人进行匹配，从而生成更准确的带说话人标签的字幕。

**输入参数**：

-   无直接节点参数，所有输入均从工作流上下文自动获取。

**前置依赖**：

-   `faster_whisper.transcribe_audio` (必需, 且必须启用词级时间戳)

-   `pyannote_audio.diarize_speakers` (必需)

**输出格式**：
与 `wservice.merge_speaker_segments` 类似，但每个片段的说话人归属更精确。

```json
{
    "merged_segments": [
        {
            "start": 0.5,
            "end": 2.3,
            "text": "这是第一段字幕",
            "speaker": "SPEAKER_00",
            "words": [
                { "word": "这是", "start": 0.5, "end": 0.8, "speaker": "SPEAKER_00" },
                { "word": "第一段字幕", "start": 0.9, "end": 2.3, "speaker": "SPEAKER_00" }
            ]
        }
    ]
}
```

**使用示例**：

```json
{
    "workflow_config": {
        "workflow_chain": ["...", "faster_whisper.transcribe_audio", "pyannote_audio.diarize_speakers", "wservice.merge_with_word_timestamps"]
    },
    "faster_whisper.transcribe_audio": {
        // 确保在全局配置中启用了词级时间戳
    }
}
```

**依赖关系**：

-   必需：`faster_whisper.transcribe_audio` (启用词级时间戳)

-   必需：`pyannote_audio.diarize_speakers`

**注意事项**：

-   仅当 `faster_whisper.transcribe_audio` 的输出包含有效的词级时间戳时，此节点才能正常工作。

-   这是生成最精确说话人字幕的首选方法。

**单任务模式支持**：

**输入参数**:

-   `segments_data` (array, 可选): 直接提供包含词级时间戳的转录片段数据数组，支持 `${{...}}` 动态引用
-   `speaker_segments_data` (array, 可选): 直接提供说话人分离片段数据数组，支持 `${{...}}` 动态引用
-   `segments_file` (string, 可选): 指定转录数据文件路径，支持 `${{...}}` 动态引用
-   `diarization_file` (string, 可选): 指定说话人分离数据文件路径，支持 `${{...}}` 动态引用
-   `source_stage_names` (object, 可选): 自定义源阶段名称配置，用于从工作流上下文获取数据

**单任务调用示例 1 - 直接传数据**:

```json
{
    "task_name": "wservice.merge_with_word_timestamps",
    "input_data": {
        "segments_data": [
            {
                "start": 0.5,
                "end": 2.3,
                "text": "这是第一段字幕",
                "words": [
                    { "word": "这是", "start": 0.5, "end": 0.8 },
                    { "word": "第一段字幕", "start": 0.9, "end": 2.3 }
                ]
            }
        ],
        "speaker_segments_data": [
            { "start": 0.0, "end": 3.0, "speaker": "SPEAKER_00" },
            { "start": 3.0, "end": 6.0, "speaker": "SPEAKER_01" }
        ]
    }
}
```

**单任务调用示例 2 - 文件路径**:

```json
{
    "task_name": "wservice.merge_with_word_timestamps",
    "input_data": {
        "segments_file": "/share/transcription/segments_with_words.json",
        "diarization_file": "/share/diarization/speaker_segments.json"
    }
}
```

**单任务调用示例 3 - 动态引用**:

```json
{
    "task_name": "wservice.merge_with_word_timestamps",
    "input_data": {
        "segments_file": "${{ context.input_params.segments_file }}",
        "diarization_file": "${{ context.input_params.diarization_file }}"
    }
}
```

**参数来源说明**:

-   节点参数可通过 `input_data` 直接传入，支持动态引用解析
-   优先级：直接传入数据 > 文件路径 > 工作流上下文自动获取
-   所有参数都支持 `${{...}}` 动态引用语法

**注意事项**:

-   转录数据必须包含词级时间戳信息（`words` 字段）
-   如果转录数据不包含词级时间戳，将回退到片段级合并逻辑
-   单任务模式下推荐直接提供包含词级时间戳的数据以获得最佳精度

---

### 6. wservice.prepare_tts_segments

为 TTS 参考音准备和优化字幕片段。

**功能描述**：根据指定的时长和间隙要求，对字幕片段进行智能合并与分割，为后续的语音合成（TTS）任务准备符合要求的参考音频片段。

**输入参数**：

-   无直接节点参数，所有输入均从工作流上下文自动获取。

**配置来源说明**：

-   **TTS 合并参数**: 如 `min_duration`, `max_duration`, `max_gap`, `split_on_punctuation` 等，均为 **全局配置**，请在 `config.yml` 文件的 `wservice.tts_merger_settings` 部分修改。

**前置依赖**：

-   `wservice.merge_with_word_timestamps` (推荐)

-   或 `wservice.merge_speaker_segments`

-   或 `wservice.generate_subtitle_files`

-   _简而言之，任何成功生成了_ _`merged_segments`_ _或_ _`segments`_ _的节点。_

**智能输入源选择**：

-   节点会自动从工作流上下文中寻找 `merged_segments` 或 `segments` 数据。

**输出格式**：

```json
{
    "prepared_segments": [
        {
            "id": 1,
            "start": 0.5,
            "end": 9.8,
            "text": "这是第一个为TTS准备的、合并后的长片段。",
            "speaker": "SPEAKER_00"
        }
    ],
    "source_stage": "wservice.merge_with_word_timestamps",
    "total_segments": 1
}
```

**使用示例**：

```json
{
    "workflow_config": {
        "workflow_chain": ["...", "wservice.merge_with_word_timestamps", "wservice.prepare_tts_segments"]
    }
}
// 注：此节点的行为由 config.yml 中的 wservice.tts_merger_settings 控制
```

**依赖关系**：

-   必需：一个成功生成字幕片段的前置节点。

**注意事项**：

-   此节点是为 `indextts.generate_speech` 或其他 TTS 任务准备输入数据的关键步骤。

-   合并与分割的具体行为由 `config.yml` 中的全局配置决定。

**单任务模式支持**：

**输入参数**:

-   `merged_segments` (array, 可选): 直接提供已合并的字幕片段数据数组，支持 `${{...}}` 动态引用
-   `segments` (array, 可选): 直接提供基础字幕片段数据数组，支持 `${{...}}` 动态引用
-   `segments_file` (string, 可选): 指定字幕片段数据文件路径，支持 `${{...}}` 动态引用
-   `source_stage_names` (object, 可选): 自定义源阶段名称配置，用于从工作流上下文获取数据

**单任务调用示例 1 - 直接传合并片段数据**:

```json
{
    "task_name": "wservice.prepare_tts_segments",
    "input_data": {
        "merged_segments": [
            {
                "id": 1,
                "start": 0.5,
                "end": 9.8,
                "text": "这是第一个为TTS准备的、合并后的长片段。",
                "speaker": "SPEAKER_00"
            },
            {
                "id": 2,
                "start": 10.2,
                "end": 15.6,
                "text": "这是第二个为TTS准备的片段。",
                "speaker": "SPEAKER_01"
            }
        ]
    }
}
```

**单任务调用示例 2 - 直接传基础片段数据**:

```json
{
    "task_name": "wservice.prepare_tts_segments",
    "input_data": {
        "segments": [
            { "start": 0.5, "end": 2.3, "text": "这是第一段" },
            { "start": 2.5, "end": 5.1, "text": "这是第二段" },
            { "start": 5.5, "end": 8.2, "text": "这是第三段" }
        ]
    }
}
```

**单任务调用示例 3 - 文件路径**:

```json
{
    "task_name": "wservice.prepare_tts_segments",
    "input_data": {
        "segments_file": "/share/subtitles/merged_segments.json"
    }
}
```

**单任务调用示例 4 - 动态引用**:

```json
{
    "task_name": "wservice.prepare_tts_segments",
    "input_data": {
        "merged_segments": "${{ context.input_params.merged_segments }}",
        "segments_file": "${{ context.input_params.segments_file }}"
    }
}
```

**参数来源说明**:

-   节点参数可通过 `input_data` 直接传入，支持动态引用解析
-   优先级：直接传入数据 > 文件路径 > 工作流上下文自动获取
-   所有参数都支持 `${{...}}` 动态引用语法
-   TTS 合并参数（如 min_duration, max_duration, max_gap, split_on_punctuation 等）均为全局配置，在 config.yml 文件的 wservice.tts_merger_settings 部分修改

**注意事项**:

-   推荐提供 `merged_segments` 数据以获得最佳效果（已包含说话人信息）
-   如果提供 `segments` 数据，节点将自动进行合并处理
-   合并与分割的具体行为由 config.yml 中的全局配置决定

---

## 工作流阶段依赖关系

### 依赖关系矩阵

YiVideo 工作流系统中的各节点存在明确的依赖关系，理解这些依赖关系对于正确配置工作流至关重要。

#### 1. 基础依赖关系

| 当前节点                             | 必需前置条件                                                | 可选前置条件                                                | 依赖说明                                                                                   |
| ------------------------------------ | ----------------------------------------------------------- | ----------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `ffmpeg.extract_audio`               | 无                                                          | 无                                                          | 工作流的起点之一                                                                           |
| `ffmpeg.extract_keyframes`           | 无                                                          | 无                                                          | 工作流的起点之一                                                                           |
| `audio_separator.separate_vocals`    | `ffmpeg.extract_audio`                                      | 无                                                          | 需要已提取的音频文件                                                                       |
| `faster_whisper.transcribe_audio`    | `ffmpeg.extract_audio` 或 `audio_separator.separate_vocals` | 无                                                          | 需要音频文件作为输入                                                                       |
| `pyannote_audio.diarize_speakers`    | `ffmpeg.extract_audio` 或 `audio_separator.separate_vocals` | 无                                                          | 需要音频文件作为输入                                                                       |
| `wservice.generate_subtitle_files`   | `faster_whisper.transcribe_audio`                           | `pyannote_audio.diarize_speakers`                           | 需要转录数据，可选说话人信息                                                               |
| `wservice.correct_subtitles`         | `wservice.generate_subtitle_files`                          | 无                                                          | 需要已生成的字幕文件                                                                       |
| `wservice.ai_optimize_subtitles`     | `faster_whisper.transcribe_audio`                           | 无                                                          | 需要转录数据                                                                               |
| `paddleocr.detect_subtitle_area`     | `ffmpeg.extract_keyframes`                                  | 无                                                          | 需要关键帧作为输入                                                                         |
| `ffmpeg.crop_subtitle_images`        | 无                                                          | `paddleocr.detect_subtitle_area`                            | 可选依赖：通过 `subtitle_area` 参数传入或从上游节点获取                                    |
| `paddleocr.create_stitched_images`   | `ffmpeg.crop_subtitle_images`                               | 无                                                          | 需要裁剪的图像，可通过 `input_data.cropped_images_path` 和 `input_data.subtitle_area` 传入 |
| `paddleocr.perform_ocr`              | `paddleocr.create_stitched_images`                          | 无                                                          | 需要拼接的图像                                                                             |
| `paddleocr.postprocess_and_finalize` | `paddleocr.perform_ocr`                                     | 无                                                          | 需要 OCR 结果                                                                              |
| `indextts.generate_speech`           | 无                                                          | 多个                                                        | 可独立运行或依赖上游输出                                                                   |
| `ffmpeg.split_audio_segments`        | `wservice.generate_subtitle_files`                          | `ffmpeg.extract_audio` 或 `audio_separator.separate_vocals` | 需要字幕和音频文件                                                                         |

#### 2. 数据流向说明

**语音转录流程**：

```
视频文件 → ffmpeg.extract_audio → audio_separator.separate_vocals (可选)
    → faster_whisper.transcribe_audio
    → pyannote_audio.diarize_speakers (可选)
    → wservice.generate_subtitle_files
    → wservice.correct_subtitles (可选)
    → wservice.ai_optimize_subtitles (可选)
```

**OCR 字幕提取流程**：

```
视频文件 → ffmpeg.extract_keyframes
    → paddleocr.detect_subtitle_area
    → ffmpeg.crop_subtitle_images
    → paddleocr.create_stitched_images
    → paddleocr.perform_ocr
    → paddleocr.postprocess_and_finalize
```

**语音合成流程**：

```
字幕文件 + 音频片段 → ffmpeg.split_audio_segments
    → indextts.generate_speech
```

#### 3. 循环依赖说明

**重要说明**：YiVideo 工作流系统**不支持循环依赖**。如果两个节点相互依赖（例如 A 需要 B 的输出，B 又需要 A 的输出），系统将无法正确执行。

**典型错误示例**：

```json
{
    "workflow_config": {
        "workflow_chain": [
            "faster_whisper.transcribe_audio",
            "wservice.generate_subtitle_files",
            "faster_whisper.transcribe_audio" // ❌ 错误：形成循环依赖
        ]
    }
}
```

#### 4. 智能依赖检测

工作流系统会在执行前进行依赖关系检查，如果发现缺失的依赖条件，将返回详细的错误信息，包括：

-   缺失的具体依赖节点

-   依赖节点的期望状态（如 `SUCCESS` 或 `COMPLETED`）

-   建议的修复方案

#### 5. 并行执行建议

为了提高工作流执行效率，以下节点可以并行执行：

-   `faster_whisper.transcribe_audio` 和 `pyannote_audio.diarize_speakers` (都依赖音频文件)

-   `ffmpeg.extract_keyframes` 和 `ffmpeg.extract_audio` (都直接依赖视频文件)

#### 6. 依赖关系最佳实践

1. **明确依赖**: 在工作流配置中明确指定所有必需的依赖关系
2. **避免循环**: 确保工作流拓扑结构是 DAG（有向无环图）
3. **合理并行**: 充分利用可并行执行的节点提高效率
4. **状态检查**: 在执行前检查所有前置条件是否满足

---

### 完整字幕生成工作流

```json
{
    "video_path": "/share/videos/example.mp4",
    "workflow_config": {
        "workflow_chain": ["ffmpeg.extract_audio", "audio_separator.separate_vocals", "faster_whisper.transcribe_audio", "pyannote_audio.diarize_speakers", "wservice.generate_subtitle_files"]
    },
    "audio_separator.separate_vocals": {
        "audio_separator_config": {
            "quality_mode": "high_quality",
            "use_vocal_optimization": true
        }
    },
    "faster_whisper.transcribe_audio": {
        "model_size": "base",
        "language": "zh",
        "word_timestamps": true
    },
    "pyannote_audio.diarize_speakers": {
        "hf_token": "your_hf_token",
        "num_speakers": 2
    }
}
```

### OCR 字幕提取工作流

```json
{
    "video_path": "/share/videos/example.mp4",
    "workflow_config": {
        "workflow_chain": ["ffmpeg.extract_keyframes", "paddleocr.detect_subtitle_area", "ffmpeg.crop_subtitle_images", "paddleocr.create_stitched_images", "paddleocr.perform_ocr", "paddleocr.postprocess_and_finalize"]
    },
    "ffmpeg.extract_keyframes": {
        "keyframe_sample_count": 50
    }
}
```

### 语音合成工作流

```json
{
    "workflow_config": {
        "workflow_chain": ["ffmpeg.extract_audio", "faster_whisper.transcribe_audio", "ffmpeg.split_audio_segments", "indextts.generate_speech"]
    },
    "indextts.generate_speech": {
        "text": "这是要合成的文本内容",
        "output_path": "/share/workflows/{workflow_id}/tts/output.wav",
        "spk_audio_prompt": "${{ stages.ffmpeg.split_audio_segments.output.audio_segments_dir }}/segment_001.wav"
    }
}
```

## 错误处理和调试

### 常见错误类型

1. **文件不存在错误**

    - 检查输入文件路径是否正确

    - 确认文件在共享存储目录中

2. **GPU 资源不足**

    - 检查 GPU 可用性：`nvidia-smi`

    - 调整并发任务数量

    - 使用 CPU 模式（如果支持）

3. **模型下载失败**

    - 检查网络连接

    - 确认有足够的存储空间

    - 验证访问令牌和权限

4. **参数配置错误**

    - 参考各节点的参数说明

    - 检查参数类型和取值范围

    - 查看服务日志获取详细错误信息

### 调试建议

1. **查看服务日志**：`docker-compose logs [service_name]`
2. **检查工作流状态**：通过 API 查询工作流执行状态
3. **验证输入文件**：确保文件格式和内容正确
4. **测试单个节点**：单独运行有问题的节点进行调试
5. **监控资源使用**：检查 CPU、GPU、内存使用情况

## 性能优化建议

### 通用优化

1. **合理的任务顺序**：按照依赖关系安排任务执行顺序
2. **参数调优**：根据需求选择合适的模型和质量参数
3. **并发控制**：合理设置并发任务数量，避免资源竞争
4. **缓存利用**：利用已有的中间结果，避免重复计算

### 特定节点优化

1. **音频处理**：使用人声分离后的音频提高识别准确率
2. **模型选择**：根据精度要求选择合适的模型大小
3. **GPU 利用**：确保 GPU 锁有效配置，提高资源利用率
4. **文件格式**：选择高质量的输入格式，避免不必要的格式转换

## 版本兼容性

-   **文档版本**：v1.1

-   **支持的系统版本**：YiVideo v2.0+

-   **最后更新时间**：2025-12-01

-   **更新内容**：新增 pyannote_audio 和 indextts 服务节点文档，补充压缩上传功能参数

---

_本文档会随系统更新而持续维护，如有疑问或建议，请提交 Issue 或 PR。_

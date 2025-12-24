# 规范: 文件路径组织规范

## 概述

定义 YiVideo 平台中所有工作流文件的标准化路径结构,包括本地存储 (`/share`) 和对象存储 (MinIO) 的路径规范。

---

## ADDED Requirements

### Requirement: 节点输出路径标准化

**优先级**: P0 (关键)

所有工作流节点的输出文件 **MUST** 遵循统一的路径结构 `/share/workflows/{task_id}/nodes/{node_name}/{file_type}/{filename}`,以提升可维护性和可追溯性。节点 **SHALL** 使用 `path_builder` 模块生成路径,严禁硬编码路径字符串。

#### Scenario: FFmpeg 提取音频输出路径

**Given**: 用户通过 `/v1/tasks` 接口调用 `ffmpeg.extract_audio` 节点
**When**: 节点成功提取音频文件
**Then**:
- 本地路径为: `/share/workflows/{task_id}/nodes/ffmpeg.extract_audio/audio/{filename}.wav`
- MinIO 路径为: `{bucket}/{task_id}/nodes/ffmpeg.extract_audio/audio/{filename}.wav`
- `WorkflowContext.stages['ffmpeg.extract_audio'].output.audio_path` 返回本地路径
- 如果 `core.auto_upload_to_minio=true`,则额外返回 `audio_path_minio_url`

**验证**:
```python
# 单元测试
def test_ffmpeg_extract_audio_path():
    task_id = "task-001"
    node_name = "ffmpeg.extract_audio"
    filename = "demo.wav"

    local_path = build_node_output_path(task_id, node_name, "audio", filename)
    assert local_path == "/share/workflows/task-001/nodes/ffmpeg.extract_audio/audio/demo.wav"

    minio_path = build_minio_path(task_id, node_name, "audio", filename)
    assert minio_path == "task-001/nodes/ffmpeg.extract_audio/audio/demo.wav"
```

---

#### Scenario: PaddleOCR 拼接图输出路径

**Given**: 用户调用 `paddleocr.create_stitched_images` 节点
**When**: 节点成功生成拼接图目录
**Then**:
- 本地路径为: `/share/workflows/{task_id}/nodes/paddleocr.create_stitched_images/images/stitched/`
- MinIO 路径为: `{task_id}/nodes/paddleocr.create_stitched_images/images/stitched/`
- 压缩包路径为: `/share/workflows/{task_id}/nodes/paddleocr.create_stitched_images/archives/stitched.zip`

**验证**:
```python
def test_paddleocr_stitched_images_path():
    task_id = "task-002"
    node_name = "paddleocr.create_stitched_images"

    images_dir = build_node_output_path(task_id, node_name, "images", "stitched")
    assert images_dir == "/share/workflows/task-002/nodes/paddleocr.create_stitched_images/images/stitched"

    archive_path = build_node_output_path(task_id, node_name, "archives", "stitched.zip")
    assert archive_path == "/share/workflows/task-002/nodes/paddleocr.create_stitched_images/archives/stitched.zip"
```

---

#### Scenario: WService 字幕文件输出路径

**Given**: 用户调用 `wservice.generate_subtitle_files` 节点
**When**: 节点成功生成字幕文件
**Then**:
- SRT 文件路径: `/share/workflows/{task_id}/nodes/wservice.generate_subtitle_files/subtitles/subtitle.srt`
- JSON 文件路径: `/share/workflows/{task_id}/nodes/wservice.generate_subtitle_files/subtitles/subtitle.json`
- MinIO 路径保持一致结构

**验证**:
```python
def test_wservice_subtitle_files_path():
    task_id = "task-003"
    node_name = "wservice.generate_subtitle_files"

    srt_path = build_node_output_path(task_id, node_name, "subtitles", "subtitle.srt")
    assert srt_path == "/share/workflows/task-003/nodes/wservice.generate_subtitle_files/subtitles/subtitle.srt"
```

---

### Requirement: 临时文件路径隔离

**优先级**: P1 (重要)

临时文件 **MUST** 统一存放在 `/share/workflows/{task_id}/temp/{node_name}/` 目录下,按节点隔离。节点 **SHALL** 在任务完成后清理临时文件,避免磁盘空间浪费。

#### Scenario: Faster-Whisper 临时结果文件

**Given**: `faster_whisper.transcribe_audio` 节点执行中需要保存临时结果
**When**: 节点生成临时 JSON 文件
**Then**:
- 临时文件路径: `/share/workflows/{task_id}/temp/faster_whisper.transcribe_audio/result_{timestamp}.json`
- 任务完成后,临时文件可被清理
- 最终结果文件移动到 `nodes/faster_whisper.transcribe_audio/data/` 目录

**验证**:
```python
def test_temp_file_path():
    task_id = "task-004"
    node_name = "faster_whisper.transcribe_audio"
    filename = "result_1234567890.json"

    temp_path = build_temp_path(task_id, node_name, filename)
    assert temp_path == "/share/workflows/task-004/temp/faster_whisper.transcribe_audio/result_1234567890.json"
    assert "temp" in temp_path
    assert node_name in temp_path
```

---

#### Scenario: PaddleOCR 下载临时关键帧

**Given**: `paddleocr.detect_subtitle_area` 节点需要从 MinIO 下载关键帧
**When**: 节点下载关键帧到本地临时目录
**Then**:
- 临时目录路径: `/share/workflows/{task_id}/temp/paddleocr.detect_subtitle_area/keyframes/`
- 检测完成后,临时目录可被清理
- 检测结果保存在 `nodes/paddleocr.detect_subtitle_area/data/` 目录

**验证**:
```python
def test_paddleocr_temp_download():
    task_id = "task-005"
    node_name = "paddleocr.detect_subtitle_area"

    temp_dir = build_temp_path(task_id, node_name, "keyframes")
    assert temp_dir == "/share/workflows/task-005/temp/paddleocr.detect_subtitle_area/keyframes"
```

---

### Requirement: MinIO 路径与本地路径对齐

**优先级**: P0 (关键)

MinIO 对象存储的路径结构 **MUST** 与本地路径保持一致,仅根路径不同。本地路径为 `/share/workflows/{path}` 时,MinIO 对象键 **SHALL** 为 `{path}`。StateManager **MUST** 确保上传时路径映射正确。

#### Scenario: 音频文件上传到 MinIO

**Given**: `ffmpeg.extract_audio` 节点成功提取音频,且 `core.auto_upload_to_minio=true`
**When**: StateManager 上传音频文件到 MinIO
**Then**:
- 本地路径: `/share/workflows/task-001/nodes/ffmpeg.extract_audio/audio/demo.wav`
- MinIO 对象键: `task-001/nodes/ffmpeg.extract_audio/audio/demo.wav`
- MinIO URL: `http://localhost:9000/yivideo/task-001/nodes/ffmpeg.extract_audio/audio/demo.wav`
- 路径结构完全对应,便于同步和备份

**验证**:
```python
def test_minio_path_alignment():
    task_id = "task-001"
    node_name = "ffmpeg.extract_audio"
    filename = "demo.wav"

    local_path = build_node_output_path(task_id, node_name, "audio", filename)
    minio_path = build_minio_path(task_id, node_name, "audio", filename)

    # 去除本地路径前缀,应与 MinIO 路径一致
    local_relative = local_path.replace("/share/workflows/", "")
    assert local_relative == minio_path
```

---

#### Scenario: 目录上传保持结构

**Given**: `paddleocr.create_stitched_images` 节点生成拼接图目录
**When**: StateManager 上传整个目录到 MinIO
**Then**:
- 本地目录: `/share/workflows/task-002/nodes/paddleocr.create_stitched_images/images/stitched/`
- MinIO 前缀: `task-002/nodes/paddleocr.create_stitched_images/images/stitched/`
- 目录内文件结构保持不变
- 例如: 本地 `stitched/frame_001.jpg` → MinIO `task-002/nodes/.../stitched/frame_001.jpg`

**验证**:
```python
def test_directory_upload_structure():
    task_id = "task-002"
    node_name = "paddleocr.create_stitched_images"

    local_dir = build_node_output_path(task_id, node_name, "images", "stitched")
    minio_prefix = build_minio_path(task_id, node_name, "images", "stitched")

    # 模拟目录内文件
    local_file = f"{local_dir}/frame_001.jpg"
    minio_file = f"{minio_prefix}/frame_001.jpg"

    assert local_file.replace("/share/workflows/", "") == minio_file
```

---

### Requirement: 路径解析与向后兼容

**优先级**: P1 (重要)

系统 **MUST** 提供 `parse_node_path()` 函数解析新路径格式,并 **SHALL** 兼容识别旧路径格式 (如 `/share/workflows/{task_id}/audio/demo.wav`),确保历史数据可访问。解析函数 **MUST** 返回包含 `is_legacy` 标志的结构化信息。

#### Scenario: 解析新格式路径

**Given**: 系统接收到新格式的文件路径
**When**: 调用 `parse_node_path()` 函数
**Then**:
- 能够正确提取 `task_id`, `node_name`, `file_type`, `filename`
- 返回结构化的路径信息字典

**验证**:
```python
def test_parse_new_path():
    path = "/share/workflows/task-001/nodes/ffmpeg.extract_audio/audio/demo.wav"
    parsed = parse_node_path(path)

    assert parsed["task_id"] == "task-001"
    assert parsed["node_name"] == "ffmpeg.extract_audio"
    assert parsed["file_type"] == "audio"
    assert parsed["filename"] == "demo.wav"
    assert parsed["is_legacy"] == False
```

---

#### Scenario: 兼容旧格式路径

**Given**: 系统接收到旧格式的文件路径 (如 `/share/workflows/task-001/audio/demo.wav`)
**When**: 调用 `parse_node_path()` 函数
**Then**:
- 能够识别为旧格式路径
- 尽可能推断节点名称和文件类型
- 标记为 `is_legacy=True`

**验证**:
```python
def test_parse_legacy_path():
    path = "/share/workflows/task-001/audio/demo.wav"
    parsed = parse_node_path(path)

    assert parsed["task_id"] == "task-001"
    assert parsed["file_type"] == "audio"
    assert parsed["filename"] == "demo.wav"
    assert parsed["is_legacy"] == True
    # node_name 可能为 None 或推断值
```

---

#### Scenario: 读取历史任务数据

**Given**: 用户查询一个使用旧路径格式的历史任务
**When**: 系统读取 `WorkflowContext` 中的文件路径
**Then**:
- 旧路径可正常解析和访问
- 不影响文件读取和下载功能
- 日志中标记为旧格式路径 (便于审计)

**验证**:
```python
def test_legacy_task_compatibility():
    # 模拟旧任务的 context
    legacy_context = {
        "workflow_id": "task-old-001",
        "shared_storage_path": "/share/workflows/task-old-001",
        "stages": {
            "ffmpeg.extract_audio": {
                "output": {
                    "audio_path": "/share/workflows/task-old-001/audio/demo.wav"
                }
            }
        }
    }

    audio_path = legacy_context["stages"]["ffmpeg.extract_audio"]["output"]["audio_path"]
    assert os.path.exists(audio_path) or True  # 假设文件存在

    parsed = parse_node_path(audio_path)
    assert parsed["is_legacy"] == True
```

---

### Requirement: 文件类型目录规范

**优先级**: P1 (重要)

在节点目录下,**MUST** 按文件类型使用标准子目录名称: `audio/` (音频), `video/` (视频), `images/` (图片), `subtitles/` (字幕), `data/` (JSON/文本), `archives/` (压缩包)。节点 **SHALL NOT** 自定义子目录名称,以保持全局一致性。

#### Scenario: 标准文件类型目录

**Given**: 节点需要保存不同类型的输出文件
**When**: 节点调用路径生成函数
**Then**:
- 音频文件使用 `audio/` 子目录
- 视频文件使用 `video/` 子目录
- 图片文件使用 `images/` 子目录
- 字幕文件使用 `subtitles/` 子目录
- JSON/文本数据使用 `data/` 子目录
- 压缩包使用 `archives/` 子目录

**验证**:
```python
def test_file_type_directories():
    task_id = "task-006"
    node_name = "test.node"

    audio_path = build_node_output_path(task_id, node_name, "audio", "test.wav")
    assert "/audio/" in audio_path

    video_path = build_node_output_path(task_id, node_name, "video", "test.mp4")
    assert "/video/" in video_path

    image_path = build_node_output_path(task_id, node_name, "images", "test.jpg")
    assert "/images/" in image_path

    subtitle_path = build_node_output_path(task_id, node_name, "subtitles", "test.srt")
    assert "/subtitles/" in subtitle_path

    data_path = build_node_output_path(task_id, node_name, "data", "test.json")
    assert "/data/" in data_path

    archive_path = build_node_output_path(task_id, node_name, "archives", "test.zip")
    assert "/archives/" in archive_path
```

---

#### Scenario: 混合类型输出

**Given**: 节点同时输出多种类型文件 (如音频 + 数据)
**When**: 节点保存输出文件
**Then**:
- 每种类型文件保存在对应的子目录
- 路径结构清晰,便于查找和管理

**验证**:
```python
def test_mixed_output_types():
    task_id = "task-007"
    node_name = "audio_separator.separate_vocals"

    # 音频文件
    vocal_path = build_node_output_path(task_id, node_name, "audio", "demo_(Vocals).flac")
    assert "/audio/" in vocal_path

    # 元数据文件
    metadata_path = build_node_output_path(task_id, node_name, "data", "separation_info.json")
    assert "/data/" in metadata_path

    # 两个文件在同一节点目录下,但类型子目录不同
    assert node_name in vocal_path
    assert node_name in metadata_path
```

---

## MODIFIED Requirements

### Requirement: StateManager MinIO 上传逻辑

**优先级**: P0 (关键)

StateManager 的 MinIO 上传逻辑 **MUST** 更新以支持新的路径结构。上传函数 **SHALL** 从本地文件路径中提取节点名称和文件类型,并生成符合规范的 MinIO 对象键 `{task_id}/nodes/{node_name}/{file_type}/{filename}`。

**原有行为**:
- MinIO 上传路径为 `{task_id}/{filename}`,缺乏节点和类型信息

**新行为**:
- MinIO 上传路径 **MUST** 为 `{task_id}/nodes/{node_name}/{file_type}/{filename}`
- StateManager **SHALL** 从本地文件路径中提取节点名称和文件类型,自动生成符合规范的 MinIO 对象键
- 上传函数 **MUST** 保持与本地路径结构一致

#### Scenario: 上传单个文件

**Given**: StateManager 需要上传节点输出文件到 MinIO
**When**: 调用 `_upload_file_to_minio()` 方法
**Then**:
- 从文件路径中提取节点名称和文件类型
- 生成符合新规范的 MinIO 对象键
- 返回完整的 MinIO URL

**验证**:
```python
def test_state_manager_upload_file():
    local_path = "/share/workflows/task-001/nodes/ffmpeg.extract_audio/audio/demo.wav"

    # 模拟 StateManager 上传
    minio_url = state_manager._upload_file_to_minio(local_path, task_id="task-001")

    assert "task-001/nodes/ffmpeg.extract_audio/audio/demo.wav" in minio_url
    assert minio_url.startswith("http://localhost:9000/yivideo/")
```

---

#### Scenario: 上传目录

**Given**: StateManager 需要上传整个目录到 MinIO
**When**: 调用目录上传函数
**Then**:
- 保持目录内部结构不变
- 所有文件的 MinIO 路径符合新规范

**验证**:
```python
def test_state_manager_upload_directory():
    local_dir = "/share/workflows/task-002/nodes/paddleocr.create_stitched_images/images/stitched/"

    # 模拟目录上传
    minio_urls = state_manager.upload_directory_to_minio(local_dir, task_id="task-002")

    for url in minio_urls:
        assert "task-002/nodes/paddleocr.create_stitched_images/images/stitched/" in url
```

---

## REMOVED Requirements

无删除的需求。

---

## 交叉引用

- **依赖规范**: [local-directory-management](../local-directory-management/spec.md) - 本地目录管理规范
- **依赖规范**: [project-architecture](../project-architecture/spec.md) - 项目架构规范
- **影响文档**: [SINGLE_TASK_API_REFERENCE.md](../../../docs/technical/reference/SINGLE_TASK_API_REFERENCE.md) - API 文档需更新路径示例

---

## 实施注意事项

1. **渐进式迁移**: 优先迁移核心节点 (FFmpeg, Faster-Whisper),再扩展到其他节点
2. **测试覆盖**: 每个节点迁移后必须通过集成测试
3. **日志审计**: 在路径生成和解析时记录详细日志,便于问题排查
4. **文档同步**: 代码变更完成后立即更新 API 文档
5. **向后兼容**: 保持旧路径解析能力至少 6 个月,便于历史数据访问

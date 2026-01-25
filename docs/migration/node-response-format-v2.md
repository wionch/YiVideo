# 节点响应格式迁移指南 v2.0

**版本**: 2.0
**日期**: 2025-12-23
**状态**: 已发布

## 概述

YiVideo 项目已完成所有 18 个工作流节点的响应格式统一化工作。本文档帮助客户端开发者从旧格式迁移到新的统一格式。

## 变更摘要

### 核心变更

1. **统一响应结构**: 所有节点现在都返回 `WorkflowContext` 结构
2. **MinIO URL 字段命名规范化**: 所有 MinIO URL 字段遵循 `{field_name}_minio_url` 规范
3. **状态字段统一**: 所有状态值统一为大写（`SUCCESS`, `FAILED`, `PENDING`）
4. **复用判定透明化**: 明确的缓存键字段声明

### 影响范围

- **所有 18 个节点**已迁移到新格式
- **向后兼容**: 提供 6 个月的兼容性层支持
- **废弃时间表**: 旧格式将于 2026-06-23 废弃

## 旧格式 vs 新格式对比

### 格式类型 A: WorkflowContext（大多数节点）

**旧格式** (已废弃):
```json
{
  "workflow_id": "task-001",
  "stages": {
    "ffmpeg.extract_audio": {
      "status": "SUCCESS",
      "output": {
        "audio_path": "/share/audio.wav",
        "audio_path_minio_url": "http://minio:9000/bucket/audio.wav"
      }
    }
  }
}
```

**新格式** (推荐):
```json
{
  "workflow_id": "task-001",
  "stages": {
    "ffmpeg.extract_audio": {
      "status": "SUCCESS",
      "output": {
        "audio_path": "/share/audio.wav",
        "audio_path_minio_url": "http://minio:9000/bucket/audio.wav"
      },
      "duration": 2.5
    }
  }
}
```

**变更点**:
- ✅ 结构保持一致
- ✅ 添加了 `duration` 字段（执行时长）
- ✅ MinIO URL 字段命名规范化

### 格式类型 B: success/data 结构（pyannote_audio 旧格式）

**旧格式** (已废弃):
```json
{
  "success": true,
  "data": {
    "speaker_segments": [
      {"start": 0.0, "end": 2.0, "speaker": "SPEAKER_00"}
    ]
  }
}
```

**新格式** (推荐):
```json
{
  "workflow_id": "task-001",
  "stages": {
    "pyannote_audio.get_speaker_segments": {
      "status": "SUCCESS",
      "output": {
        "speaker_segments": [
          {"start": 0.0, "end": 2.0, "speaker": "SPEAKER_00"}
        ],
        "total_segments": 1
      },
      "duration": 1.2
    }
  }
}
```

**变更点**:
- ❌ 移除 `success` 字段
- ❌ 移除 `data` 包装
- ✅ 使用标准 `WorkflowContext` 结构
- ✅ 数据位于 `stages[task_name].output`

**受影响的节点**:
- `pyannote_audio.get_speaker_segments`
- `pyannote_audio.validate_diarization`

### 格式类型 C: 普通任务字典（indextts 旧格式）

**旧格式** (已废弃):
```json
{
  "status": "success",
  "audio_path": "/share/generated.wav",
  "processing_time": 5.2
}
```

**新格式** (推荐):
```json
{
  "workflow_id": "task-001",
  "stages": {
    "indextts.generate_speech": {
      "status": "SUCCESS",
      "output": {
        "audio_path": "/share/generated.wav",
        "audio_duration": 10.5
      },
      "duration": 5.2
    }
  }
}
```

**变更点**:
- ❌ 移除顶层 `status` 字段
- ❌ 移除 `processing_time` 字段
- ✅ 使用标准 `WorkflowContext` 结构
- ✅ 状态值统一为大写 `SUCCESS`
- ✅ 执行时长移至 `duration` 字段

**受影响的节点**:
- `indextts.generate_speech`

## MinIO URL 字段命名规范

### 规则

所有 MinIO URL 字段必须遵循以下规则：

1. **保留完整前缀**: `{field_name}_minio_url`
2. **数组字段**: `{field_name}_minio_urls`（复数）
3. **不省略后缀**: 保留 `_path`, `_dir`, `_file` 等后缀

### 示例

| 本地字段名 | MinIO URL 字段名 | 状态 |
|-----------|-----------------|------|
| `audio_path` | `audio_path_minio_url` | ✅ 正确 |
| `keyframe_dir` | `keyframe_dir_minio_url` | ✅ 正确 |
| `multi_frames_path` | `multi_frames_path_minio_url` | ✅ 正确 |
| `subtitle_files` | `subtitle_files_minio_urls` | ✅ 正确（数组） |
| `audio` | `audio_minio_url` | ❌ 错误（缺少 `_path`） |
| `keyframe` | `keyframe_minio_url` | ❌ 错误（缺少 `_dir`） |

### 受影响的节点

**已修复的字段命名**:
- `paddleocr.detect_subtitle_area`: `keyframe_dir` → `keyframe_dir_minio_url`
- `paddleocr.create_stitched_images`: `multi_frames_path` → `multi_frames_path_minio_url`
- `audio_separator.separate_vocals`: `all_audio_files` → `all_audio_files_minio_urls`

## 状态字段统一

### 旧格式

```json
{
  "status": "success"  // 小写
}
```

### 新格式

```json
{
  "status": "SUCCESS"  // 大写
}
```

### 所有状态值

| 旧值 | 新值 | 说明 |
|-----|------|------|
| `success` | `SUCCESS` | 成功 |
| `failed` | `FAILED` | 失败 |
| `pending` | `PENDING` | 等待中 |
| `running` | `RUNNING` | 执行中 |
| `skipped` | `SKIPPED` | 跳过 |

## 迁移检查清单

### 客户端代码迁移

- [ ] **步骤 1**: 更新响应解析逻辑
  - [ ] 移除对 `success/data` 结构的处理
  - [ ] 移除对顶层 `status` 字段的处理
  - [ ] 使用 `stages[task_name].output` 访问结果数据

- [ ] **步骤 2**: 更新字段访问路径
  - [ ] 将 `response.data.speaker_segments` 改为 `response.stages['pyannote_audio.get_speaker_segments'].output.speaker_segments`
  - [ ] 将 `response.audio_path` 改为 `response.stages['indextts.generate_speech'].output.audio_path`

- [ ] **步骤 3**: 更新状态检查逻辑
  - [ ] 将 `status === 'success'` 改为 `status === 'SUCCESS'`
  - [ ] 将 `status === 'failed'` 改为 `status === 'FAILED'`

- [ ] **步骤 4**: 更新 MinIO URL 字段访问
  - [ ] 检查所有 MinIO URL 字段名是否符合新规范
  - [ ] 更新字段访问代码

- [ ] **步骤 5**: 测试
  - [ ] 单元测试覆盖所有节点的响应解析
  - [ ] 集成测试验证端到端流程

### 服务端配置（可选）

如果需要临时使用旧格式（不推荐）：

```python
# 在请求中添加 legacy_format 参数
response = requests.post(
    "http://localhost:8788/v1/tasks",
    json={
        "task_name": "ffmpeg.extract_audio",
        "input_data": {...},
        "legacy_format": True  # 启用旧格式兼容
    }
)
```

**注意**: `legacy_format` 参数将于 2026-06-23 移除。

## 迁移示例

### Python 客户端

**旧代码**:
```python
# 处理 pyannote_audio.get_speaker_segments 响应
response = api.call_task("pyannote_audio.get_speaker_segments", {...})
if response["success"]:
    segments = response["data"]["speaker_segments"]
    for segment in segments:
        print(f"Speaker: {segment['speaker']}")
```

**新代码**:
```python
# 处理统一的 WorkflowContext 响应
response = api.call_task("pyannote_audio.get_speaker_segments", {...})
stage = response["stages"]["pyannote_audio.get_speaker_segments"]
if stage["status"] == "SUCCESS":
    segments = stage["output"]["speaker_segments"]
    for segment in segments:
        print(f"Speaker: {segment['speaker']}")
```

### JavaScript 客户端

**旧代码**:
```javascript
// 处理 indextts.generate_speech 响应
const response = await api.callTask("indextts.generate_speech", {...});
if (response.status === "success") {
    const audioPath = response.audio_path;
    console.log(`Generated audio: ${audioPath}`);
}
```

**新代码**:
```javascript
// 处理统一的 WorkflowContext 响应
const response = await api.callTask("indextts.generate_speech", {...});
const stage = response.stages["indextts.generate_speech"];
if (stage.status === "SUCCESS") {
    const audioPath = stage.output.audio_path;
    console.log(`Generated audio: ${audioPath}`);
}
```

## 常见问题

### Q1: 旧格式何时完全废弃？

**A**: 旧格式将于 **2026-06-23** 完全废弃。在此之前，可以通过 `legacy_format=True` 参数继续使用旧格式。

### Q2: 如何检测响应格式版本？

**A**: 检查响应头中的 `X-Response-Format-Version` 字段：
- `v1`: 旧格式（已废弃）
- `v2`: 新格式（推荐）

```python
response = requests.post(...)
version = response.headers.get("X-Response-Format-Version", "v1")
if version == "v2":
    # 使用新格式解析
    pass
```

### Q3: 所有节点都需要迁移吗？

**A**: 是的。所有 18 个节点都已迁移到新格式。如果您的客户端使用了以下节点，需要更新代码：

**必须迁移的节点**:
- `pyannote_audio.get_speaker_segments` (success/data → WorkflowContext)
- `pyannote_audio.validate_diarization` (success/data → WorkflowContext)
- `indextts.generate_speech` (普通字典 → WorkflowContext)

**建议检查的节点**:
- 所有 `paddleocr.*` 节点（MinIO URL 字段命名）
- 所有 `wservice.*` 节点（数据溯源字段）

### Q4: 如何验证我的客户端代码是否兼容新格式？

**A**: 运行以下测试：

```python
# 测试脚本
import requests

def test_node_response_format(task_name, input_data):
    response = requests.post(
        "http://localhost:8788/v1/tasks",
        json={
            "task_name": task_name,
            "task_id": f"test-{task_name}",
            "input_data": input_data
        }
    )

    result = response.json()

    # 验证 WorkflowContext 结构
    assert "workflow_id" in result
    assert "stages" in result
    assert task_name in result["stages"]

    # 验证状态字段
    stage = result["stages"][task_name]
    assert stage["status"] in ["SUCCESS", "FAILED", "PENDING", "RUNNING"]

    # 验证输出字段
    assert "output" in stage

    print(f"✅ {task_name} 响应格式验证通过")

# 测试所有节点
test_node_response_format("ffmpeg.extract_audio", {"video_path": "..."})
test_node_response_format("pyannote_audio.get_speaker_segments", {...})
# ... 测试其他节点
```

### Q5: 迁移过程中遇到问题怎么办？

**A**:
1. 检查 `X-Response-Format-Version` 响应头确认格式版本
2. 查看服务端日志中的格式验证错误
3. 使用 `legacy_format=True` 临时回退到旧格式
4. 联系技术支持团队

## 技术支持

如有疑问，请联系：
- **GitHub Issues**: https://github.com/your-org/yivideo/issues
- **技术文档**: `/docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
- **集成测试**: `/tests/integration/test_node_response_format.py`

## 附录

### 完整节点列表

所有 18 个已迁移节点：

**FFmpeg 系列** (2个):
1. `ffmpeg.extract_audio`
2. `ffmpeg.extract_keyframes`

**Faster-Whisper** (1个):
3. `faster_whisper.transcribe_audio`

**Audio Separator** (1个):
4. `audio_separator.separate_vocals`

**Pyannote Audio 系列** (3个):
5. `pyannote_audio.diarize_speakers`
6. `pyannote_audio.get_speaker_segments` ⚠️ 格式变更
7. `pyannote_audio.validate_diarization` ⚠️ 格式变更

**PaddleOCR 系列** (4个):
8. `paddleocr.detect_subtitle_area`
9. `paddleocr.create_stitched_images` ⚠️ 字段命名变更
10. `paddleocr.perform_ocr`
11. `paddleocr.postprocess_and_finalize`

**IndexTTS** (1个):
12. `indextts.generate_speech` ⚠️ 格式变更

**WService 系列** (7个):
13. `wservice.generate_subtitle_files`
14. `wservice.correct_subtitles`
15. `wservice.ai_optimize_text`
16. `wservice.rebuild_subtitle_with_words`
17. `wservice.merge_speaker_segments`
18. `wservice.merge_with_word_timestamps`
19. `wservice.prepare_tts_segments`

### 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v2.1 | 2026-01-25 | 新增纯文本纠错与词级重构节点，更新至 19 个节点 |
| v2.0 | 2025-12-23 | 所有 18 个节点迁移完成 |
| v1.0 | 2024-01-01 | 初始版本（已废弃） |

---

**最后更新**: 2026-01-25
**文档版本**: 2.1
**维护者**: YiVideo 开发团队

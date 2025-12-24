# Capability: 缓存键策略 (Cache Key Strategy)

## ADDED Requirements

### Requirement: 每个节点必须显式声明缓存键字段

**优先级**: P0
**理由**: 消除复用判定逻辑的不透明性，确保缓存行为可预测

#### Scenario: 节点声明缓存键字段

**Given** 开发者实现一个新的 FFmpeg 音频提取节点
**When** 继承 `BaseNodeExecutor` 并实现 `get_cache_key_fields()` 方法
**Then** 必须返回用于生成缓存键的字段列表

**示例**:
```python
class FFmpegExtractAudioExecutor(BaseNodeExecutor):
    def get_cache_key_fields(self) -> List[str]:
        """
        音频提取的缓存键仅依赖输入视频路径。
        相同的视频路径会复用之前的提取结果。
        """
        return ["video_path"]
```

#### Scenario: 多字段组合缓存键

**Given** 节点的输出依赖多个输入参数
**When** 声明缓存键字段
**Then** 必须包含所有影响输出的字段

**示例**:
```python
class FasterWhisperTranscribeExecutor(BaseNodeExecutor):
    def get_cache_key_fields(self) -> List[str]:
        """
        转录结果依赖音频路径和模型配置。
        不同的模型或参数会产生不同的转录结果。
        """
        return [
            "audio_path",
            "model_name",
            "enable_word_timestamps"
        ]
```

---

### Requirement: 缓存键生成必须稳定且唯一

**优先级**: P0
**理由**: 确保相同输入总是生成相同的缓存键

#### Scenario: 生成稳定的缓存键

**Given** 节点的缓存键字段为 `["audio_path", "model_name"]`
**And** 输入参数为:
```python
{
    "audio_path": "/share/audio.wav",
    "model_name": "base"
}
```
**When** 生成缓存键
**Then** 缓存键必须为稳定的哈希值:
```
faster_whisper.transcribe_audio:5f4dcc3b5aa765d61d8327deb882cf99
```

**And** 相同的输入参数必须总是生成相同的缓存键
**And** 参数顺序不影响缓存键（使用排序后的 JSON）

#### Scenario: 不同输入生成不同缓存键

**Given** 两组不同的输入参数:
- 输入 A: `{"audio_path": "/share/audio1.wav"}`
- 输入 B: `{"audio_path": "/share/audio2.wav"}`

**When** 分别生成缓存键
**Then** 缓存键必须不同:
- 缓存键 A: `task_name:hash_a`
- 缓存键 B: `task_name:hash_b`

**And** `hash_a != hash_b`

---

### Requirement: 复用判定必须基于缓存键和输出完整性

**优先级**: P0
**理由**: 确保复用的结果是有效的

#### Scenario: 检查缓存命中条件

**Given** 缓存键为 `ffmpeg.extract_audio:abc123`
**And** Redis 中存在该键对应的 `StageExecution` 记录
**When** 检查是否可以复用
**Then** 必须满足以下所有条件:
1. `StageExecution.status == "SUCCESS"`
2. `StageExecution.output` 非空
3. 关键输出字段存在且非空（由节点定义）

**And** 如果任一条件不满足，不复用缓存

#### Scenario: 定义关键输出字段

**Given** 节点需要验证特定输出字段的存在性
**When** 实现 `get_required_output_fields()` 方法
**Then** 返回必须存在的输出字段列表

**示例**:
```python
class FFmpegExtractAudioExecutor(BaseNodeExecutor):
    def get_required_output_fields(self) -> List[str]:
        """
        音频提取必须产生 audio_path 字段。
        如果该字段不存在或为空，缓存无效。
        """
        return ["audio_path"]
```

**复用判定逻辑**:
```python
def can_reuse_cache(stage: StageExecution, required_fields: List[str]) -> bool:
    if stage.status != "SUCCESS":
        return False

    if not stage.output:
        return False

    for field in required_fields:
        if field not in stage.output or not stage.output[field]:
            return False

    return True
```

---

### Requirement: 等待态缓存必须返回 pending 状态

**优先级**: P0
**理由**: 避免重复调度相同任务

#### Scenario: 检测到等待态缓存

**Given** 缓存键为 `ffmpeg.extract_audio:abc123`
**And** Redis 中存在该键对应的 `StageExecution` 记录
**And** `StageExecution.status == "PENDING"` 或 `"RUNNING"`
**When** 检查缓存
**Then** 不调度新任务
**And** 同步响应返回:
```python
{
    "task_id": "task-001",
    "status": "pending",
    "message": "任务已在执行中，请等待",
    "reuse_info": {
        "reuse_hit": true,
        "state": "pending",
        "task_name": "ffmpeg.extract_audio"
    }
}
```

---

### Requirement: 成功缓存复用必须触发回调

**优先级**: P0
**理由**: 确保客户端收到结果通知

#### Scenario: 复用成功缓存并发送回调

**Given** 缓存键命中成功的 `StageExecution` 记录
**And** 请求包含新的 `callback` URL
**When** 复用缓存
**Then** 必须使用新的 `callback` URL 发送回调
**And** 回调载荷包含完整的 `WorkflowContext`
**And** 同步响应返回:
```python
{
    "task_id": "task-001",
    "status": "completed",
    "message": "任务已命中缓存并完成回调",
    "reuse_info": {
        "reuse_hit": true,
        "task_name": "ffmpeg.extract_audio",
        "source": "redis",
        "cached_at": "2025-12-17T12:00:03Z"
    },
    "result": { ...完整 WorkflowContext... }
}
```

---

## MODIFIED Requirements

### Requirement: 现有节点的复用判定逻辑必须迁移到缓存键策略

**优先级**: P0
**理由**: 统一复用判定机制

#### Scenario: 迁移 ffmpeg.extract_audio 的复用逻辑

**Given** 现有节点使用隐式判定逻辑:
```python
# 旧代码：隐式检查 output.audio_path
if context.stages.get("ffmpeg.extract_audio", {}).get("output", {}).get("audio_path"):
    # 复用缓存
    pass
```

**When** 迁移到缓存键策略
**Then** 必须显式声明:
```python
class FFmpegExtractAudioExecutor(BaseNodeExecutor):
    def get_cache_key_fields(self) -> List[str]:
        return ["video_path"]

    def get_required_output_fields(self) -> List[str]:
        return ["audio_path"]
```

**And** 复用判定逻辑由 `CacheManager` 统一处理

#### Scenario: 修复文档与实现不一致的问题

**Given** 文档说明 `wservice.merge_speaker_segments` 检查 `output.merged_subtitle_path`
**And** 实际输出中只有 `merged_segments` 数组
**When** 迁移到缓存键策略
**Then** 必须修正为:
```python
class MergeSpeakerSegmentsExecutor(BaseNodeExecutor):
    def get_required_output_fields(self) -> List[str]:
        return ["merged_segments"]  # 实际输出字段
```

**And** 更新文档以匹配实现

---

## REMOVED Requirements

无（这是新增能力）

---

## 依赖关系

- **依赖**: `services/common/context.py` 中的 `WorkflowContext` 和 `StageExecution` 模型
- **依赖**: Redis 缓存存储
- **被依赖**: `BaseNodeExecutor.execute()` 方法
- **被依赖**: `single_task_api.py` 中的任务调度逻辑

---

## 测试要求

### 单元测试

1. **测试缓存键生成稳定性**:
   ```python
   def test_cache_key_stability():
       strategy = CacheKeyStrategy()
       input_params = {"audio_path": "/share/audio.wav", "model_name": "base"}

       key1 = strategy.generate_cache_key("task_name", input_params)
       key2 = strategy.generate_cache_key("task_name", input_params)

       assert key1 == key2  # 相同输入生成相同键
   ```

2. **测试参数顺序无关性**:
   ```python
   def test_cache_key_order_independence():
       strategy = CacheKeyStrategy()

       input1 = {"a": 1, "b": 2}
       input2 = {"b": 2, "a": 1}  # 顺序不同

       key1 = strategy.generate_cache_key("task_name", input1)
       key2 = strategy.generate_cache_key("task_name", input2)

       assert key1 == key2  # 顺序不影响键
   ```

3. **测试复用判定逻辑**:
   ```python
   def test_can_reuse_cache():
       # 成功且输出完整
       stage_success = StageExecution(
           status="SUCCESS",
           output={"audio_path": "/share/audio.wav"}
       )
       assert can_reuse_cache(stage_success, ["audio_path"]) == True

       # 成功但输出缺失
       stage_missing = StageExecution(
           status="SUCCESS",
           output={}
       )
       assert can_reuse_cache(stage_missing, ["audio_path"]) == False

       # 失败状态
       stage_failed = StageExecution(
           status="FAILED",
           output={"audio_path": "/share/audio.wav"}
       )
       assert can_reuse_cache(stage_failed, ["audio_path"]) == False
   ```

4. **测试等待态检测**:
   ```python
   def test_pending_state_detection():
       stage_pending = StageExecution(status="PENDING", output={})
       assert is_pending_state(stage_pending) == True

       stage_running = StageExecution(status="RUNNING", output={})
       assert is_pending_state(stage_running) == True

       stage_success = StageExecution(status="SUCCESS", output={})
       assert is_pending_state(stage_success) == False
   ```

### 集成测试

1. **测试缓存复用流程**:
   ```python
   def test_cache_reuse_flow():
       # 第一次执行：创建缓存
       context1 = execute_task("ffmpeg.extract_audio", {"video_path": "/share/video.mp4"})
       assert context1.stages["ffmpeg.extract_audio"].status == "SUCCESS"

       # 第二次执行：复用缓存
       response2 = submit_task("ffmpeg.extract_audio", {"video_path": "/share/video.mp4"})
       assert response2["status"] == "completed"
       assert response2["reuse_info"]["reuse_hit"] == True
   ```

2. **测试等待态缓存**:
   ```python
   def test_pending_cache():
       # 启动长时间运行的任务
       task1 = submit_task_async("ffmpeg.extract_audio", {"video_path": "/share/large_video.mp4"})

       # 立即提交相同任务
       response2 = submit_task("ffmpeg.extract_audio", {"video_path": "/share/large_video.mp4"})

       assert response2["status"] == "pending"
       assert response2["reuse_info"]["state"] == "pending"
   ```

3. **测试回调触发**:
   ```python
   def test_cache_reuse_callback():
       # 第一次执行
       execute_task("ffmpeg.extract_audio", {"video_path": "/share/video.mp4"})

       # 第二次执行，使用新的回调 URL
       callback_url = "http://localhost:5678/webhook/test"
       submit_task("ffmpeg.extract_audio", {
           "video_path": "/share/video.mp4",
           "callback": callback_url
       })

       # 验证回调被发送到新 URL
       assert callback_received(callback_url) == True
   ```

---

## 性能要求

- 缓存键生成时间 < 5ms
- Redis 缓存查询时间 < 10ms
- 复用判定逻辑时间 < 5ms

---

## 配置要求

### Redis 缓存配置

```yaml
# config.yml
cache:
  redis_db: 3  # 使用 DB3 存储缓存
  ttl: 86400   # 缓存有效期 24 小时
  key_prefix: "yivideo:cache:"
```

### 缓存键格式

```
yivideo:cache:{task_name}:{hash}
```

示例:
```
yivideo:cache:ffmpeg.extract_audio:5f4dcc3b5aa765d61d8327deb882cf99
```

---

## 文档要求

### 缓存键字段参考文档

创建 `docs/development/cache-key-fields-reference.md`，列出所有节点的缓存键字段:

| 节点名称 | 缓存键字段 | 必需输出字段 | 说明 |
|---------|-----------|-------------|------|
| `ffmpeg.extract_audio` | `["video_path"]` | `["audio_path"]` | 相同视频复用音频提取结果 |
| `faster_whisper.transcribe_audio` | `["audio_path", "model_name", "enable_word_timestamps"]` | `["segments_file"]` | 模型或参数不同会重新转录 |
| `pyannote_audio.diarize_speakers` | `["audio_path", "use_paid_api"]` | `["diarization_file"]` | 付费/免费接口结果不同 |
| ... | ... | ... | ... |

### 复用判定流程图

```
┌─────────────────┐
│  收到任务请求    │
└────────┬────────┘
         │
         ▼
┌─────────────────────────┐
│ 生成缓存键              │
│ (基于 cache_key_fields) │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│ 查询 Redis 缓存         │
└────────┬────────────────┘
         │
         ├─ 缓存不存在 ──→ 调度新任务
         │
         ├─ 缓存状态 = PENDING/RUNNING ──→ 返回等待态
         │
         └─ 缓存状态 = SUCCESS
                  │
                  ▼
         ┌─────────────────────────┐
         │ 检查必需输出字段        │
         │ (required_output_fields)│
         └────────┬────────────────┘
                  │
                  ├─ 字段缺失/为空 ──→ 调度新任务
                  │
                  └─ 字段完整
                           │
                           ▼
                  ┌─────────────────┐
                  │ 复用缓存        │
                  │ 发送回调        │
                  │ 返回结果        │
                  └─────────────────┘
```

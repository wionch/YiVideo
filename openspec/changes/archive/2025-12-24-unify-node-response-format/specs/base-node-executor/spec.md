# Capability: 基础节点执行器 (Base Node Executor)

## ADDED Requirements

### Requirement: 所有节点必须继承 BaseNodeExecutor 抽象基类

**优先级**: P0
**理由**: 确保所有节点遵循统一的执行流程和响应格式

#### Scenario: 创建新的 FFmpeg 音频提取节点

**Given** 开发者需要实现一个新的 FFmpeg 音频提取节点
**When** 创建节点执行器类
**Then** 该类必须继承 `BaseNodeExecutor` 抽象基类
**And** 必须实现以下抽象方法:
- `validate_input()`: 验证输入参数
- `execute_core_logic()`: 执行核心业务逻辑
- `get_cache_key_fields()`: 返回缓存键字段列表

**示例代码**:
```python
from services.common.base_node_executor import BaseNodeExecutor

class FFmpegExtractAudioExecutor(BaseNodeExecutor):
    def validate_input(self) -> None:
        if "video_path" not in self.context.input_params.get("input_data", {}):
            raise ValueError("Missing required parameter: video_path")

    def execute_core_logic(self) -> Dict[str, Any]:
        # 实现音频提取逻辑
        video_path = self._resolve_video_path()
        audio_path = self._extract_audio(video_path)
        return {"audio_path": audio_path}

    def get_cache_key_fields(self) -> List[str]:
        return ["video_path"]
```

#### Scenario: 节点执行自动应用统一流程

**Given** 一个继承了 `BaseNodeExecutor` 的节点执行器
**When** 调用 `execute()` 方法
**Then** 执行流程必须按以下顺序进行:
1. 调用 `validate_input()` 验证输入
2. 调用 `execute_core_logic()` 执行核心逻辑
3. 调用 `format_output()` 格式化输出（应用 MinIO URL 约定）
4. 更新 `WorkflowContext.stages[task_name]` 为 `StageExecution` 对象
5. 返回更新后的 `WorkflowContext`

**And** 如果任何步骤抛出异常:
- 捕获异常并记录到 `StageExecution.error`
- 设置 `StageExecution.status = "FAILED"`
- 设置 `WorkflowContext.error` 为错误摘要
- 仍然返回 `WorkflowContext`（不向上抛出异常）

#### Scenario: 节点执行记录时长信息

**Given** 一个节点执行器开始执行
**When** 执行完成（无论成功或失败）
**Then** `StageExecution.duration` 字段必须记录执行耗时（秒）
**And** 耗时精度至少为 0.1 秒

---

### Requirement: BaseNodeExecutor 必须提供默认的输出格式化逻辑

**优先级**: P0
**理由**: 避免每个节点重复实现 MinIO URL 生成逻辑

#### Scenario: 自动生成 MinIO URL 字段

**Given** 节点的 `execute_core_logic()` 返回包含本地路径的输出字典:
```python
{
    "audio_path": "/share/workflows/task-001/audio.wav",
    "keyframe_dir": "/share/workflows/task-001/keyframes"
}
```
**And** 全局配置 `core.auto_upload_to_minio = true`
**When** `BaseNodeExecutor.format_output()` 被调用
**Then** 输出字典必须被增强为:
```python
{
    "audio_path": "/share/workflows/task-001/audio.wav",
    "audio_path_minio_url": "http://localhost:9000/yivideo/task-001/audio.wav",
    "keyframe_dir": "/share/workflows/task-001/keyframes",
    "keyframe_dir_minio_url": "http://localhost:9000/yivideo/task-001/keyframes/"
}
```
**And** 原始本地路径字段不被覆盖或删除

#### Scenario: 子类可以覆盖格式化逻辑

**Given** 某个节点需要自定义输出格式化逻辑
**When** 该节点覆盖 `format_output()` 方法
**Then** 自定义逻辑必须被执行
**And** 仍然可以调用 `super().format_output()` 以复用默认逻辑

---

### Requirement: BaseNodeExecutor 必须提取并记录输入参数快照

**优先级**: P1
**理由**: 便于调试和审计，了解节点执行时的实际输入

#### Scenario: 记录输入参数到 StageExecution

**Given** 节点执行时的输入参数为:
```python
{
    "input_data": {
        "video_path": "http://example.com/video.mp4",
        "sample_rate": 16000
    }
}
```
**When** 节点执行完成
**Then** `StageExecution.input_params` 必须包含实际使用的参数快照
**And** 如果参数来自智能回退，必须记录最终解析后的值
**And** 敏感信息（如 API 密钥）必须被脱敏（替换为 `***`）

---

## MODIFIED Requirements

### Requirement: 现有节点必须迁移到 BaseNodeExecutor

**优先级**: P0
**理由**: 确保所有节点统一

#### Scenario: 迁移 pyannote_audio.get_speaker_segments 节点

**Given** 现有节点返回简化的 `success/data` 格式:
```python
{
    "success": true,
    "data": {"segments": [...]},
    "summary": "..."
}
```
**When** 迁移到 `BaseNodeExecutor`
**Then** 必须返回完整的 `WorkflowContext` 结构
**And** `data` 内容必须移动到 `StageExecution.output`
**And** `summary` 可以作为 `output` 中的一个字段保留

**迁移前**:
```python
def get_speaker_segments_task(context: dict) -> dict:
    # ... 逻辑 ...
    return {"success": True, "data": {...}}
```

**迁移后**:
```python
class GetSpeakerSegmentsExecutor(BaseNodeExecutor):
    def execute_core_logic(self) -> Dict[str, Any]:
        # ... 逻辑 ...
        return {
            "segments": [...],
            "summary": "..."
        }
```

---

## REMOVED Requirements

无（这是新增能力）

---

## 依赖关系

- **依赖**: `services/common/context.py` 中的 `WorkflowContext` 和 `StageExecution` 模型
- **依赖**: `services/common/minio_url_convention.py`（MinIO URL 命名约定）
- **被依赖**: 所有 18 个工作流节点

---

## 测试要求

### 单元测试

1. **测试抽象方法强制实现**:
   - 尝试实例化未实现抽象方法的子类，必须抛出 `TypeError`

2. **测试执行流程顺序**:
   - Mock 各个方法，验证调用顺序

3. **测试异常处理**:
   - 在 `execute_core_logic()` 中抛出异常，验证 `StageExecution.status = "FAILED"`

4. **测试时长记录**:
   - 验证 `duration` 字段准确性

### 集成测试

1. **测试真实节点执行**:
   - 使用真实的 FFmpeg 节点，验证完整流程

2. **测试 MinIO URL 生成**:
   - 验证本地路径正确转换为 MinIO URL

---

## 性能要求

- `execute()` 方法的额外开销（验证、格式化）不得超过 50ms
- 内存使用增加不得超过 10%

---

## 安全要求

- 输入参数快照中的敏感信息必须脱敏
- 错误信息不得泄露系统路径或配置细节

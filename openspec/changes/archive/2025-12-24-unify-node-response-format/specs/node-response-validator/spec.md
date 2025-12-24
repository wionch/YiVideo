# Capability: 节点响应验证器 (Node Response Validator)

## ADDED Requirements

### Requirement: 所有节点响应必须通过格式验证

**优先级**: P0
**理由**: 确保响应格式一致性，快速发现不符合规范的节点

#### Scenario: 验证响应包含所有必需字段

**Given** 节点执行完成并更新了 `WorkflowContext`
**When** 运行 `NodeResponseValidator.validate()`
**Then** 验证器必须检查 `StageExecution` 包含以下必需字段:
- `status`: 任务状态
- `input_params`: 输入参数快照
- `output`: 输出数据
- `error`: 错误信息（可为 null）
- `duration`: 执行时长

**And** 如果任何必需字段缺失，验证失败并报告错误

#### Scenario: 验证状态字段格式

**Given** 节点的 `StageExecution.status` 字段值为 `"success"`（小写）
**When** 运行验证器
**Then** 验证失败并报告错误:
```
Invalid status 'success'. Must be one of: SUCCESS, FAILED, PENDING, RUNNING
```

**And** 仅接受以下大写状态值:
- `SUCCESS`
- `FAILED`
- `PENDING`
- `RUNNING`

---

### Requirement: 验证 MinIO URL 字段命名符合约定

**优先级**: P0
**理由**: 自动检测命名不一致问题

#### Scenario: 检测不符合约定的 MinIO URL 字段名

**Given** 节点输出包含以下字段:
```python
{
    "keyframe_dir": "/share/keyframes",
    "keyframe_minio_url": "http://..."  # ❌ 错误命名
}
```
**When** 运行验证器
**Then** 验证失败并报告错误:
```
MinIO URL field 'keyframe_minio_url' does not follow naming convention.
Expected: 'keyframe_dir_minio_url'
```

#### Scenario: 检测 MinIO URL 字段缺少对应的本地字段

**Given** 节点输出包含:
```python
{
    "audio_path_minio_url": "http://..."
}
```
**And** 缺少对应的 `audio_path` 本地字段
**When** 运行验证器
**Then** 验证失败并报告错误:
```
MinIO URL field 'audio_path_minio_url' exists but corresponding local field 'audio_path' is missing
```

---

### Requirement: 验证禁止使用非标准时长字段

**优先级**: P1
**理由**: 统一时长字段命名，避免混淆

#### Scenario: 检测非标准时长字段

**Given** 节点输出包含以下字段:
```python
{
    "processing_time": 10.5,  # ❌ 非标准字段
    "transcribe_duration": 8.2  # ❌ 非标准字段
}
```
**When** 运行验证器
**Then** 验证失败并报告错误:
```
Non-standard duration field 'processing_time' found. Use 'duration' at stage level instead
Non-standard duration field 'transcribe_duration' found. Use 'duration' at stage level instead
```

**And** 仅允许在 `StageExecution.duration` 中记录时长

---

### Requirement: 验证数据溯源字段格式（可选但推荐）

**优先级**: P2
**理由**: 确保数据来源可追溯

#### Scenario: 验证 provenance 字段结构

**Given** 节点输出包含 `provenance` 字段:
```python
{
    "provenance": {
        "source_stage": "faster_whisper.transcribe_audio"
        # ❌ 缺少 source_field
    }
}
```
**When** 运行验证器
**Then** 验证失败并报告错误:
```
Provenance field missing 'source_field'
```

**And** 完整的 `provenance` 结构必须包含:
- `source_stage`: 数据来源的阶段名称
- `source_field`: 数据来源的字段名称
- `fallback_chain`（可选）: 回退链列表

---

### Requirement: 支持严格模式和宽松模式

**优先级**: P0
**理由**: 开发环境需要严格验证，生产环境需要性能优化

#### Scenario: 严格模式下验证失败抛出异常

**Given** 验证器配置为严格模式 `strict_mode=True`
**And** 节点响应存在验证错误
**When** 运行验证器
**Then** 必须抛出 `ValidationError` 异常
**And** 异常消息包含所有验证错误的详细信息

#### Scenario: 宽松模式下验证失败仅记录日志

**Given** 验证器配置为宽松模式 `strict_mode=False`
**And** 节点响应存在验证错误
**When** 运行验证器
**Then** 不抛出异常
**And** 返回 `False` 表示验证失败
**And** 错误信息记录到日志

---

### Requirement: 提供详细的验证报告

**优先级**: P1
**理由**: 便于开发者快速定位问题

#### Scenario: 生成可读的验证报告

**Given** 节点响应存在多个验证错误
**When** 调用 `validator.get_validation_report()`
**Then** 返回格式化的报告:
```
❌ Found 3 validation errors:
  1. ffmpeg.extract_audio: Invalid status 'success'. Must be one of: SUCCESS, FAILED, PENDING, RUNNING
  2. ffmpeg.extract_audio: MinIO URL field 'keyframe_minio_url' does not follow naming convention. Expected: 'keyframe_dir_minio_url'
  3. ffmpeg.extract_audio: Non-standard duration field 'processing_time' found. Use 'duration' at stage level instead
```

#### Scenario: 验证通过时返回成功消息

**Given** 节点响应通过所有验证
**When** 调用 `validator.get_validation_report()`
**Then** 返回:
```
✅ All validations passed
```

---

## MODIFIED Requirements

### Requirement: 现有节点必须修复验证错误

**优先级**: P0
**理由**: 确保所有节点符合新规范

#### Scenario: 修复 indextts.generate_speech 的状态字段

**Given** 现有节点返回 `status="success"`（小写）
**When** 运行验证器
**Then** 验证失败
**And** 节点必须修改为 `status="SUCCESS"`（大写）

#### Scenario: 修复 faster_whisper.transcribe_audio 的时长字段

**Given** 现有节点输出包含:
```python
{
    "transcribe_duration": 45.2,
    "duration": 45.2  # 重复
}
```
**When** 运行验证器
**Then** 验证失败
**And** 节点必须移除 `transcribe_duration` 字段，仅保留 `StageExecution.duration`

---

## REMOVED Requirements

无（这是新增能力）

---

## 依赖关系

- **依赖**: `services/common/context.py` 中的 `WorkflowContext` 和 `StageExecution` 模型
- **依赖**: `services/common/minio_url_convention.py`（用于验证字段命名）
- **被依赖**: `BaseNodeExecutor.execute()` 方法（可选集成）
- **被依赖**: 集成测试套件

---

## 测试要求

### 单元测试

1. **测试必需字段验证**:
   ```python
   def test_required_fields_validation():
       stage = StageExecution(
           status="SUCCESS",
           input_params={},
           output={},
           # 缺少 error 和 duration
       )
       validator = NodeResponseValidator(strict_mode=True)
       with pytest.raises(ValidationError):
           validator.validate(context, "test_stage")
   ```

2. **测试状态字段验证**:
   ```python
   def test_status_field_validation():
       stage = StageExecution(
           status="success",  # 小写，错误
           input_params={},
           output={},
           error=None,
           duration=1.0
       )
       validator = NodeResponseValidator()
       assert validator.validate(context, "test_stage") == False
       assert "Invalid status" in validator.get_validation_report()
   ```

3. **测试 MinIO URL 命名验证**:
   ```python
   def test_minio_url_naming_validation():
       stage = StageExecution(
           status="SUCCESS",
           output={
               "keyframe_dir": "/share/keyframes",
               "keyframe_minio_url": "http://..."  # 错误命名
           },
           ...
       )
       validator = NodeResponseValidator()
       assert validator.validate(context, "test_stage") == False
       assert "does not follow naming convention" in validator.get_validation_report()
   ```

4. **测试时长字段验证**:
   ```python
   def test_duration_field_validation():
       stage = StageExecution(
           status="SUCCESS",
           output={
               "processing_time": 10.5  # 非标准字段
           },
           duration=10.5,
           ...
       )
       validator = NodeResponseValidator()
       assert validator.validate(context, "test_stage") == False
       assert "Non-standard duration field" in validator.get_validation_report()
   ```

5. **测试严格模式与宽松模式**:
   ```python
   def test_strict_vs_loose_mode():
       # 严格模式：抛出异常
       validator_strict = NodeResponseValidator(strict_mode=True)
       with pytest.raises(ValidationError):
           validator_strict.validate(invalid_context, "test_stage")

       # 宽松模式：返回 False
       validator_loose = NodeResponseValidator(strict_mode=False)
       assert validator_loose.validate(invalid_context, "test_stage") == False
   ```

### 集成测试

1. **测试所有节点的响应格式**:
   ```python
   @pytest.mark.parametrize("task_name", [
       "ffmpeg.extract_audio",
       "faster_whisper.transcribe_audio",
       "pyannote_audio.diarize_speakers",
       # ... 所有 18 个节点
   ])
   def test_all_nodes_response_format(task_name):
       context = execute_task(task_name, test_input)
       validator = NodeResponseValidator(strict_mode=True)
       assert validator.validate(context, task_name) == True
   ```

---

## 性能要求

- 验证单个节点响应的时间不得超过 10ms
- 验证器不得显著增加内存使用（< 1MB）

---

## 配置要求

### 环境变量

```bash
# 开发环境：启用严格验证
NODE_RESPONSE_VALIDATOR_STRICT_MODE=true

# 生产环境：禁用严格验证（仅记录日志）
NODE_RESPONSE_VALIDATOR_STRICT_MODE=false
```

### 集成到执行流程

```python
# 在 BaseNodeExecutor.execute() 中集成验证器
def execute(self) -> WorkflowContext:
    # ... 执行逻辑 ...

    # 可选：验证响应格式
    if os.getenv("NODE_RESPONSE_VALIDATOR_STRICT_MODE") == "true":
        validator = NodeResponseValidator(strict_mode=True)
        validator.validate(self.context, self.stage_name)

    return self.context
```

---

## 文档要求

### 验证错误参考文档

创建 `docs/development/node-response-validation-errors.md`，列出所有可能的验证错误及修复方法:

| 错误代码 | 错误消息 | 修复方法 |
|---------|---------|---------|
| `E001` | Missing required field 'status' | 确保 `StageExecution` 包含 `status` 字段 |
| `E002` | Invalid status 'success' | 使用大写状态值（SUCCESS/FAILED/PENDING/RUNNING） |
| `E003` | MinIO URL field naming error | 使用 `{field_name}_minio_url` 格式 |
| `E004` | Non-standard duration field | 移除 `processing_time` 等字段，使用 `StageExecution.duration` |
| `E005` | Provenance field incomplete | 确保 `provenance` 包含 `source_stage` 和 `source_field` |

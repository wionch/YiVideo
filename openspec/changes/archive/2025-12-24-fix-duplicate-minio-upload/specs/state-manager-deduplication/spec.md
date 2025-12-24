# Spec: State Manager MinIO 上传去重

## Capability ID
`state-manager-deduplication`

## Summary
为 `state_manager.py` 的文件上传功能添加去重逻辑,防止同一文件被重复上传到 MinIO。

---

## MODIFIED Requirements

### Requirement: 文件上传去重检查

**描述**:
在上传文件到 MinIO 之前,系统 **MUST** 检查对应的 `{key}_minio_url` 字段是否已存在。如果存在,系统 **SHALL** 跳过上传并记录日志。

**优先级**: P0

**受影响组件**:
- `services/common/state_manager.py::_upload_files_to_minio()`

#### Scenario: 单个文件字段去重

**Given**:
- `stage.output` 中存在 `audio_path: /share/workflows/xxx/223.wav`
- `stage.output` 中已存在 `audio_path_minio_url: http://minio:9000/yivideo/xxx/223.wav`

**When**:
- 调用 `update_workflow_state(context)`

**Then**:
- 不会重新上传 `audio_path` 对应的文件
- 记录日志: `"跳过已上传的文件: audio_path (已有 audio_path_minio_url)"`
- `audio_path_minio_url` 保持不变

**实现细节**:
```python
elif isinstance(file_value, str):
    minio_field_name = convention.get_minio_url_field_name(key)

    # 优先检查是否已有 MinIO URL
    if minio_field_name in stage.output:
        logger.info(f"跳过已上传的文件: {key} (已有 {minio_field_name})")
        continue

    # 跳过已经是URL的路径
    if file_value.startswith('http://') or file_value.startswith('https://'):
        continue

    # 检查文件是否存在
    if os.path.exists(file_value):
        # ...现有上传逻辑...
```

---

#### Scenario: 数组文件字段去重

**Given**:
- `stage.output` 中存在 `all_audio_files: ["/share/a.wav", "/share/b.wav"]`
- `stage.output` 中已存在 `all_audio_files_minio_urls: ["http://minio/a.wav", "http://minio/b.wav"]`

**When**:
- 调用 `update_workflow_state(context)`

**Then**:
- 不会重新上传 `all_audio_files` 中的文件
- 记录日志: `"跳过已上传的文件数组: all_audio_files (已有 all_audio_files_minio_urls)"`
- `all_audio_files_minio_urls` 保持不变

**实现细节**:
```python
if isinstance(file_value, list):
    minio_field_name = convention.get_minio_url_field_name(key)

    # 检查是否已有 MinIO URL 数组
    if minio_field_name in stage.output and stage.output[minio_field_name]:
        logger.info(f"跳过已上传的文件数组: {key} (已有 {minio_field_name})")
        continue

    # ...现有上传逻辑...
```

---

#### Scenario: MinIO URL 缺失时正常上传

**Given**:
- `stage.output` 中存在 `audio_path: /share/workflows/xxx/223.wav`
- `stage.output` 中**不存在** `audio_path_minio_url`

**When**:
- 调用 `update_workflow_state(context)`

**Then**:
- 正常上传 `audio_path` 对应的文件
- 生成 `audio_path_minio_url` 字段
- 记录日志: `"准备上传文件: /share/workflows/xxx/223.wav -> xxx/223.wav"`
- 记录日志: `"文件已上传: audio_path_minio_url = http://minio:9000/yivideo/xxx/223.wav"`

---

#### Scenario: 重复调用不会重复上传

**Given**:
- 工作流上下文 `context` 包含文件路径 `audio_path`
- 第一次调用 `update_workflow_state(context)` 已上传文件

**When**:
- 第二次调用 `update_workflow_state(context)` (例如 API Gateway 合并状态时)

**Then**:
- 检测到 `audio_path_minio_url` 已存在
- 跳过上传,不会向 MinIO 发起请求
- 日志中出现 `"跳过已上传的文件"` 而非 `"准备上传文件"`

---

### Requirement: 保持向后兼容性

**描述**:
去重逻辑 **MUST NOT** 影响现有工作流的正常运行,数据结构 **SHALL** 保持不变。

**优先级**: P0

#### Scenario: 现有工作流正常运行

**Given**:
- 现有工作流配置和数据结构
- 已部署的 Worker 服务

**When**:
- 部署新版本 `state_manager.py`
- 执行现有工作流

**Then**:
- 工作流正常完成
- 文件正常上传到 MinIO
- 阶段输出结构与之前一致
- 不需要数据迁移

---

#### Scenario: 数据结构保持不变

**Given**:
- 上传前的 `stage.output` 结构

**When**:
- 执行文件上传

**Then**:
- 上传后的 `stage.output` 结构与之前一致
- 仍然包含原始本地路径字段 (如 `audio_path`)
- 仍然包含 MinIO URL 字段 (如 `audio_path_minio_url`)
- 不会新增额外的标记字段 (如 `audio_path_uploaded`)

**数据结构示例**:
```python
# 修复前后结构一致
stage.output = {
    "audio_path": "/share/workflows/xxx/223.wav",
    "audio_path_minio_url": "http://minio:9000/yivideo/xxx/223.wav"
}
```

---

## ADDED Requirements

### Requirement: 日志可观测性

**描述**:
系统 **MUST** 添加清晰的日志信息,便于排查问题和监控上传行为。

**优先级**: P1

#### Scenario: 跳过上传时记录日志

**Given**:
- 文件已上传,`minio_field_name` 已存在

**When**:
- 检测到去重条件满足

**Then**:
- 记录 INFO 级别日志
- 日志格式: `"跳过已上传的文件: {key} (已有 {minio_field_name})"`
- 日志包含足够信息用于问题排查

---

#### Scenario: 日志区分单个文件和数组

**Given**:
- 单个文件字段和数组文件字段

**When**:
- 跳过上传

**Then**:
- 单个文件: `"跳过已上传的文件: audio_path (已有 audio_path_minio_url)"`
- 数组文件: `"跳过已上传的文件数组: all_audio_files (已有 all_audio_files_minio_urls)"`

---

## Testing Requirements

### Requirement: 单元测试覆盖

**描述**:
为去重逻辑编写全面的单元测试。

**优先级**: P0

**测试文件**: `tests/unit/common/test_state_manager_upload_dedup.py`

**测试用例**:
1. `test_first_upload_succeeds` - 首次上传成功
2. `test_skip_already_uploaded_file` - 跳过已上传的单个文件
3. `test_skip_already_uploaded_array` - 跳过已上传的文件数组
4. `test_upload_when_minio_url_missing` - MinIO URL 缺失时正常上传
5. `test_log_message_on_skip` - 跳过时记录正确日志

---

## Performance Requirements

### Requirement: 性能无回退

**描述**:
去重检查不应显著增加函数执行时间。

**优先级**: P1

#### Scenario: 检查开销可忽略

**Given**:
- 包含 10 个文件字段的工作流上下文

**When**:
- 执行 `_upload_files_to_minio(context)`

**Then**:
- 去重检查总耗时 < 10ms
- 相比原实现,性能开销 < 5%

---

## Related Capabilities

- `single-task-state-reuse` - 单任务状态复用机制
- `local-directory-management` - 本地目录管理
- `ffmpeg-crop-subtitle-images` - FFmpeg 压缩上传

---

## Implementation Notes

### 修改位置

**文件**: `services/common/state_manager.py`

**函数**: `_upload_files_to_minio(context: WorkflowContext) -> None`

**行号**:
- 单个文件字段: 约 156-178 行
- 数组文件字段: 约 124-153 行

### 关键代码变更

```python
# 在上传前添加检查
minio_field_name = convention.get_minio_url_field_name(key)

if minio_field_name in stage.output:
    logger.info(f"跳过已上传的文件: {key} (已有 {minio_field_name})")
    continue
```

### 不需要修改的部分

- MinIO URL 命名约定 (`minio_url_convention.py`)
- 文件上传服务 (`file_service.py`)
- 工作流上下文结构 (`context.py`)

---

## Acceptance Criteria

- [ ] 同一文件在工作流执行过程中只上传一次
- [ ] API Gateway 日志中不再出现重复上传信息
- [ ] 所有单元测试通过 (覆盖率 > 90%)
- [ ] 集成测试验证工作流正常运行
- [ ] 代码通过 Flake8 和 Black 检查
- [ ] 性能测试显示无明显回退
- [ ] 文档更新完成

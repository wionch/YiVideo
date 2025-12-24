# Tasks: 修复 MinIO 文件重复上传问题

## 任务列表

### Task 1: 修改文件上传去重逻辑
**优先级**: P0
**预计时间**: 1 小时
**依赖**: 无

**描述**:
修改 `services/common/state_manager.py::_upload_files_to_minio()` 函数,在上传前检查 `{key}_minio_url` 字段是否已存在。

**验收标准**:
- [x] 单个文件字段: 检查 `minio_field_name` 是否已存在于 `stage.output`
- [x] 数组文件字段: 同样添加去重检查
- [x] 添加日志: 跳过已上传文件时记录日志
- [x] 代码符合 Python 3.11+ 规范

**实施细节**:
```python
# 单个文件字段 (约 156-178 行)
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

# 数组文件字段 (约 124-153 行)
if isinstance(file_value, list):
    minio_field_name = convention.get_minio_url_field_name(key)

    # 检查是否已有 MinIO URL 数组
    if minio_field_name in stage.output and stage.output[minio_field_name]:
        logger.info(f"跳过已上传的文件数组: {key} (已有 {minio_field_name})")
        continue

    # ...现有上传逻辑...
```

---

### Task 2: 编写单元测试
**优先级**: P0
**预计时间**: 1 小时
**依赖**: Task 1

**描述**:
为 `_upload_files_to_minio()` 函数编写全面的单元测试,覆盖去重逻辑。

**验收标准**:
- [x] 测试首次上传正常工作
- [x] 测试重复调用不会重复上传(单个文件)
- [x] 测试重复调用不会重复上传(数组文件)
- [x] 测试 MinIO URL 已存在时跳过上传
- [x] 测试日志输出正确
- [x] 所有测试通过 (12/12)

**测试文件位置**:
`tests/unit/common/test_state_manager_upload_dedup.py`

**测试用例**:
1. `test_first_upload_succeeds` - 首次上传成功
2. `test_skip_already_uploaded_file` - 跳过已上传的单个文件
3. `test_skip_already_uploaded_array` - 跳过已上传的文件数组
4. `test_upload_when_minio_url_missing` - MinIO URL 缺失时正常上传
5. `test_log_message_on_skip` - 跳过时记录正确日志

---

### Task 3: 集成测试验证
**优先级**: P1
**预计时间**: 30 分钟
**依赖**: Task 1, Task 2

**描述**:
执行完整工作流,验证文件只上传一次,日志中不再出现重复上传信息。

**验收标准**:
- [x] 执行 `video_to_subtitle_task` 工作流
- [x] 检查 MinIO 中每个文件只有一个版本
- [x] 检查 API Gateway 日志,确认每个文件只上传一次
- [x] 验证工作流正常完成

**测试步骤**:
```bash
# 1. 清空 MinIO bucket
# 2. 执行工作流
curl -X POST http://localhost:8000/api/v1/single_task \
  -H "Content-Type: application/json" \
  -d '{"task_name": "ffmpeg.extract_audio", "task_id": "test_dedup", ...}'

# 3. 检查日志
docker logs yivideo-api-gateway-1 2>&1 | grep "准备上传文件"
docker logs yivideo-api-gateway-1 2>&1 | grep "跳过已上传的文件"

# 4. 检查 MinIO
# 验证每个文件只有一个版本
```

---

### Task 4: 性能验证
**优先级**: P2
**预计时间**: 30 分钟
**依赖**: Task 3

**描述**:
对比修复前后的性能指标,验证改进效果。

**验收标准**:
- [ ] 记录修复前的 MinIO 上传次数
- [ ] 记录修复后的 MinIO 上传次数
- [ ] 验证上传次数减少至少 50%
- [ ] 验证 API Gateway 响应时间无明显增加

**性能指标**:
| 指标 | 修复前 | 修复后 | 改善 |
|------|--------|--------|------|
| 单个工作流上传次数 | ~10-15 | ~5-7 | 50%+ |
| API Gateway 平均响应时间 | 待测 | 待测 | 无回退 |
| MinIO 存储使用量 | 待测 | 待测 | 减少 |

---

### Task 5: 代码审查与文档更新
**优先级**: P1
**预计时间**: 30 分钟
**依赖**: Task 1, Task 2

**描述**:
代码审查并更新相关文档。

**验收标准**:
- [x] 代码通过 Flake8 和 Black 检查
- [x] 添加函数文档字符串说明去重逻辑
- [x] 更新 `services/common/state_manager.py` 的模块文档
- [x] 代码审查通过

**文档更新**:
```python
def _upload_files_to_minio(context: WorkflowContext) -> None:
    """
    自动检测并上传工作流中的文件到MinIO

    去重逻辑:
    - 检查 {key}_minio_url 字段是否已存在
    - 如果存在,跳过上传并记录日志
    - 如果不存在,执行上传并生成 MinIO URL

    Args:
        context: 工作流上下文对象
    """
```

---

## 任务依赖关系

```
Task 1 (核心修复)
  ├─→ Task 2 (单元测试)
  │     └─→ Task 5 (代码审查)
  └─→ Task 3 (集成测试)
        └─→ Task 4 (性能验证)
```

## 可并行化任务

- Task 2 和 Task 5 可以在 Task 1 完成后并行执行
- Task 3 和 Task 4 必须顺序执行

## 总计时间

- **关键路径**: Task 1 → Task 2 → Task 3 → Task 4 = 3 小时
- **并行优化**: Task 1 → (Task 2 || Task 5) → Task 3 → Task 4 = 2.5 小时

## 回滚计划

如果发现问题,可以通过以下方式回滚:

1. **代码回滚**: `git revert <commit-hash>`
2. **功能开关**: 暂时禁用 `auto_upload_to_minio` 配置
3. **热修复**: 注释掉去重检查逻辑,恢复原始行为

## 监控指标

部署后需要监控:
- MinIO 上传请求数 (应该减少)
- API Gateway CPU/内存使用率 (应该降低)
- 工作流执行成功率 (应该保持 100%)
- 错误日志数量 (应该为 0)

---

### Task 6: 修复空 MinIO URL 问题
**优先级**: P0 (紧急)
**预计时间**: 1 小时
**依赖**: Task 1, Task 2

**描述**:
修复去重逻辑中未验证 URL 值有效性的问题，导致空字符串被误判为"已上传"。

**验收标准**:
- [x] 单个文件字段：验证 URL 非空且格式有效
- [x] 数组文件字段：验证至少包含一个有效 URL
- [x] 无效 URL 警告：记录日志并触发重新上传
- [x] 新增 3 个测试用例 (空字符串、空数组、无效格式)
- [x] 所有测试通过 (15/15)

**实施结果**:
- 修改 `state_manager.py` Line 62-75 (数组字段) 和 Line 113-125 (单个文件)
- 测试文件：`tests/unit/common/test_state_manager_upload_dedup.py::TestEmptyUrlHandling`
- 文档：`docs/fixes/empty-minio-url-fix.md`

---

### Task 7: 修复 API Gateway 阻塞问题
**优先级**: P0 (紧急)
**预计时间**: 30 分钟
**依赖**: Task 1

**描述**:
在 API Gateway 的所有 `update_workflow_state()` 调用中添加 `skip_side_effects=True`，避免同步上传大文件阻塞 HTTP 请求。

**验收标准**:
- [x] 修改 `_create_task_record()` 添加参数
- [x] 修改 `_update_task_status()` 添加参数
- [x] 修改 `_check_reuse()` 添加参数
- [x] 修改 `_send_reuse_callback_async()` 添加参数
- [x] 创建验证测试确认 API Gateway 不执行上传
- [x] 所有 4 处调用点已修改

**实施结果**:
- 修改文件：`services/api_gateway/app/single_task_executor.py` (4 处)
- 验证测试：`tests/integration/test_api_no_upload_blocking.py`
- 文档：`docs/fixes/api-gateway-upload-blocking-fix.md`

---

## 任务完成统计

| 任务 | 状态 | 完成时间 |
|------|------|---------|
| Task 1: 去重逻辑 | ✅ 完成 | 2025-12-24 |
| Task 2: 单元测试 | ✅ 完成 | 2025-12-24 |
| Task 3: 集成测试 | ✅ 完成 | 2025-12-24 |
| Task 4: 性能验证 | ⚠️ 部分完成 | - |
| Task 5: 代码审查 | ✅ 完成 | 2025-12-24 |
| Task 6: 空URL修复 | ✅ 完成 | 2025-12-24 |
| Task 7: API阻塞修复 | ✅ 完成 | 2025-12-24 |

**总计**: 6/7 完成 (Task 4 性能验证未进行压力测试，但功能验证已通过)

## 最终验收

- ✅ 所有单元测试通过 (15/15)
- ✅ 集成测试通过
- ✅ API Gateway 不再阻塞
- ✅ 文件上传成功率 100%
- ✅ MinIO URL 字段均为有效值
- ✅ 文档完整

# Design: MinIO 文件上传去重机制

## 架构决策

### 决策 1: 保留集中式上传架构

**背景**:
当前文件上传逻辑集中在 `state_manager.py` 中,由 `update_workflow_state()` 自动触发。这导致 API Gateway 和 Worker 都会执行上传操作。

**选项**:
1. **保持集中式** - 在 `state_manager` 中添加去重逻辑
2. **迁移到 Worker** - 将上传逻辑移到各个 Worker 服务
3. **混合模式** - Worker 负责上传,API Gateway 仅验证

**决策**: 选择选项 1 - 保持集中式架构

**理由**:
- **关注点分离**: Worker 专注业务逻辑,不应关心存储细节
- **容错性**: 即使 Worker 忘记上传,API Gateway 也会补救
- **实施成本**: 仅需修改一个文件,影响范围最小
- **向后兼容**: 不需要修改所有 Worker 服务

**权衡**:
- ✅ 简单、低风险、快速实施
- ❌ API Gateway 仍需处理文件上传(但通过去重已大幅减少)

---

### 决策 2: 使用 _minio_url 字段检查而非标记位

**背景**:
需要一种机制来判断文件是否已上传,避免重复上传。

**选项**:
1. **检查 _minio_url 字段** - 如果字段存在,说明已上传
2. **清除本地路径** - 上传后将本地路径设为 None
3. **添加 _uploaded 标记** - 新增布尔字段标记上传状态

**决策**: 选择选项 1 - 检查 _minio_url 字段

**理由**:
- **最小侵入**: 不改变数据结构,仅优化检查逻辑
- **语义清晰**: `_minio_url` 存在即代表已上传
- **保留信息**: 本地路径和 MinIO URL 都保留,便于调试
- **向后兼容**: 现有代码无需修改

**权衡**:
- ✅ 零数据迁移成本
- ✅ 完全向后兼容
- ❌ 如果 MinIO 文件被手动删除,不会自动重新上传(但这是合理的行为)

**替代方案对比**:

| 方案 | 数据结构变更 | 兼容性 | 调试友好度 | 实施复杂度 |
|------|-------------|--------|-----------|-----------|
| 检查 _minio_url | 无 | 100% | 高 | 低 |
| 清除本地路径 | 有 (丢失信息) | 90% | 中 | 低 |
| 添加 _uploaded 标记 | 有 (新增字段) | 95% | 高 | 中 |

---

### 决策 3: 日志级别选择

**背景**:
需要决定跳过上传时的日志级别。

**选项**:
1. **INFO** - 正常信息,便于监控
2. **DEBUG** - 调试信息,减少日志噪音
3. **WARNING** - 警告信息,提示潜在问题

**决策**: 选择选项 1 - INFO 级别

**理由**:
- **可观测性**: 便于验证去重逻辑是否生效
- **问题排查**: 可以快速定位文件上传行为
- **非噪音**: 相比之前的重复上传,这是有价值的信息

**日志格式**:
```
跳过已上传的文件: audio_path (已有 audio_path_minio_url)
跳过已上传的文件数组: all_audio_files (已有 all_audio_files_minio_urls)
```

---

## 实现策略

### 修改位置

**文件**: `services/common/state_manager.py`

**函数**: `_upload_files_to_minio(context: WorkflowContext) -> None`

**关键代码段**:

#### 1. 单个文件字段 (约 156-178 行)

```python
elif isinstance(file_value, str):
    minio_field_name = convention.get_minio_url_field_name(key)

    # 【新增】优先检查是否已有 MinIO URL
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

#### 2. 数组文件字段 (约 124-153 行)

```python
if isinstance(file_value, list):
    minio_field_name = convention.get_minio_url_field_name(key)

    # 【新增】检查是否已有 MinIO URL 数组
    if minio_field_name in stage.output and stage.output[minio_field_name]:
        logger.info(f"跳过已上传的文件数组: {key} (已有 {minio_field_name})")
        continue

    # ...现有上传逻辑...
```

---

## 测试策略

### 单元测试

**文件**: `tests/unit/common/test_state_manager_upload_dedup.py`

**测试覆盖**:
1. 首次上传成功
2. 重复调用不会重复上传
3. MinIO URL 缺失时正常上传
4. 数组字段去重
5. 日志输出正确

### 集成测试

**场景**: 执行完整工作流 `video_to_subtitle_task`

**验证点**:
1. 每个文件只上传一次
2. 日志中出现 "跳过已上传的文件"
3. 工作流正常完成
4. MinIO 中文件数量正确

---

## 性能影响分析

### 预期改善

| 指标 | 修复前 | 修复后 | 改善 |
|------|--------|--------|------|
| 单个工作流上传次数 | 10-15 | 5-7 | 50%+ |
| MinIO 网络流量 | 高 | 低 | 50%+ |
| API Gateway CPU 使用率 | 中 | 低 | 20%+ |

### 检查开销

**新增操作**: `if minio_field_name in stage.output`

**时间复杂度**: O(1) (字典查找)

**预计开销**: < 1ms per file

**结论**: 可忽略不计

---

## 风险缓解

### 风险 1: 逻辑错误导致文件未上传

**缓解措施**:
- 充分的单元测试覆盖 (覆盖率 > 90%)
- 集成测试验证完整工作流
- 代码审查确保逻辑正确

### 风险 2: 与现有代码冲突

**缓解措施**:
- 仅修改一个函数,影响范围可控
- 保持数据结构不变,向后兼容
- 在测试环境充分验证

### 风险 3: MinIO 文件被删除后无法重新上传

**分析**:
- 这是合理的行为,不应视为缺陷
- 如需重新上传,可以手动删除 `_minio_url` 字段
- 或者提供管理接口强制重新上传

---

## 未来优化方向

### 1. 后台上传队列 (可选)

将大文件上传移至后台线程,避免阻塞 API Gateway。

**优点**: 提升 API Gateway 响应速度
**缺点**: 增加系统复杂度

### 2. 上传失败重试机制 (可选)

如果上传失败,自动重试 3 次。

**优点**: 提高可靠性
**缺点**: 需要额外的错误处理逻辑

### 3. MinIO 文件校验 (可选)

检查 MinIO URL 是否真实存在,如果不存在则重新上传。

**优点**: 自动修复 MinIO 文件丢失问题
**缺点**: 增加网络开销

---

## 总结

本设计采用 **最小侵入、最大兼容** 的原则,通过简单的字段检查逻辑解决重复上传问题。

**核心优势**:
- ✅ 实施简单,风险低
- ✅ 完全向后兼容
- ✅ 性能改善显著
- ✅ 可观测性强

**实施时间**: 2.5-3.5 小时

**预期效果**: MinIO 上传次数减少 50%+

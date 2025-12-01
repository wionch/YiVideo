# 实施任务：WService节点增加input_data参数支持

## 总体安排
- **预估时间**: 3-4小时 (大幅缩短)
- **风险等级**: 低
- **影响范围**: 代码重构 + 文档更新
- **关键路径**: 采用项目标准参数模式 → 代码集成 → 文档更新 → 测试验证

**重要改进**: 发现了项目已有的成熟参数管理模块，无需重新设计参数获取逻辑

## 任务分解

### Phase 1: 基础架构实现 (1小时)

#### Task 1.1: 分析并确定具体参数需求 (已完成，15分钟)
- [x] 分析三个节点的当前实现方式
- [x] 确定需要添加的参数列表
- [x] 发现项目中已有统一的参数管理模块

#### Task 1.2: 采用项目标准参数解析模式 (30分钟)
- [x] 确认使用 `resolve_parameters` + `get_param_with_fallback` 模式
- [x] 分析其他服务的实现示例
- [x] 设计采用项目标准的参数获取流程

#### Task 1.3: 修改wservice.merge_speaker_segments任务 (45分钟) ✅
- [x] 1.3.1 添加节点参数解析逻辑
- [x] 1.3.2 实现segments_data/speaker_segments_data获取
- [x] 1.3.3 实现segments_file/diarization_file获取
- [x] 1.3.4 添加数据验证逻辑
- [x] 1.3.5 保留原有回退逻辑确保向后兼容

#### Task 1.4: 修改wservice.merge_with_word_timestamps任务 (45分钟) ✅
- [x] 1.4.1 添加节点参数解析逻辑
- [x] 1.4.2 实现segments_data/speaker_segments_data获取（验证词级时间戳）
- [x] 1.4.3 实现segments_file/diarization_file获取
- [x] 1.4.4 添加词级时间戳数据验证
- [x] 1.4.5 保留原有回退逻辑确保向后兼容

### Phase 2: 高级功能实现 (2小时) ✅

#### Task 2.1: 增强wservice.prepare_tts_segments任务 (60分钟) ✅
- [x] 2.1.1 扩展_get_segments_from_source_stages函数支持input_data
- [x] 2.1.2 添加segments_data参数支持
- [x] 2.1.3 添加segments_file参数支持
- [x] 2.1.4 添加source_stage_names自定义支持
- [x] 2.1.5 优化参数获取优先级逻辑

#### Task 2.2: 实现统一参数解析模块 (60分钟) ✅
- [x] 2.2.1 创建参数验证函数validate_segments_data
- [x] 2.2.2 创建参数验证函数validate_speaker_segments_data
- [x] 2.2.3 创建文件加载增强函数
- [x] 2.2.4 添加详细的错误处理和日志记录
- [x] 2.2.5 优化参数记录到input_params的逻辑

### Phase 3: 文档更新 (1小时) ✅

#### Task 3.1: 更新WORKFLOW_NODES_REFERENCE.md (60分钟) ✅
- [x] 3.1.1 更新wservice.merge_speaker_segments节点说明
- [x] 3.1.2 更新wservice.merge_with_word_timestamps节点说明
- [x] 3.1.3 更新wservice.prepare_tts_segments节点说明
- [x] 3.1.4 为每个节点添加单任务模式支持说明
- [x] 3.1.5 补充完整的调用示例
- [x] 3.1.6 确保参数说明格式统一

### Phase 4: 测试验证 (1.5小时)

#### Task 4.1: 单元测试验证 (45分钟)
- [ ] 4.1.1 测试参数解析逻辑的正确性
- [ ] 4.1.2 测试数据验证逻辑
- [ ] 4.1.3 测试文件加载功能
- [ ] 4.1.4 测试向后兼容性

#### Task 4.2: 集成测试 (45分钟)
- [ ] 4.2.1 测试单任务模式直接传数据
- [ ] 4.2.2 测试单任务模式文件路径参数
- [ ] 4.2.3 测试动态引用功能
- [ ] 4.2.4 测试错误处理机制

## 具体实施细节

### 核心参数获取逻辑实现

```python
def _get_input_data_with_fallback(param_name: str, resolved_params: dict, 
                                  workflow_context, data_type: str = 'segments'):
    """
    为WService节点优化的参数获取函数
    
    Args:
        param_name: 参数名
        resolved_params: 已解析的节点参数
        workflow_context: 工作流上下文
        data_type: 数据类型 ('segments', 'speaker_segments')
    
    Returns:
        参数值或None
    """
    # 1. 优先从resolved_params获取
    value = resolved_params.get(param_name)
    if value is not None:
        return value
    
    # 2. 从input_data获取
    input_data = workflow_context.input_params.get('input_data', {})
    value = input_data.get(param_name)
    
    if value is not None:
        # 支持动态引用解析
        if isinstance(value, str) and value.strip().startswith('${{'):
            try:
                return _resolve_string(value, workflow_context.model_dump())
            except ValueError:
                return value
        return value
    
    return None
```

### 数据验证逻辑

```python
def validate_segments_data(segments: list) -> bool:
    """验证segments数据格式"""
    if not isinstance(segments, list):
        return False
    
    required_fields = {'start', 'end', 'text'}
    for segment in segments:
        if not isinstance(segment, dict):
            return False
        if not required_fields.issubset(segment.keys()):
            return False
        if not isinstance(segment['start'], (int, float)):
            return False
        if not isinstance(segment['end'], (int, float)):
            return False
        if not isinstance(segment['text'], str):
            return False
    
    return True

def validate_speaker_segments_data(speaker_segments: list) -> bool:
    """验证speaker_segments数据格式"""
    if not isinstance(speaker_segments, list):
        return False
    
    required_fields = {'start', 'end', 'speaker'}
    for segment in speaker_segments:
        if not isinstance(segment, dict):
            return False
        if not required_fields.issubset(segment.keys()):
            return False
        if not isinstance(segment['start'], (int, float)):
            return False
        if not isinstance(segment['end'], (int, float)):
            return False
        if not isinstance(segment['speaker'], str):
            return False
    
    return True
```

## 验收标准

### 功能验收
1. **参数获取**: 三个节点都能正确从input_data获取所有新增参数
2. **动态引用**: input_data中的参数支持 `${{...}}` 语法
3. **向后兼容**: 现有工作流不受影响，继续正常工作
4. **单任务模式**: 所有节点都能在单任务模式下独立运行

### 质量验收
1. **代码质量**: 遵循项目编码规范，有适当的日志记录
2. **错误处理**: 提供清晰的错误信息和处理机制
3. **测试覆盖**: 关键路径有对应的测试用例
4. **文档一致**: 代码实现与文档描述完全一致

### 性能验收
1. **性能无损耗**: 新增参数解析逻辑不影响现有性能
2. **内存使用**: 避免不必要的内存占用
3. **文件处理**: 优化文件加载和缓存机制

## 风险与缓解措施

### 技术风险
1. **参数解析冲突**: 新旧参数解析逻辑可能冲突
   - **缓解**: 充分的测试验证，确保向后兼容性

2. **数据验证复杂性**: 多种数据输入格式的验证
   - **缓解**: 使用统一的验证函数，详细的错误提示

3. **错误处理**: 错误信息不够清晰
   - **缓解**: 统一的错误处理机制，详细的日志记录

### 业务风险
1. **现有工作流中断**: 新功能可能影响现有工作流
   - **缓解**: 保留所有原有逻辑，通过可选参数启用新功能

2. **文档不一致**: 代码实现与文档描述不一致
   - **缓解**: 实现后立即更新文档，使用实际运行结果验证示例

## 验证计划

### 测试用例设计

#### 测试用例1: merge_speaker_segments直接传数据
```python
def test_merge_speaker_segments_direct_data():
    """测试直接传入segments_data和speaker_segments_data"""
    input_data = {
        "segments_data": [
            {"start": 0.0, "end": 3.5, "text": "第一段字幕"},
            {"start": 4.0, "end": 7.2, "text": "第二段字幕"}
        ],
        "speaker_segments_data": [
            {"start": 0.0, "end": 5.0, "speaker": "SPEAKER_00"},
            {"start": 5.0, "end": 10.0, "speaker": "SPEAKER_01"}
        ]
    }
    # 验证能正确处理并返回合并结果
```

#### 测试用例2: merge_with_word_timestamps文件路径
```python
def test_merge_with_word_timestamps_file_paths():
    """测试通过文件路径传入参数"""
    input_data = {
        "segments_file": "/test/segments_with_words.json",
        "diarization_file": "/test/speaker_segments.json"
    }
    # 验证能从文件加载数据并处理词级时间戳
```

#### 测试用例3: prepare_tts_segments自定义源
```python
def test_prepare_tts_segments_custom_source():
    """测试自定义source_stage_names"""
    input_data = {
        "source_stage_names": ["wservice.merge_speaker_segments", "custom.stage.name"]
    }
    # 验证能正确使用自定义的源阶段列表
```

### 回归测试
1. **现有工作流测试**: 验证所有现有工作流配置不受影响
2. **边界条件测试**: 测试各种异常情况下的处理
3. **性能测试**: 验证新功能不会影响系统性能

## 部署计划

### 部署顺序
1. **代码部署**: 先部署代码更改到测试环境
2. **文档更新**: 更新文档到相应的环境
3. **测试验证**: 在测试环境中充分验证功能
4. **生产部署**: 验证无误后部署到生产环境

### 回滚计划
1. **回滚条件**: 如果发现严重问题或破坏性影响
2. **回滚步骤**: 
   - 停止相关服务的Celery任务
   - 回滚代码到上一个稳定版本
   - 重启相关服务
   - 验证原有功能正常
3. **数据恢复**: 确保不会丢失任何工作流状态数据

## 项目时间表

| 阶段 | 开始时间 | 结束时间 | 负责人 | 状态 |
|------|----------|----------|--------|------|
| Phase 1: 基础架构 | T+0h | T+2h | 开发团队 | ✅ 已完成 |
| Phase 2: 高级功能 | T+2h | T+4h | 开发团队 | ✅ 已完成 |
| Phase 3: 文档更新 | T+4h | T+5h | 技术文档 | ✅ 已完成 |
| Phase 4: 测试验证 | T+5h | T+6.5h | QA团队 | ⏳ 待进行 |
| 部署验证 | T+6.5h | T+7h | 运维团队 | ⏳ 待进行 |

**实际完成情况**:
- Phase 1-3 总计用时约3小时，提前完成预期目标
- Phase 4 测试验证将在下一阶段进行
- 所有代码重构和文档更新工作已100%完成

## 成功指标

1. **功能完整性**: 100%完成所有新增参数的支持
2. **向后兼容性**: 0个现有功能受影响
3. **文档一致性**: 100%代码实现与文档一致
4. **测试覆盖率**: 关键路径100%覆盖
5. **错误率**: 新功能相关错误率 < 0.1%

## 后续优化

1. **性能优化**: 根据实际使用情况优化参数解析性能
2. **功能扩展**: 根据用户反馈增加更多参数支持
3. **监控增强**: 添加相关的监控指标和告警
4. **文档完善**: 根据使用情况持续完善文档和示例

# 变更提案：统一所有功能节点参数管理

## 为什么

YiVideo项目的参数管理机制目前存在不一致性。虽然核心模块 `parameter_resolver.py` 已经功能完善，提供了统一的参数解析和获取函数，但部分工作流节点仍在使用手动的参数回退逻辑，这导致了：

1. **代码重复和维护困难**：多个服务重复实现相同的参数获取逻辑
2. **功能不一致**：某些服务不支持完整的单任务模式或动态引用语法
3. **调试复杂性**：不同的参数获取方式增加问题排查难度
4. **扩展性受限**：新增参数管理功能时需要多处修改

通过统一所有节点的参数管理，可以确保整个系统的参数处理行为一致，提升代码质量和可维护性。

## 变更什么

### 核心变更

1. **统一 audio_separator_service 参数获取逻辑**
   - 将第118-126行的手动参数回退逻辑替换为 `get_param_with_fallback` 函数
   - 确保音频源选择逻辑的完整性和一致性
   - 支持完整的单任务模式和工作流模式

2. **统一 faster_whisper_service 参数获取逻辑**
   - 将第479-486行的手动参数回退逻辑替换为 `get_param_with_fallback` 函数
   - 保持智能音频源选择逻辑的正确性
   - 确保动态引用语法 `${{...}}` 的完全支持

### 具体修改内容

#### audio_separator_service 修改
- **文件**: `services/workers/audio_separator_service/app/tasks.py`
- **目标**: 替换第118-126行的音频源选择逻辑
- **方法**: 使用 `get_param_with_fallback` 实现多级参数回退

```python
# 修改前（手动逻辑）
audio_path = resolved_params.get("audio_path")
if not audio_path:
    audio_path = workflow_context.input_params.get("input_data", {}).get("audio_path") or workflow_context.input_params.get("input_data", {}).get("video_path")

# 修改后（统一函数）
audio_path = get_param_with_fallback(
    "audio_path", 
    resolved_params, 
    workflow_context,
    fallback_from_stage="audio_separator.separate_vocals"
)
```

#### faster_whisper_service 修改
- **文件**: `services/workers/faster_whisper_service/app/tasks.py`
- **目标**: 替换第479-486行的音频源选择逻辑
- **方法**: 使用 `get_param_with_fallback` 实现多级参数回退

```python
# 修改前（手动逻辑）
audio_path = resolved_params.get('audio_path')
if not audio_path:
    audio_path = workflow_context.input_params.get('input_data', {}).get('audio_path')

# 修改后（统一函数）
audio_path = get_param_with_fallback(
    "audio_path", 
    resolved_params, 
    workflow_context,
    fallback_from_stage="faster_whisper.transcribe_audio"
)
```

### 不变更的内容

- 核心参数管理模块 `parameter_resolver.py` 保持不变
- 已正确使用 `get_param_with_fallback` 的服务（wservice、paddleocr、indextts、ffmpeg、pyannote_audio）无需修改
- 现有的工作流配置和API接口保持完全兼容
- 智能音频源选择逻辑的核心算法保持不变

## 影响

### 受影响的服务和节点

- **直接影响**:
  - `audio_separator_service.separate_vocals`: 音频源选择逻辑重构
  - `faster_whisper_service.transcribe_audio`: 音频源选择逻辑重构

- **其他节点不受影响**:
  - `wservice`, `paddleocr`, `indextts`, `ffmpeg`, `pyannote_audio`: 保持现有的统一标准
  - 两个服务的其他功能（如果有）完全不受影响

### 受影响的代码

- `services/workers/audio_separator_service/app/tasks.py` (第118-126行，约20行代码修改)
- `services/workers/faster_whisper_service/app/tasks.py` (第479-486行，约20行代码修改)
- 相关测试文件需要更新

### 向后兼容性

- ✅ **完全兼容**: 现有的工作流配置无需修改
- ✅ **API兼容**: 所有现有的API调用方式保持有效
- ✅ **功能兼容**: 智能音频源选择逻辑保持完全一致
- ✅ **性能兼容**: 重构不引入额外的性能开销

### 测试影响

- 需要更新现有的单元测试和集成测试
- 新增参数管理统一性验证测试
- 确保单任务模式和工作流模式的功能完整性

## 预期收益

1. **代码质量提升**: 消除重复代码，提高代码复用率
2. **维护性改善**: 统一的参数管理逻辑，降低维护复杂度
3. **功能完整性**: 所有节点支持完整的单任务模式特性
4. **调试效率**: 统一的参数获取方式简化问题排查
5. **扩展性增强**: 新增参数管理功能时只需在核心模块修改

## 风险评估

### 低风险
- 核心功能保持不变，仅重构实现方式
- 充分的测试验证确保兼容性
- 渐进式重构，可以分步验证

### 潜在问题
- 重构过程中的代码错误可能影响现有功能
- 测试覆盖不完整可能遗漏边界情况

### 缓解措施
- 详细的测试计划和验证流程
- 代码审查和同行评议
- 渐进式部署和回滚准备
# 任务 ID 传递缺陷修复设计文档

## 背景和约束

### 当前问题

1. **缺陷表现**：faster_whisper_service 忽略传入的 task_id，生成随机 ID
2. **根本原因**：函数参数传递链断裂，workflow_context 无法正确传递
3. **影响范围**：所有使用 faster_whisper 服务的任务
4. **用户体验**：无法通过 task_id 追踪和管理任务

### 设计约束

-   **最小化变更**：只修复参数传递缺陷，不改变业务逻辑
-   **向后兼容**：不破坏现有工作流和 API 接口
-   **类型安全**：确保所有参数传递的类型安全
-   **性能影响**：修复不应影响现有性能

## 目标和非目标

### 目标

-   修复 task_id 参数传递缺陷
-   确保传入的 task_id 被正确使用
-   保持与目录重构提案的兼容性
-   提高系统可靠性和可追踪性

### 非目标

-   不改变 faster_whisper 的核心业务逻辑
-   不修改 API 接口或数据格式
-   不重构系统架构
-   不改变其他 worker 服务的实现

## 技术决策

### 决策 1: 参数传递方式

**选择**: 在函数调用链中添加 `workflow_context` 参数
**理由**:

-   符合项目现有模式（其他 worker 服务已采用）
-   类型安全，可以通过类型检查验证
-   便于调试和错误追踪
-   保持函数职责清晰

**备选方案**:

1. 全局变量：不符合项目设计原则
2. 线程本地存储：增加复杂性，不需要
3. 参数封装：过度设计，不必要

### 决策 2: 函数修改策略

**选择**: 修改内部函数签名，添加 workflow_context 参数
**理由**:

-   最小化修改范围
-   保持函数职责不变
-   便于测试和维护
-   确保类型安全

**影响函数**:

-   `_execute_transcription`
-   `_transcribe_audio_with_gpu_lock`
-   `_transcribe_audio_without_lock`

### 决策 3: 调用链更新

**选择**: 更新所有调用点，确保参数传递链完整
**理由**:

-   确保修复的完整性
-   避免运行时错误
-   便于静态分析验证
-   提高代码可维护性

**调用点**:

-   `transcribe_audio` -> `_transcribe_audio_with_lock`
-   `_transcribe_audio_with_lock` -> `_execute_transcription`
-   `_transcribe_audio_without_lock` -> `_execute_transcription`

### 决策 4: 测试策略

**选择**: 多层次测试策略
**理由**:

-   确保修复的正确性
-   防止回归问题
-   验证兼容性
-   提供质量保证

**测试层次**:

1. 单元测试：测试单个函数
2. 集成测试：测试函数间协作
3. 端到端测试：测试完整流程

## 详细设计

### 函数签名修改

#### \_execute_transcription 函数

**修改前**:

```python
def _execute_transcription(audio_path: str, service_config: dict, stage_name: str) -> dict:
    # 有缺陷的task_id获取逻辑
    task_id = workflow_context.workflow_id if 'workflow_context' in locals() else f"task_{int(time.time())}"
```

**修改后**:

```python
def _execute_transcription(
    audio_path: str,
    service_config: dict,
    stage_name: str,
    workflow_context: WorkflowContext
) -> dict:
    # 直接使用传入的workflow_context
    task_id = workflow_context.workflow_id
```

#### 调用链更新

**transcribe_audio 函数**:

```python
def transcribe_audio(self, context: dict) -> dict:
    # ... 现有逻辑 ...
    workflow_context = WorkflowContext(**context)

    # 修复：传递workflow_context给内部函数
    transcribe_result = _transcribe_audio_with_lock(
        audio_path, service_config, stage_name, workflow_context
    )
```

**\_transcribe_audio_with_gpu_lock 函数**:

```python
@gpu_lock()
def _transcribe_audio_with_gpu_lock(
    audio_path: str,
    service_config: dict,
    stage_name: str,
    workflow_context: WorkflowContext
) -> dict:
    return _execute_transcription(audio_path, service_config, stage_name, workflow_context)
```

### 类型安全设计

#### 类型注解

所有修改的函数都必须添加完整的类型注解：

```python
from typing import Dict, Any
from services.common.context import WorkflowContext

def _execute_transcription(
    audio_path: str,
    service_config: Dict[str, Any],
    stage_name: str,
    workflow_context: WorkflowContext
) -> Dict[str, Any]:
```

#### 运行时检查

在函数入口添加类型检查：

```python
def _execute_transcription(
    audio_path: str,
    service_config: Dict[str, Any],
    stage_name: str,
    workflow_context: WorkflowContext
) -> Dict[str, Any]:
    if not isinstance(workflow_context, WorkflowContext):
        raise TypeError(f"Expected WorkflowContext, got {type(workflow_context)}")
```

### 错误处理设计

#### 参数验证

在函数开始时验证所有参数：

```python
def _execute_transcription(
    audio_path: str,
    service_config: Dict[str, Any],
    stage_name: str,
    workflow_context: WorkflowContext
) -> Dict[str, Any]:
    # 参数验证
    if not audio_path or not isinstance(audio_path, str):
        raise ValueError("audio_path must be a non-empty string")

    if not service_config or not isinstance(service_config, dict):
        raise ValueError("service_config must be a non-empty dictionary")

    if not workflow_context or not isinstance(workflow_context, WorkflowContext):
        raise ValueError("workflow_context must be a WorkflowContext instance")
```

#### 异常传播

确保所有异常都能正确传播到调用者：

```python
try:
    return _execute_transcription(audio_path, service_config, stage_name, workflow_context)
except Exception as e:
    logger.error(f"[{stage_name}] Transcription failed: {e}")
    raise
```

## 风险和权衡

### 主要风险

1. **遗漏调用点** - 可能存在未发现的调用点需要更新
2. **类型错误** - 可能传递错误类型的参数
3. **回归问题** - 可能影响现有功能

### 权衡考虑

-   **正确性 vs 复杂性**: 选择正确性，即使增加一些复杂性
-   **性能 vs 可维护性**: 选择可维护性，性能影响最小
-   **向后兼容性 vs 最佳实践**: 优先最佳实践，但尽量保持兼容

## 迁移计划

### 阶段 1: 代码修改

1. **函数签名更新**: 修改所有相关函数的签名
2. **调用点更新**: 更新所有函数调用点
3. **类型检查**: 添加运行时类型检查

### 阶段 2: 测试验证

1. **单元测试**: 为每个修改的函数创建测试
2. **集成测试**: 测试函数间的协作
3. **端到端测试**: 测试完整业务流程

### 阶段 3: 部署验证

1. **开发环境测试**: 在开发环境验证修复
2. **生产环境部署**: 逐步部署到生产环境
3. **监控验证**: 监控关键指标确保正常

## 测试设计

### 单元测试

#### 测试用例 1: workflow_context 传递

```python
def test_execute_transcription_with_workflow_context():
    """测试workflow_context正确传递给execute_transcription函数"""
    # 准备测试数据
    workflow_context = create_test_workflow_context()
    audio_path = "/path/to/audio.wav"
    service_config = {"model_name": "test"}
    stage_name = "test_stage"

    # 调用函数
    result = _execute_transcription(audio_path, service_config, stage_name, workflow_context)

    # 验证结果
    assert result is not None
    # 验证task_id被正确使用
    assert workflow_context.workflow_id in str(result)
```

#### 测试用例 2: 错误处理

```python
def test_execute_transcription_error_handling():
    """测试错误情况下的函数行为"""
    # 测试无效参数
    with pytest.raises(ValueError):
        _execute_transcription("", {}, "stage", create_test_workflow_context())

    with pytest.raises(TypeError):
        _execute_transcription("audio.wav", {}, "stage", "invalid_context")
```

### 集成测试

#### 测试用例 3: 完整调用链

```python
def test_complete_transcription_chain():
    """测试从transcribe_audio到execute_transcription的完整调用链"""
    # 准备测试数据
    context = create_test_context()
    context["input_data"]["task_id"] = "test_task_123"

    # 调用主函数
    result = transcribe_audio(None, context)

    # 验证task_id被正确使用
    assert "test_task_123" in str(result)
```

### 回归测试

#### 测试用例 4: 现有功能

```python
def test_existing_functionality():
    """确保修复后现有功能正常工作"""
    # 测试各种输入场景
    test_scenarios = [
        {"task_id": "scenario1", "audio_path": "path1.wav"},
        {"task_id": "scenario2", "audio_path": "path2.wav"},
    ]

    for scenario in test_scenarios:
        result = transcribe_audio(None, create_context_for_scenario(scenario))
        assert result["status"] == "SUCCESS"
```

## 清理计划

### 代码清理

1. **移除冗余代码**: 清理有缺陷的 task_id 生成逻辑
2. **优化导入**: 确保导入语句正确和必要
3. **格式化代码**: 应用项目代码格式标准

### 文档清理

1. **更新文档字符串**: 为修改的函数添加完整文档
2. **更新注释**: 确保注释准确反映代码逻辑
3. **更新类型注解**: 确保类型注解完整和正确

## 开放问题

1. **测试覆盖率**: 如何确保测试覆盖所有边界情况？
2. **性能影响**: 参数传递是否会对性能产生可测量的影响？
3. **监控方案**: 如何监控修复后的系统行为？

## 总结

本设计方案通过系统性的参数传递修复，彻底解决 faster_whisper_service 中 task_id 传递缺陷。设计重点在于最小化变更、确保类型安全和保持向后兼容性，同时提供全面的测试验证和风险控制机制。

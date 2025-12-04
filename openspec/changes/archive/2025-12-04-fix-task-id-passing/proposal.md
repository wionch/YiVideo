# 变更：修复任务 ID 传递缺陷

## Why

当前系统存在一个严重的功能缺陷：faster_whisper_service 在处理任务时完全忽略用户传入的 `task_id` 参数，而是生成基于时间戳的随机任务 ID。这导致了以下问题：

1. **功能失效**：用户无法通过指定的 task_id 追踪和管理任务
2. **数据混乱**：文件保存到随机目录，无法关联到原始任务
3. **用户体验差**：系统行为不可预测，影响用户信任度
4. **调试困难**：问题排查时无法准确定位相关文件和日志

这个问题在 `refactor-directory-usage` 提案施工完成后被发现，需要立即修复以确保系统功能的正确性和可预测性。

## What Changes

本次变更将修复 faster_whisper_service 中的任务 ID 传递缺陷，确保用户传入的 task_id 被正确使用：

1. **函数签名更新**：为 `_execute_transcription`、`_transcribe_audio_with_lock`、`_transcribe_audio_with_gpu_lock`、`_transcribe_audio_without_lock` 等函数添加 `workflow_context: WorkflowContext` 参数
2. **参数传递链修复**：建立完整的从主函数到内部函数的参数传递链
3. **核心逻辑替换**：将有缺陷的 `task_id = workflow_context.workflow_id if 'workflow_context' in locals() else f"task_{int(time.time())}"` 替换为简单直接的 `task_id = workflow_context.workflow_id`
4. **类型安全保证**：添加完整的类型注解和验证

## 背景

在 `refactor-directory-usage` 提案施工完成后，发现了一个严重的功能缺陷：**faster_whisper_service 在处理任务时忽略传入的 `task_id` 参数，而是生成随机任务 ID**。

### 问题表现

当用户传入特定的 `task_id` 时：

```json
{
    "task_name": "faster_whisper.transcribe_audio",
    "task_id": "task_id",
    "input_data": {
        "audio_path": "http://host.docker.internal:9000/yivideo/task_id/223.wav"
    }
}
```

实际执行中使用随机 ID：

```
任务目录: /share/workflows/task_1764834183/
结果文件: /share/workflows/task_1764834183/tmp/faster_whisper_result_1764834183502.json
```

## 问题分析

### 根本原因

在 `services/workers/faster_whisper_service/app/tasks.py` 第 146 行存在代码缺陷：

```python
task_id = workflow_context.workflow_id if 'workflow_context' in locals() else f"task_{int(time.time())}"
```

**具体问题**：

1. **变量作用域错误**：`workflow_context` 变量在 `_execute_transcription` 函数执行时根本不存在
2. **逻辑错误**：`locals()` 检查的是当前函数的局部变量，而不是调用者的变量
3. **总是生成随机 ID**：由于 `workflow_context` 永远不在局部变量中，导致总是使用基于时间戳的随机 ID

### 调用链分析

```mermaid
graph TD
    A[transcribe_audio] --> B[_transcribe_audio_with_lock]
    B --> C[_transcribe_audio_with_gpu_lock]
    C --> D[_execute_transcription]
    D --> E[生成随机task_id] ❌

    A1[workflow_context创建] --> A
    B1[workflow_context传递] --> C1[_transcribe_audio_without_lock]
    C1 --> D
```

### 影响范围

-   **核心影响**：faster_whisper_service 生成随机 task_id，影响所有相关功能
-   **功能影响**：传入的 `task_id` 参数被完全忽略
-   **数据影响**：文件保存到随机目录，无法关联到原始任务
-   **用户体验**：无法通过 task_id 追踪和管理任务

## 变更目标

### 主要目标

1. **修复参数传递**：确保传入的 `task_id` 被正确使用
2. **保持兼容性**：不破坏现有功能和工作流
3. **提高可靠性**：消除随机 ID 生成的不确定性

### 具体要求

-   传入的 `task_id` 应该被正确传递给所有相关函数
-   临时文件路径应该基于传入的任务 ID 构建
-   保持与 `refactor-directory-usage` 提案的兼容性

## 解决方案

### 核心策略

修改函数调用链，确保 `workflow_context` 正确传递给需要使用任务 ID 的函数：

```python
# 修改前
def _execute_transcription(audio_path: str, service_config: dict, stage_name: str):
    task_id = workflow_context.workflow_id if 'workflow_context' in locals() else f"task_{int(time.time())}"

# 修改后
def _execute_transcription(audio_path: str, service_config: dict, stage_name: str, workflow_context: WorkflowContext):
    task_id = workflow_context.workflow_id
```

### 修改范围

1. **函数签名修改**：在 `_execute_transcription` 及相关函数中添加 `workflow_context` 参数
2. **调用链更新**：确保从主任务函数到内部函数的参数传递链完整
3. **类型安全**：确保所有调用点都传递正确的参数

## 风险评估

### 风险等级：**低**

**原因**：

-   修改范围明确，主要涉及参数传递
-   不改变业务逻辑，只是修复传递缺陷
-   其他 worker 服务已经正确实现了类似逻辑

### 潜在风险

1. **遗漏调用点**：可能有未发现的调用点需要更新
2. **参数类型错误**：传递错误的参数类型
3. **向后兼容性**：可能影响某些特殊调用场景

### 缓解措施

1. **全面代码审查**：检查所有相关调用点
2. **单元测试**：为修改的函数添加测试用例
3. **集成测试**：验证完整的工作流不受影响

## 实施策略

### 阶段 1：代码分析和设计

1. 分析完整的调用链
2. 识别所有需要修改的函数
3. 设计参数传递方案

### 阶段 2：代码修复

1. 修改函数签名
2. 更新所有调用点
3. 确保类型安全

### 阶段 3：测试验证

1. 单元测试验证
2. 集成测试确认
3. 端到端测试验证

### 阶段 4：文档更新

1. 更新函数文档
2. 补充测试用例说明
3. 更新相关技术文档

## 验收标准

### 功能验收

-   [ ] 传入的 `task_id` 被正确使用
-   [ ] 临时文件路径基于传入的任务 ID
-   [ ] 不破坏现有工作流

### 测试验收

-   [ ] 单元测试通过
-   [ ] 集成测试通过
-   [ ] 端到端测试通过

### 代码质量验收

-   [ ] 代码审查通过
-   [ ] 类型检查通过
-   [ ] 静态分析无警告

## 回滚计划

如果出现问题，可以快速回滚：

1. 恢复原始函数签名
2. 撤销所有调用点修改
3. 重新部署验证

## 与现有提案的关系

本提案与 `refactor-directory-usage` 提案的关系：

-   **时间顺序**：在目录重构完成后发现问题
-   **技术关系**：互补关系，共同完善目录管理机制
-   **影响范围**：独立修复，不依赖目录重构的实现
-   **兼容性**：保持与目录重构提案的完全兼容

## 总结

这个修复提案专注于解决一个具体的技术缺陷，确保任务 ID 参数的正确传递。虽然发现时间较晚，但修复范围明确，风险可控，对系统整体稳定性和用户体验有积极意义。

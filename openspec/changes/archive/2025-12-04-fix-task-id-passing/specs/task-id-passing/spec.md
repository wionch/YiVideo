# 规范：任务 ID 传递修复

## ADDED Requirements

### Requirement: workflow_context 参数传递

系统 MUST 在`_execute_transcription`函数中添加`workflow_context: WorkflowContext`参数，以确保任务 ID 的正确传递。

#### Scenario:

-   输入：音频文件路径、服务配置、阶段名称、工作流上下文
-   预期：函数能够正确接收和使用工作流上下文中的任务 ID
-   验证：通过检查生成的临时文件路径确认使用了正确的工作流 ID

### Requirement: 函数调用链更新

系统 MUST 更新从`transcribe_audio`到`_execute_transcription`的完整调用链，确保所有函数都正确传递`workflow_context`参数。

#### Scenario:

-   输入：包含有效`task_id`的请求
-   预期：所有中间函数都正确传递`workflow_context`参数
-   验证：静态分析检查确保所有调用点都传递了正确参数

### Requirement: 类型安全保证

系统 MUST 为所有修改的函数添加完整的类型注解，确保类型安全和编译时检查。

#### Scenario:

-   编译时：mypy 类型检查必须通过
-   运行时：传递错误类型参数必须抛出 TypeError
-   验证：类型检查工具报告零错误

### Requirement: 任务 ID 使用验证

系统 MUST 确保生成的临时文件路径完全基于传入的任务 ID，而不是生成随机 ID。

#### Scenario:

-   输入：`task_id = "test_task_123"`
-   预期：临时文件路径为`/share/workflows/test_task_123/tmp/...`
-   验证：检查文件系统确认路径正确

## MODIFIED Requirements

### Requirement: \_execute_transcription 函数签名

系统 MUST 修改`_execute_transcription`函数签名，添加`workflow_context: WorkflowContext`参数。

**Modified From**:

```python
def _execute_transcription(audio_path: str, service_config: dict, stage_name: str) -> dict:
```

**Modified To**:

```python
def _execute_transcription(
    audio_path: str,
    service_config: Dict[str, Any],
    stage_name: str,
    workflow_context: WorkflowContext
) -> Dict[str, Any]:
```

#### Scenario:

-   函数调用：必须传递 4 个参数，包括 workflow_context
-   兼容性：现有调用代码必须更新以传递新参数
-   验证：函数能够正确接收和使用所有参数

### Requirement: \_transcribe_audio_with_gpu_lock 函数签名

系统 MUST 修改`_transcribe_audio_with_gpu_lock`函数签名，添加`workflow_context: WorkflowContext`参数。

**Modified From**:

```python
def _transcribe_audio_with_gpu_lock(audio_path: str, service_config: dict, stage_name: str) -> dict:
```

**Modified To**:

```python
def _transcribe_audio_with_gpu_lock(
    audio_path: str,
    service_config: Dict[str, Any],
    stage_name: str,
    workflow_context: WorkflowContext
) -> Dict[str, Any]:
```

#### Scenario:

-   GPU 模式：在 CUDA 模式下正确传递参数
-   锁机制：GPU 锁功能不受影响
-   验证：GPU 任务执行成功且使用正确的工作流 ID

### Requirement: \_transcribe_audio_without_lock 函数签名

系统 MUST 修改`_transcribe_audio_without_lock`函数签名，添加`workflow_context: WorkflowContext`参数。

**Modified From**:

```python
def _transcribe_audio_without_lock(audio_path: str, service_config: dict, stage_name: str) -> dict:
```

**Modified To**:

```python
def _transcribe_audio_without_lock(
    audio_path: str,
    service_config: Dict[str, Any],
    stage_name: str,
    workflow_context: WorkflowContext
) -> Dict[str, Any]:
```

#### Scenario:

-   CPU 模式：在 CPU 模式下正确传递参数
-   功能性：转录功能保持不变
-   验证：CPU 任务执行成功且使用正确的工作流 ID

### Requirement: transcribe_audio 函数调用

系统 MUST 更新`transcribe_audio`函数的调用，传递`workflow_context`参数。

**Modified From**:

```python
transcribe_result = _transcribe_audio_with_lock(audio_path, service_config, stage_name)
```

**Modified To**:

```python
transcribe_result = _transcribe_audio_with_lock(
    audio_path, service_config, stage_name, workflow_context
)
```

#### Scenario:

-   主任务：transcribe_audio 主函数正确传递上下文
-   错误处理：异常情况下的参数传递保持正确
-   验证：完整工作流执行成功

## REMOVED Requirements

### Requirement: 移除有缺陷的 task_id 生成逻辑

系统 MUST 移除有缺陷的 task_id 生成逻辑，不再使用基于时间戳的随机 ID 生成方式。

**Removed**:

```python
task_id = workflow_context.workflow_id if 'workflow_context' in locals() else f"task_{int(time.time())}"
```

**Reason**:

-   逻辑错误：`locals()`检查不会找到调用者的变量
-   总是生成随机 ID：无法正确获取传入的任务 ID
-   类型不安全：没有类型检查和验证

#### Scenario:

-   输入：有效的工作流上下文
-   预期：不再生成基于时间戳的随机 ID
-   验证：确认没有随机 ID 生成的日志或文件路径

## 测试要求

### 10. 单元测试覆盖率

**Requirement**: 新增代码的测试覆盖率必须达到 90%以上

**Test Cases**:

-   `test_execute_transcription_with_workflow_context`
-   `test_transcribe_audio_chain_integration`
-   `test_parameter_validation`
-   `test_type_safety`

**Scenario**:

-   覆盖率：单元测试覆盖所有修改的函数
-   边界条件：测试异常输入和边界情况
-   验证：测试工具报告高覆盖率

### 11. 集成测试验证

**Requirement**: 必须通过完整的端到端集成测试

**Test Scenarios**:

-   单任务模式：测试独立的转录任务
-   工作流模式：测试工作流中的转录任务
-   并发模式：测试多个并发转录任务

**Scenario**:

-   正确 ID 使用：所有场景下都使用传入的 task_id
-   目录隔离：不同任务使用不同的目录
-   验证：检查文件系统和日志确认正确行为

### 12. 回归测试通过

**Requirement**: 所有现有测试必须继续通过

**Test Suite**:

-   现有的 faster_whisper_service 测试
-   相关 worker 服务的集成测试
-   端到端工作流测试

**Scenario**:

-   兼容性：修复后不影响现有功能
-   稳定性：系统行为保持一致
-   验证：测试套件报告 100%通过率

## 性能要求

### 13. 性能影响最小化

**Requirement**: 修复不应显著影响系统性能

**Metrics**:

-   函数调用开销：参数传递开销应<1ms
-   内存使用：不应增加显著的内存使用
-   响应时间：整体转录响应时间保持不变

**Scenario**:

-   基准测试：对比修复前后的性能指标
-   负载测试：在高负载下验证性能
-   验证：性能监控工具报告无明显退化

## 安全要求

### 14. 输入验证

**Requirement**: 必须对所有输入参数进行验证

**Validation Rules**:

-   audio_path：必须是字符串且文件存在
-   service_config：必须是字典且包含必要字段
-   workflow_context：必须是 WorkflowContext 实例
-   stage_name：必须是非空字符串

**Scenario**:

-   有效输入：正确的参数被正常处理
-   无效输入：错误的参数被拒绝并抛出适当异常
-   验证：安全测试确认输入验证有效

### 15. 日志和审计

**Requirement**: 必须记录任务 ID 相关的关键操作

**Logging Points**:

-   接收到的工作流上下文信息
-   使用的任务 ID
-   生成的文件路径
-   错误和异常情况

**Scenario**:

-   追踪性：可以通过日志追踪任务执行
-   调试性：问题发生时便于定位
-   验证：日志包含所有必要信息

## 兼容性要求

### 16. 向后兼容性

**Requirement**: 修复不应破坏现有 API 和功能

**Compatibility Points**:

-   API 接口：外部 API 保持不变
-   配置：配置文件格式不变
-   数据格式：输入输出格式不变

**Scenario**:

-   现有客户端：现有客户端代码无需修改
-   现有工作流：现有工作流定义无需修改
-   验证：兼容性测试确认无破坏性变更

### 17. 与目录重构的兼容性

**Requirement**: 必须与`refactor-directory-usage`提案完全兼容

**Integration Points**:

-   目录结构：使用新的目录结构`/share/workflows/{task_id}/`
-   临时文件：临时文件使用正确的任务 ID 路径
-   配置：与新的配置格式兼容

**Scenario**:

-   目录创建：正确创建基于任务 ID 的目录
-   文件存储：文件正确存储在指定目录
-   验证：文件系统检查确认正确结构

## 文档要求

### 18. 函数文档更新

**Requirement**: 所有修改的函数必须更新文档字符串

**Documentation Elements**:

-   函数说明：清晰描述函数功能
-   参数说明：详细说明每个参数的类型和用途
-   返回值说明：描述返回值的格式和含义
-   使用示例：提供使用示例

**Scenario**:

-   可读性：文档字符串清晰易懂
-   完整性：包含所有必要信息
-   验证：文档生成工具正常工作

### 19. 变更日志

**Requirement**: 必须创建详细的变更日志

**Log Entries**:

-   修改的函数列表
-   参数变化详情
-   影响范围说明
-   迁移指南

**Scenario**:

-   可追踪性：可以追踪所有变更
-   迁移指导：开发者知道如何适配变更
-   验证：变更日志完整准确

## 部署要求

### 20. 部署验证

**Requirement**: 必须在部署前进行充分验证

**Validation Steps**:

-   代码审查：同行代码审查通过
-   测试验证：所有测试通过
-   静态分析：静态分析工具无警告

**Scenario**:

-   开发环境：在开发环境验证修复
-   测试环境：在测试环境验证兼容性
-   验证：部署检查清单完整通过

### 21. 监控设置

**Requirement**: 必须设置适当的监控和告警

**Monitoring Points**:

-   函数调用成功率
-   参数传递错误率
-   性能指标
-   错误日志

**Scenario**:

-   实时监控：系统状态实时可见
-   告警机制：问题发生时及时通知
-   验证：监控仪表板正常工作

## 成功标准

### 功能成功标准

-   [ ] 传入的 task_id 被 100%正确使用
-   [ ] 临时文件路径 100%基于传入的任务 ID
-   [ ] 0 个随机生成的 task_id

### 测试成功标准

-   [ ] 单元测试覆盖率 ≥ 90%
-   [ ] 集成测试通过率 = 100%
-   [ ] 回归测试通过率 = 100%
-   [ ] 性能基准测试无退化

### 质量成功标准

-   [ ] 代码审查通过
-   [ ] 静态分析无错误
-   [ ] 类型检查无警告
-   [ ] 文档完整准确

### 部署成功标准

-   [ ] 开发环境验证通过
-   [ ] 测试环境验证通过
-   [ ] 生产环境部署成功
-   [ ] 监控指标正常

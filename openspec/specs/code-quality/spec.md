# code-quality Specification

## Purpose
TBD - created by archiving change audit-redundant-code. Update Purpose after archive.
## Requirements
### Requirement: 统一配置加载

系统 SHALL 使用统一的配置加载机制,所有服务 MUST 从 `services.common.config_loader` 导入配置加载功能,禁止在各服务中实现独立的配置加载器。

#### Scenario: 服务使用统一配置加载器

- **WHEN** 任何 worker 服务需要加载全局配置
- **THEN** 必须使用 `from services.common.config_loader import get_config`
- **AND** 不得在服务内部实现独立的配置加载逻辑

#### Scenario: 禁止重复的配置加载器

- **WHEN** 代码审查发现服务内部有独立的配置加载器实现
- **THEN** 必须标记为违反 DRY 原则
- **AND** 必须重构为使用 common 模块的统一配置加载器

### Requirement: 模型管理抽象化

系统 SHALL 提供抽象的模型管理基类,所有 AI 模型服务 MUST 继承该基类并实现特定的模型加载和推理逻辑,避免在各服务中重复实现通用的模型管理功能。

#### Scenario: 创建新的模型服务

- **WHEN** 开发新的 AI 模型服务
- **THEN** 应继承 `BaseModelManager` 抽象基类
- **AND** 仅需实现特定的 `_load_model()` 和 `_inference()` 方法
- **AND** 通用功能(健康检查、配置加载、缓存)由基类提供

#### Scenario: 模型管理器包含通用功能

- **WHEN** `BaseModelManager` 基类被设计
- **THEN** 必须包含以下通用功能:
  - 配置加载和验证
  - 模型健康检查接口
  - 模型缓存机制
  - 错误处理和日志记录
- **AND** 子类通过覆盖抽象方法实现特定逻辑

### Requirement: 工作流任务基类

系统 MUST 提供统一的工作流任务基类,自动处理状态管理、错误处理和上下文传递,所有工作流任务 SHALL 继承该基类以避免重复的状态管理代码。

#### Scenario: 创建新的工作流任务

- **WHEN** 开发新的 Celery 工作流任务
- **THEN** 必须继承 `WorkflowTask` 基类
- **AND** 仅需实现 `execute(workflow_context)` 方法
- **AND** 状态管理(IN_PROGRESS, SUCCESS, FAILED)由基类自动处理

#### Scenario: 任务执行自动状态管理

- **WHEN** 工作流任务开始执行
- **THEN** 基类自动设置阶段状态为 IN_PROGRESS
- **WHEN** 任务执行成功
- **THEN** 基类自动设置阶段状态为 SUCCESS 并记录结果
- **WHEN** 任务执行失败
- **THEN** 基类自动设置阶段状态为 FAILED 并记录错误信息

#### Scenario: 避免重复的状态更新代码

- **WHEN** 代码审查发现任务中有手动的状态更新逻辑
- **THEN** 应标记为可优化项
- **AND** 建议重构为使用 `WorkflowTask` 基类

### Requirement: 异常处理最佳实践

系统 SHALL 使用具体的异常类型而非宽泛的 `Exception`,并 MUST 提供统一的异常处理装饰器,以提高错误定位的精确性和代码的可维护性。

#### Scenario: 捕获具体异常类型

- **WHEN** 编写异常处理代码
- **THEN** 应优先捕获具体的异常类型(如 `FileNotFoundError`, `ValueError`, `ConnectionError`)
- **AND** 仅在确实需要捕获所有异常时才使用 `Exception`
- **AND** 必须记录详细的错误上下文信息

#### Scenario: 使用异常处理装饰器

- **WHEN** 函数需要统一的异常处理逻辑
- **THEN** 应使用 `@handle_exceptions` 装饰器
- **AND** 装饰器应提供结构化的错误日志
- **AND** 装饰器应支持自定义错误处理回调

#### Scenario: 避免过于宽泛的异常捕获

- **WHEN** 代码审查发现过多的 `except Exception as e:` 模式
- **THEN** 应标记为代码质量问题
- **AND** 建议重构为更具体的异常类型或使用装饰器

### Requirement: GPU 锁使用标准化

系统 MUST 标准化 GPU 锁装饰器的参数使用,所有 GPU 密集型任务 SHALL 使用一致的超时和轮询间隔配置。

#### Scenario: GPU 任务使用标准参数

- **WHEN** 编写 GPU 密集型任务
- **THEN** 必须使用 `@gpu_lock(timeout=1800, poll_interval=0.5)` 装饰器
- **AND** 除非有特殊需求,否则应使用标准参数值
- **AND** 特殊参数需求必须在代码注释中说明原因

#### Scenario: GPU 锁参数一致性检查

- **WHEN** 代码审查发现 GPU 锁参数不一致
- **THEN** 应标记为需要标准化
- **AND** 除非有文档说明的特殊原因,否则应统一为标准参数

### Requirement: 代码冗余审计流程

系统 SHALL 建立定期的代码冗余审计流程,MUST 使用自动化工具和人工审查相结合的方式,持续识别和消除代码重复。

#### Scenario: 定期执行冗余代码扫描

- **WHEN** 每个开发迭代结束
- **THEN** 应运行自动化代码重复检测工具
- **AND** 生成冗余代码报告
- **AND** 将高优先级问题纳入下一迭代的重构计划

#### Scenario: 代码审查包含冗余检查

- **WHEN** 进行代码审查 (Code Review)
- **THEN** 审查者应检查是否存在与现有代码的重复
- **AND** 如发现重复,应要求重构或提取为共享组件
- **AND** 重复代码不应被合并到主分支

#### Scenario: 维护冗余代码清单

- **WHEN** 发现新的代码冗余问题
- **THEN** 应记录到冗余代码清单文档
- **AND** 标记优先级 (P0-P3)
- **AND** 分配责任人和目标修复时间


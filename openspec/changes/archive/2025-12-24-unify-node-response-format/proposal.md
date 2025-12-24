# Proposal: 统一节点响应格式与参数处理

## 概述

当前系统中的 18 个工作流节点在响应格式、字段命名、参数处理和 MinIO URL 生成等方面存在严重的不一致性问题。这导致客户端集成困难、文档维护成本高、代码复用性差。本提案旨在建立统一的节点响应规范，确保所有节点遵循一致的接口契约。

## 问题陈述

### 当前问题

1. **响应结构不统一**：存在至少 3 种不同的返回格式
   - 类型 A：完整 WorkflowContext（大多数节点）
   - 类型 B：简化 success/data 结构（pyannote_audio 部分节点）
   - 类型 C：普通任务字典（indextts.generate_speech）

2. **字段命名不规范**：MinIO URL 字段命名混乱
   - `audio_path` → `audio_path_minio_url` ✅
   - `keyframe_dir` → `keyframe_minio_url` ❌（缺少 `_dir`）
   - `multi_frames_path` → `multi_frames_minio_url` ❌（缺少 `_path`）

3. **复用判定机制不透明**：
   - 判定字段不统一（有的检查单个字段，有的检查多个可选字段）
   - 文档说明与实际输出不匹配

4. **参数处理不一致**：
   - "智能源选择"逻辑模糊，回退顺序不明确
   - 必需参数标记矛盾
   - 默认值表述不统一

5. **数据溯源不规范**：
   - 来源标记字段位置不统一（input_params / output / input_summary）
   - 缺乏显式的依赖图

## 目标

1. **统一响应格式**：所有节点强制使用 WorkflowContext 结构
2. **规范字段命名**：建立清晰的命名约定和验证机制
3. **标准化参数处理**：统一参数验证、默认值和智能回退逻辑
4. **透明化复用判定**：明确缓存键生成规则
5. **规范化数据溯源**：统一的来源标记字段和依赖链追踪

## 范围

### 包含内容

- 定义 `BaseNodeExecutor` 抽象基类
- 创建 `NodeResponseValidator` 验证器
- 建立 `MinioUrlNamingConvention` 命名规范
- 实现 `ParameterResolver` 增强版
- 设计 `CacheKeyStrategy` 接口
- 更新所有 18 个节点以符合新规范
- 更新 API 文档以反映统一格式

### 不包含内容

- 修改 WorkflowContext 核心结构（保持向后兼容）
- 改变现有的 Celery 任务签名
- 重构 StateManager 核心逻辑（仅增强）

## 利益相关者

- **API 用户**：获得一致的响应格式，简化客户端集成
- **文档维护者**：减少文档维护成本，消除矛盾
- **开发者**：通过代码复用减少重复工作
- **测试工程师**：统一的测试模式，提高测试覆盖率

## 风险与缓解

### 风险

1. **向后兼容性**：现有客户端可能依赖当前的响应格式
2. **迁移成本**：18 个节点需要逐一迁移
3. **性能影响**：额外的验证可能增加响应时间

### 缓解措施

1. **分阶段迁移**：
   - 阶段 1：建立基础设施（BaseNodeExecutor、验证器）
   - 阶段 2：迁移高优先级节点（FFmpeg、Faster-Whisper）
   - 阶段 3：迁移剩余节点
   - 阶段 4：废弃旧格式

2. **兼容性层**：
   - 提供 `legacy_format` 参数支持旧格式
   - 在响应头中添加 `X-Response-Format-Version` 标识

3. **性能优化**：
   - 验证逻辑仅在开发/测试环境启用严格模式
   - 生产环境使用轻量级验证

## 成功标准

1. 所有 18 个节点返回统一的 WorkflowContext 结构
2. MinIO URL 字段命名 100% 符合 `{field_name}_minio_url` 规范
3. 所有节点通过 `NodeResponseValidator` 验证
4. API 文档无矛盾，所有示例与实际输出一致
5. 单元测试覆盖率 ≥ 90%
6. 集成测试验证所有节点的响应格式

## 时间线

- **第 1 周**：设计和评审规范文档
- **第 2-3 周**：实现基础设施（BaseNodeExecutor、验证器）
- **第 4-6 周**：迁移节点（分 3 批）
- **第 7 周**：更新文档和测试
- **第 8 周**：集成测试和性能验证

## 替代方案

### 方案 A：渐进式改进（当前提案）
- 优点：风险可控，向后兼容
- 缺点：迁移周期长

### 方案 B：大爆炸式重构
- 优点：快速统一
- 缺点：高风险，可能破坏现有集成

### 方案 C：仅文档修复
- 优点：成本最低
- 缺点：不解决根本问题

**推荐方案**：方案 A（渐进式改进）

## 依赖关系

- 依赖现有的 `WorkflowContext` 和 `StageExecution` 模型
- 依赖 `StateManager` 的 MinIO 上传逻辑
- 需要更新 `single_task_api.py` 以支持新的验证层

## 开放问题

1. 是否需要为旧客户端提供永久的兼容性层？
2. 复用判定逻辑是否应该从节点代码中提取到独立的 `CacheManager`？
3. 是否需要在响应中添加 JSON Schema 引用以支持客户端自动验证？

## 附录

### 相关文档
- `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
- `services/common/context.py`
- `services/api_gateway/app/single_task_models.py`

### 相关规范
- `openspec/specs/single-task-api-docs/`
- `openspec/specs/project-architecture/`

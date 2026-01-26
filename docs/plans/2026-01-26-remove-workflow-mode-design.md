# 删除工作流模式设计文档

## 背景
项目模式调整，各功能节点改造成独立 API 服务，仅保留单节点模式 `/v1/tasks`。工作流链路（`/v1/workflows`、增量执行、链式调度）不再对外提供。

## 目标
- 删除工作流模式入口与执行链路，只保留单节点 API。
- 清理工作流相关文档与示例，避免误导。
- 现有单节点模式行为不变。

## 范围与边界
- **删除**：`/v1/workflows` 创建、增量/重试执行、状态查询接口及其实现模块。
- **删除**：工作流示例与工作流参考文档。
- **保留**：`/v1/tasks` 单节点 API 与内部 `WorkflowContext` 结构（字段命名不强制改动）。
- **不做**：对内部 `workflow_id` 的字段重命名或状态管理的全面重构。

## 方案概述
1. API Gateway 中移除工作流请求/响应模型、路由、创建/增量执行逻辑。
2. 删除 `workflow_factory.py` 与 `incremental_utils.py`。
3. 文档与示例从“工作流模式”转为“仅单节点模式”，并删除工作流示例文件。

## 影响范围
- **服务端**：仅 API Gateway 需要变更，其他 worker 不受影响。
- **对外接口**：`/v1/workflows` 不再响应，客户端将收到 404。
- **文档**：产品与技术文档中涉及 `/v1/workflows` 的内容需要删除或替换。

## 文件清单
**删除**
- `services/api_gateway/app/workflow_factory.py`
- `services/api_gateway/app/incremental_utils.py`
- `docs/technical/reference/WORKFLOW_NODES_REFERENCE.md`
- `docs/technical/reference/WORKFLOW_EXAMPLES_GUIDE.md`
- `config/examples/workflow_examples.yml`

**修改**
- `services/api_gateway/app/main.py`
- `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
- `docs/product/SDD.md`
- `docs/product/SYSTEM_ARCHITECTURE.md`
- `docs/technical/IMPLEMENTATION_SUMMARY.md`

## 风险与回滚
- **风险**：旧客户端调用 `/v1/workflows` 直接 404。
- **回滚**：恢复工作流模块与路由注册即可回滚（本次删除将完全移除入口）。

## 验证策略
- 基线测试（容器内）：`docker exec -it api_gateway pytest /app/tests -v`
- 变更后回归：同上

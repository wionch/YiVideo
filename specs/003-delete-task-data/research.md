# 研究: 任务删除 API 节点

## 工具可用性
- sequential-thinking：用于梳理待确认项与优先级。
- serena：对齐仓库现有文档与术语，引用 `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md` 的删除接口说明（目录/MinIO 删除示例）。 
- context7：查阅 FastAPI 路由/Path Operation 组织与依赖配置的官方文档，以确保契约描述符合框架常规（来源 `/fastapi/fastapi`）。
- 所有 MCP 工具可用，无需降级；宪章文件为空模板，已在下方单独注明。

## 研究问题
1. 删除端点的 HTTP 形态（是否使用 DELETE/POST；如何承载 `force` 标志）。
2. 响应结构：如何表达本地目录、Redis、MinIO 的逐项结果与整体状态。
3. 运行/排队任务的强制删除策略与默认安全模式。
4. 与现有文档的术语与路径对齐（目录删除、MinIO 删除说明）。
5. 鉴权与幂等性：是否沿用现有单任务接口的鉴权、并确保重复调用无副作用。
6. 宪章缺失：需记录假设，不阻断研究。

## 发现与决策

### F1: 端点形态与方法
- **决策**：使用 `POST /v1/tasks/{task_id}/delete`，请求体承载 `force`（默认 false）。保持幂等语义但允许强制删除需要请求端显式声明。  
- **理由**：DELETE 请求体在部分客户端/代理存在兼容性争议；POST 可携带 JSON 并保留清晰语义，同时与现有文档风格（示例用 DELETE 携带 query）保持一致的路径参数模式。  
- **考虑的替代方案**：`DELETE /v1/tasks/{task_id}?force=true`（受限于 query 传布尔且不可扩展）；`DELETE` 带请求体（跨代理支持差）。  
- **证据**：FastAPI 对 Path Operation 的通用支持（context7 `/fastapi/fastapi`，路径操作配置与依赖可嵌套）；现有删除接口采用 DELETE + query（`docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:1329-1351`）。

### F2: 响应结构与幂等性
- **决策**：响应包含整体状态（success/partial_failed/failed）与 per-resource 结果列表（resource=local_directory|redis|minio，status=deleted/skipped/failed，message，可重试标志），幂等：缺失资源视为 deleted/skipped。  
- **理由**：需求要求三类资源均需覆盖，且需告知部分失败与重试指引；幂等是规范 FR-006/FR-007 的核心。  
- **考虑的替代方案**：仅返回布尔 success（无法表达部分失败）。  
- **证据**：规范 FR-001/FR-005/FR-006/FR-007；现有文件删除/目录删除示例的 success + message 结构（`docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:1329-1351`）。

### F3: 运行/排队任务策略与 force
- **决策**：默认安全模式拒绝运行/排队任务删除并提示稍后重试；当 `force=true` 时允许立即清理并在响应中标记风险与实际结果。  
- **理由**：避免中断正在执行的任务；规范边缘情况已约定此策略。  
- **考虑的替代方案**：排队等待终态后再删（增加复杂度且延迟不可控）。  
- **证据**：规范边缘情况与 FR-008（`specs/003-delete-task-data/spec.md:53-88`）。

### F4: 鉴权与安全
- **决策**：沿用现有单任务接口鉴权/权限模式（与 `/v1/tasks` 一致）；拒绝未授权删除。  
- **理由**：规范 FR-002 要求；当前文档对单任务接口默认鉴权一致。  
- **考虑的替代方案**：单独权限域（未在需求中提出）。  
- **证据**：规范 FR-002；现有单任务接口文档作为参考（`docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`）。

### F5: 宪章缺失
- **决策**：将宪章内容缺失标记为 NEEDS CLARIFICATION，不阻塞计划，但在后续设计/实现中需复核或等待补充。  
- **理由**：`.specify/memory/constitution.md` 为空模板，无法执行门控。  
- **考虑的替代方案**：阻塞规划（与命令目标相悖）。  
- **证据**：`.specify/memory/constitution.md` 内容为空。

### F6: 数据模型范围
- **决策**：`TaskDeletionRequest`（task_id, force=false）；`TaskDeletionResult`（status, results[], warnings[] 可选，timestamp）。  
- **理由**：覆盖三类资源结果并支撑幂等/部分失败反馈。  
- **考虑的替代方案**：分开三个端点（与“单节点删除”需求不符）。  
- **证据**：规范 FR-001..FR-009。

## 结论
- 使用 POST + JSON 体承载 force，保持幂等、可扩展且与现有文档风格兼容。
- 响应需分资源汇总状态，缺失资源视为成功/跳过，异常需标记可重试。
- 默认安全模式，force 明确突破限制；鉴权沿用现有单任务接口。
- 宪章缺失已记录，不阻塞后续阶段。

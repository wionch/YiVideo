## 1. 方案与范围确认
- [x] 1.1 以 `services/api_gateway/app/single_task_api.py:get_supported_tasks` 为准确认单任务节点清单，与 `WORKFLOW_NODES_REFERENCE.md` 交叉比对是否齐全。
- [x] 1.2 确认文件操作端点范围：`/v1/files/directories`、`/v1/files/{file_path}`、`/v1/files/upload`、`/v1/files/download/{file_path}`。
- [x] 1.3 确定 HTTP API 文档承载位置（独立参考文档 + 在节点文档中添加索引/链接），遵循 `docs/DOCUMENT_WRITING_GUIDELINES.md`，并统一示例格式、时间/URL 示例值。

## 2. 数据与示例收集
- [x] 2.1 从 `SingleTaskResponse`、`WorkflowContext`、`state_manager`、`callback_manager` 提取同步响应、状态查询、callback 载荷的字段与示例，形成通用章节（统一示例时间/URL）。
- [x] 2.2 按节点逐项核对代码（Celery 任务实现）与节点文档，整理必填/可选参数、默认值/回退逻辑、输出字段；生成统一格式的请求与回调 JSON 示例。
- [x] 2.3 收集 `/v1/files` 端点的请求/响应字段与约束（路径安全、桶名默认、幂等行为），并产出示例。

## 3. 文档编写与对齐
- [x] 3.1 编写单任务 HTTP API 总览章节（端点、字段表、成功/失败示例、`WorkflowContext` 结构）。
- [x] 3.2 为所有单任务节点编写独立小节，统一格式（描述→请求样例→同步响应→结果查询→callback→参数/输出表），并从节点功能文档或索引可跳转。

## 4. 校验与输出
- [x] 4.1 自查字段命名与示例值与代码保持一致（task_id/task_name/callback_url/stages.*.status/output/error/duration 等）。
- [x] 4.2 运行 `openspec validate add-single-task-api-docs --strict`，确保变更通过校验；补充“最后更新”标识与引用链接。

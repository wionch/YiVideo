# Research: add-n8n-audio-separation-nodes

## 结论（TL;DR）

要在 n8n 工作流 `YiVideoNodes` 中新增“提取人声 + 全部音轨”节点模板，最小可行路径是复用 YiVideo 单步任务接口 `POST /v1/tasks` 调用 `audio_separator.separate_vocals`，并在回调 payload 中稳定提供 **人声** 与 **完整音轨列表** 两类产物的 MinIO URL。

新增确认需求：**单步请求（`input_data.audio_separator_config.model_name`）必须能够覆盖 `config.yml` 中的模型设置，且优先级高于全局配置**。目前代码未读取 `input_data`，需要在实施阶段补齐并明确优先级。

当前代码/文档存在 3 个阻断点，需要在实施阶段一并修复后，n8n 节点才能“开箱可用”：

1. `audio_separator.separate_vocals` 的 worker 输出仅包含 `vocal_audio` / `audio_list`，无法明确告诉调用方“全部拆分音轨有哪些”，也无法应对非传统“人声 vs 伴奏”的模型。
2. 单步模式下 `input_data.model_name/quality_mode`（以及 `input_data.audio_separator_config`）并未在 `audio_separator` worker 中被读取，和节点参考文档不一致。
3. API Gateway 单任务结果上传 MinIO 的提取逻辑未包含 `vocal_audio`/`all_audio_files` 字段，导致即便生成了分离文件，也无法通过 callback 的 `minio_files` 暴露给 n8n。

## 已核对的证据（MCP + Repo）

### 1) 单步任务接口与支持的任务

- 单任务 API 路由：`services/api_gateway/app/single_task_api.py`
  - 创建任务：`POST /v1/tasks`
  - 查询：`GET /v1/tasks/{task_id}/status`、`GET /v1/tasks/{task_id}/result`
  - 支持任务列表中包含 `audio_separator.separate_vocals`：`services/api_gateway/app/single_task_api.py`

### 2) audio_separator worker 的输出结构与参数读取现状

- 任务实现：`services/workers/audio_separator_service/app/tasks.py`
- 日志打印了 `result.get('instrumental')`，但 `StageExecution.output` 仅包含 `audio_list` 与 `vocal_audio`，缺少“一次性列出全部音轨”的结构，n8n 很难泛化到其它模型拆分结果。
  - 质量/模型相关参数当前从 `audio_separator_config`（位于 `workflow_context.input_params` 或 node_params 解析后）读取；单任务模式下这些信息通常在 `input_data` 里，当前没有对齐读取逻辑，也没有明确“请求覆盖全局配置”的优先级。
- 默认模型配置：`services/workers/audio_separator_service/app/config.py`
  - `default_model` 默认值为 `UVR-MDX-NET-Inst_HQ_5.onnx`，满足“必须使用该模型”的目标，但 n8n 节点仍需要显式固定以避免配置漂移。

### 3) API Gateway 回调与 MinIO 文件暴露机制

- callback payload 结构：`services/api_gateway/app/callback_manager.py`
  - 回调字段：`task_id`、`status`、`result`、（可选）`minio_files`
- 单任务结果上传逻辑：`services/api_gateway/app/single_task_executor.py`
- `_extract_file_paths` 仅识别少量 key（如 `audio_path`、`video_path` 等），不包含 `vocal_audio`、`all_audio_files` 等字段，因此音频分离产物无法进入 `minio_files`。

### 4) n8n 工作流模板现状（目标工作流）

- 已读取目标工作流结构：n8n workflow `YiVideoNodes`（id: `ijOqn9Dh0EX32tN5`）
  - 存在多组 “HTTP Request -> Wait(webhook)” 的模板化节点，用于调用 `POST http://api_gateway/v1/tasks` 并等待 callback。
  - 当前未包含 `audio_separator.separate_vocals` 的节点模板，需要新增。

## Context7 外部文档要点（第三方依赖）

通过 Context7 查阅 `/nomadkaraoke/python-audio-separator`：

- 模型加载使用 `separator.load_model(model_filename=...)`，与我们要求固定 `UVR-MDX-NET-Inst_HQ_5.onnx` 的方式一致。
- 分离输出通常包含 Vocals / Instrumental / Other 等 stem 文件，需要一种“vocal + all” 的抽象来兼容不同模型。

## 风险与注意事项

1. **模型文件可用性**：需要确认 `UVR-MDX-NET-Inst_HQ_5.onnx` 在 `audio_separator_service` 容器内可访问（通过模型卷映射或预置缓存）。否则单任务会失败，n8n 节点无法稳定运行。
2. **回调 URL 可达性与安全校验**：`services/api_gateway/app/callback_manager.py` 会拒绝 `localhost/127.0.0.1/.local`，n8n 的 `resumeUrl` 必须是 API Gateway 容器可访问的域名/地址。
3. **长耗时与 n8n 超时**：音频分离耗时可能较长，应保持异步回调模式（HTTP Request 仅提交任务，Wait 节点等待回调），避免同步阻塞。

## 待确认问题（需要产品/集成侧拍板）

1. “all” 的定义需确认：是否直接透出 audio-separator 提供的所有轨道？若模型只输出 2 轨，则 `all` 就是 2 条；若输出 4 轨，则需保证顺序与文件名保持一致，供 UI/下游选择。
2. n8n 节点输出字段命名：建议固定为 `vocals_url` 与 `all_audio_urls`；若已有既定命名规范，请以规范为准。

## 推荐方案（含取舍）

推荐：在 `YiVideoNodes` 中新增一组节点模板（HTTP Request + Wait + 可选的 URL 提取节点）：

- 请求节点固定调用 `audio_separator.separate_vocals`，并在请求体中固定 `model_name = UVR-MDX-NET-Inst_HQ_5.onnx`（通过 `input_data.audio_separator_config.model_name`）。
- Wait 节点通过 webhook resume 等待 YiVideo callback。
- 提取节点从 callback payload 的 `minio_files` 或 `result` 中提取并输出 `vocals_url` 与 `all_audio_urls`。

取舍：

- 复用现有 `audio_separator.separate_vocals`（而不是新增一个 `audio_separator.separate_background`）能避免引入新 Celery task 名称与队列管理；但需要在结果结构中补齐“vocal + all” 两种语义，且需要让 API Gateway 能上传并暴露这些文件。
- 明确参数优先级：`input_data.audio_separator_config`（或 `node_params.audio_separator_config`）应优先于 `config.yml` 默认值，以满足“指定 `UVR-MDX-NET-Inst_HQ_5.onnx`”的需求，并让 `model_used` 回传真实生效的模型。

# Change: 在 n8n 工作流中新增音频人声/多轨分离节点（固定 UVR-MDX-NET-Inst_HQ_5.onnx）

## Why

- 现有 `YiVideoNodes` 工作流缺少可直接调用 `audio_separator.separate_vocals` 并输出“人声 + 全部音轨”两类产物的节点模板，导致 n8n 侧无法低成本复用 YiVideo 的音频分离能力。
- 需求要求统一使用 `UVR-MDX-NET-Inst_HQ_5.onnx` 模型，避免工作流在不同环境/配置下得到不一致结果。

## What Changes

- 在 n8n 工作流 `YiVideoNodes`（id: `ijOqn9Dh0EX32tN5`）新增节点模板：
  - `HTTP Request`：调用 `POST http://api_gateway/v1/tasks`，`task_name="audio_separator.separate_vocals"`，并在 `input_data` 中固定 `audio_separator_config.model_name="UVR-MDX-NET-Inst_HQ_5.onnx"`。
  - `Wait`：webhook resume 等待 YiVideo callback。
  - （可选）`Code/Set`：从 callback payload 解析并输出 `vocals_url` 与 `all_audio_urls` 两个字段。
- 对齐 YiVideo 单任务模式与回调结果：
  - audio_separator worker 输出仅保留 `vocal_audio` 与 `all_audio_files` 两个层级，使不同模型拆分的轨道都能被 n8n 感知。
  - API Gateway 的单任务结果上传逻辑覆盖所有音轨，并在回调中提供 `vocal_audio_minio_url` 与 `all_audio_minio_urls`。
  - **实现单步请求参数的优先级**：`input_data.audio_separator_config`（或 node_params）中的模型设置必须优先于 `config.yml` 默认值，确保指定 `UVR-MDX-NET-Inst_HQ_5.onnx` 时立即生效，并在 `model_used` 中如实反映。
- 补充 OpenSpec 规格：`n8n-integration` 与 `audio-separator-service`。

## Impact

- 影响规格：`n8n-integration`、`audio-separator-service`
- 影响范围：
  - n8n 工作流模板（`YiVideoNodes`）
  - YiVideo 单任务模式的音频分离输出/回调数据一致性

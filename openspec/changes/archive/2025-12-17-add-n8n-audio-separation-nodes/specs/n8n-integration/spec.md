## ADDED Requirements

### Requirement: Audio Separator 人声/多轨分离节点（固定 UVR-MDX-NET-Inst_HQ_5.onnx）

系统 SHALL 在 n8n 工作流 `YiVideoNodes` 中提供调用 `audio_separator.separate_vocals` 的节点模板，用于从输入音频中获得“人声”以及“全部分离音轨（all）”两类产物，并强制使用 `UVR-MDX-NET-Inst_HQ_5.onnx` 模型。

#### Scenario: 配置 Audio Separator 请求节点

- **GIVEN** 需要在 n8n 发起音频分离任务
- **WHEN** 配置 HTTP Request 节点调用 YiVideo 单任务 API
- **THEN** 节点配置必须包含：
  - method: "POST"
  - url: "http://api_gateway/v1/tasks"
  - sendBody: true, specifyBody: "json"
  - jsonBody: 包含
    - task_name="audio_separator.separate_vocals"
    - task_id（占位符/变量）
    - callback（指向 Wait 节点的 resumeUrl 路径）
    - input_data.audio_path（示例：MinIO URL）
    - input_data.audio_separator_config.model_name="UVR-MDX-NET-Inst_HQ_5.onnx"

#### Scenario: 配置 Audio Separator Wait 节点

- **GIVEN** 需要等待 `audio_separator.separate_vocals` 的回调
- **WHEN** 配置 n8n Wait 节点
- **THEN** 节点配置必须包含：
  - resume: "webhook"
  - httpMethod: "POST"
  - options.webhookSuffix: 唯一的步骤标识符（例如 "t_audio_sep"）
  - 与请求节点通过主线连接，确保回调命中该 Wait 节点

#### Scenario: 获取人声与全部音轨的输出 URL

- **GIVEN** YiVideo 已通过 callback 返回 `result` 与 `minio_files`
- **WHEN** n8n 需要将分离结果作为后续节点输入
- **THEN** 工作流应能得到两个字段：
  - `vocals_url`（人声音频下载 URL）
  - `all_audio_urls`（数组，包含该次分离产生的所有音轨下载 URL，至少含一条与 `vocals_url` 相同）
- **AND** 这两个字段来源 SHOULD 优先使用 callback 的 `minio_files`（避免依赖 `/share` 挂载）

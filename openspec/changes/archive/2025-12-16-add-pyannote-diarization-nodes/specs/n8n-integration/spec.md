## ADDED Requirements

### Requirement: Pyannote 说话人分离节点

系统 SHALL 在 n8n 工作流中提供调用 `pyannote_audio.diarize_speakers` 的节点模板，并通过 webhook Wait 节点等待回调。

#### Scenario: 配置 Pyannote 请求节点

- **GIVEN** 需要在 n8n 发起说话人分离任务
- **WHEN** 配置 HTTP Request 节点调用 YiVideo 单任务 API
- **THEN** 节点配置必须包含：
  - method: "POST"
  - url: "http://api_gateway/v1/tasks"
  - sendBody: true, specifyBody: "json"
  - jsonBody: 包含 task_name="pyannote_audio.diarize_speakers", task_id、callback（指向 Wait 节点的 resumeUrl 路径）、input_data.audio_path 示例（MinIO URL）

#### Scenario: 配置 Pyannote Wait 节点

- **GIVEN** 需要等待 `pyannote_audio.diarize_speakers` 的回调
- **WHEN** 配置 n8n Wait 节点
- **THEN** 节点配置必须包含：
  - resume: "webhook"
  - httpMethod: "POST"
  - options.webhookSuffix: 唯一的步骤标识符
  - 与请求节点通过主线连接，确保回调命中该 Wait 节点

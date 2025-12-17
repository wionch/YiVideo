## 1. Implementation

- [x] 1.1 按现有模式在 `YiVideoNodes` 增加 `pyannote_audio.diarize_speakers` HTTP 请求节点（POST /v1/tasks，callback=wait webhook）。
- [x] 1.2 增加对应 Wait 节点，使用 webhook resume，webhookSuffix 唯一，连接到请求节点输出。
- [x] 1.3 确认节点参数示例使用 MinIO 输入路径，任务 ID/回调占位符合现有模板。
- [x] 1.4 更新 n8n 集成规范，补充 Pyannote 说话人分离节点配置与等待要求。
- [x] 1.5 运行 `openspec validate add-pyannote-diarization-nodes --strict`，确保规范通过校验。

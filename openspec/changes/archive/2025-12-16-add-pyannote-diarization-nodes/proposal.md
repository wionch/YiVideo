# Change: 在 n8n 工作流中新增 Pyannote 说话人分离请求节点与 Wait 节点

## Why

- 现有 `YiVideoNodes` 工作流缺少调用 `pyannote_audio.diarize_speakers` 的节点模板，无法在 n8n 中直接发起说话人分离任务并等待回调。

## What Changes

- 新增一个 HTTP Request 节点模板，按 YiVideo 规范调用 `pyannote_audio.diarize_speakers`，包含回调和 MinIO 输入参数示例。
- 新增配套 Wait 节点，使用 webhook resume 方式等待 `pyannote_audio` 回调。
- 补充 n8n 集成规范，明确 Pyannote 说话人分离节点的配置和数据依赖。

## Impact

- 影响规格：`n8n-integration`
- 影响范围：n8n 工作流模板（`YiVideoNodes`）

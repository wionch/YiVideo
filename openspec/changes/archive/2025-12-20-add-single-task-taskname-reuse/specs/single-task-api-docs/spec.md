## ADDED Requirements

### Requirement: 单任务复用文档覆盖
`SINGLE_TASK_API_REFERENCE.md` SHALL 描述按 `task_id+task_name` 的复用流程、返回字段，并在所有单任务节点小节中给出复用判定规则与示例字段。

#### Scenario: 通用接口复用说明
- **WHEN** 文档描述 `POST /v1/tasks`、`GET /v1/tasks/{task_id}/status`、`GET /v1/tasks/{task_id}/result` 或回调载荷
- **THEN** 必须说明在执行前检查 Redis 中 `(task_id, task_name)` 成功阶段的逻辑以及复用全局开关的默认开启/关闭效果
- **AND** 示例 SHALL 展示 `reuse_info`（含 `reuse_hit`、`task_name`、`source`、`cached_at` 可选）在命中/未命中情况下的取值
- **AND** 命中复用的响应/回调输出字段（含 `stages[task_name].output/status/duration/error` 与顶层字段） SHALL 与实际执行成功时一致，仅附加 `reuse_info`

#### Scenario: 节点级复用判定字段
- **WHEN** 文档展示任一单任务节点小节（`ffmpeg.extract_keyframes/extract_audio/crop_subtitle_images/split_audio_segments`、`faster_whisper.transcribe_audio`、`audio_separator.separate_vocals`、`pyannote_audio.*`、`paddleocr.*`、`indextts.generate_speech`、`wservice.*`）
- **THEN** 小节 SHALL 说明该节点用于复用判定的主要输出字段（至少表明需要成功状态且 `output` 非空），并给出命中时的返回形态与 `reuse_info` 取值

## ADDED Requirements

### Requirement: 说话人分离结果可外部访问
说话人分离任务 MUST 在成功时将结果文件上传到对象存储，并在输出中返回可供外部访问的 MinIO URL，同时保留本地路径以兼容后续处理。

#### Scenario: 结果上传并返回 URL
- **WHEN** `pyannote_audio.diarize_speakers` 任务完成并生成 `diarization_result.json`
- **THEN** 结果文件被上传到 MinIO
- **AND** 输出包含本地路径和 MinIO URL（如 `diarization_file` 与 `diarization_file_minio_url`）供回调/下游使用

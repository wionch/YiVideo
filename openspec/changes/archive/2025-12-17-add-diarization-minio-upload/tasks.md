## 1. 实施
- [x] 1.1 在 `pyannote_audio.diarize_speakers` 成功分支上传 `diarization_result.json` 到 MinIO，生成 URL 字段（保留本地路径）。
- [x] 1.2 上传失败仅记 warning，不让任务失败。
- [x] 1.3 更新输出结构，新增 MinIO URL 返回给回调。

## 2. 验证
- [x] 2.1 重跑 `pyannote_audio.diarize_speakers`，回调包含 `diarization_file_minio_url` 且可访问。（已验证：callback 返回 URL 并成功访问）
- [x] 2.2 可选：调用 `get_speaker_segments` 使用 MinIO URL 输入，确认自动下载解析。（已验证：MinIO URL 可被 resolve_and_download 解析）

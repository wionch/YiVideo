# Research

## 结论
- 需求：pyannote diarization 结果目前仅返回本地路径 `/share/.../diarization_result.json`，需要上传到 MinIO 并返回可访问 URL。
- 现状：`services/workers/pyannote_audio_service/app/tasks.py` 在 `diarize_speakers` 中构造 `output_data['diarization_file'] = str(output_file)`，未上传。下载/上传工具集中在 `services/common/file_service.py`，提供 `upload_to_minio(local_file_path, object_name, bucket_name=None)`，返回 `http://{host}:{port}/{bucket}/{object}`。
- 影响：下游 `get_speaker_segments` 等函数用 `get_param_with_fallback` + `file_service.resolve_and_download`，已支持 MinIO URL，因此新增 URL 字段不会破坏现有解析。

## 证据（serena）
- `services/workers/pyannote_audio_service/app/tasks.py:304-335`：`output_data` 仅含本地 `diarization_file`。
- `services/workers/pyannote_audio_service/app/tasks.py:391+`、`506+`：下游处理使用 `file_service.resolve_and_download`，可消费 MinIO URL。
- `services/common/file_service.py:248-276`：`upload_to_minio` 封装，返回 MinIO HTTP URL。
- 对比参考：`services/workers/paddleocr_service/app/tasks.py:639-670` 在完成后上传 manifest 至 MinIO 并在输出增加 `manifest_minio_url`。

## context7
- 查询 `minio python` 获得 `/minio/minio-py` 文档候选，现有代码已使用 MinIO Python SDK，无需新增依赖。

## 未决问题
- 对象名规范：建议沿用 `workflow_id/diarization/diarization_result.json`，与当前共享目录结构一致。
- 是否上传后删除本地文件？需求未提，保持本地文件以兼容现有路径。

## 推荐方案
- 在 `diarize_speakers` 成功分支中调用 `file_service.upload_to_minio` 上传结果文件；输出增加字段 `diarization_file_minio_url`（保留本地路径）。
- 若上传失败，记录 warning 并继续返回本地路径，避免任务标记失败。
- 更新 spec delta：说话人分离结果必须上传 MinIO 并返回 URL。
- 验证：重跑 diarization 任务，回调包含新 URL；可选检查下游 `get_speaker_segments` 能解析 MinIO URL。

# Change: 说话人分离结果上传MinIO并返回URL

## Why
当前 pyannote 说话人分离仅返回本地路径，外部回调无法直接访问结果文件，需要上传到 MinIO 并返回 URL。

## What Changes
- 在 `pyannote_audio.diarize_speakers` 成功后上传 diarization 结果文件到 MinIO。
- 输出中新增 MinIO URL 字段，保留本地路径以兼容下游。
- 上传失败仅记录警告，不影响任务成功。

## Impact
- 代码：`services/workers/pyannote_audio_service/app/tasks.py`（增加上传逻辑和输出字段）。
- 规格：新增说话人分离输出上传能力（speaker-diarization）。

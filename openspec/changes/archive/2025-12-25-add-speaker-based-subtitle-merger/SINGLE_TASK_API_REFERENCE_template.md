#### wservice.merge_speaker_based_subtitles
复用判定：`stages.wservice.merge_speaker_based_subtitles.status=SUCCESS` 且 `output.merged_segments_file` 非空即命中复用；等待态返回 `status=pending`；未命中按正常流程执行。
功能概述（wservice.merge_speaker_based_subtitles）：基于说话人时间区间合并字幕，输出 segments 数量与 Diarization 一致（如 58 个），保留完整词级时间戳和匹配质量指标，用于说话人优先的字幕展示或对话分析。
请求体：
```json
{
  "task_name": "wservice.merge_speaker_based_subtitles",
  "task_id": "task-demo-001",
  "callback": "http://localhost:5678/webhook/demo-t1",
  "input_data": {
    "segments_file": "http://localhost:9000/yivideo/task-demo-001/transcribe_data.json",
    "diarization_file": "http://localhost:9000/yivideo/task-demo-001/diarization/diarization_result.json",
    "overlap_threshold": 0.5
  }
}
```
WorkflowContext 示例：
```json
{
  "workflow_id": "task-demo-001",
  "create_at": "2025-12-17T12:00:00Z",
  "input_params": {
    "task_name": "wservice.merge_speaker_based_subtitles",
    "input_data": {
      "segments_file": "http://localhost:9000/yivideo/task-demo-001/transcribe_data.json",
      "diarization_file": "http://localhost:9000/yivideo/task-demo-001/diarization/diarization_result.json",
      "overlap_threshold": 0.5
    },
    "callback_url": "http://localhost:5678/webhook/demo-t1"
  },
  "shared_storage_path": "/share/workflows/task-demo-001",
  "stages": {
    "wservice.merge_speaker_based_subtitles": {
      "status": "SUCCESS",
      "input_params": {
        "segments_file": "http://localhost:9000/yivideo/task-demo-001/transcribe_data.json",
        "diarization_file": "http://localhost:9000/yivideo/task-demo-001/diarization/diarization_result.json",
        "overlap_threshold": 0.5
      },
      "output": {
        "merged_segments_file": "/share/workflows/task-demo-001/merged_segments_speaker_based.json",
        "merged_segments_file_minio_url": "http://localhost:9000/yivideo/task-demo-001/merged_segments_speaker_based.json",
        "total_segments": 58,
        "matched_segments": 56,
        "empty_segments": 2
      },
      "error": null,
      "duration": 3.2
    }
  },
  "error": null
}
```
说明：输出文件包含 58 个 segments（与 Diarization 一致），每个 segment 包含匹配的词级时间戳和质量指标；若 `segments_file` 为本地且上传开关开启，state_manager 可能追加 `segments_file_minio_url`，原字段不覆盖。
参数表：
| 参数 | 类型 | 必需 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `segments_data` | array | 否 | - | 直接传入含词级时间戳的转录片段 |
| `speaker_segments_data` | array | 否 | - | 直接传入说话人片段数据 |
| `segments_file` | string | 否 | 智能源选择 | 未提供则回退 `faster_whisper.transcribe_audio` 输出 |
| `diarization_file` | string | 否 | 智能源选择 | 未提供则回退 `pyannote_audio.diarize_speakers` 输出 |
| `overlap_threshold` | float | 否 | 0.5 | 词级时间戳重叠阈值（0.0-1.0），控制部分重叠词的匹配策略 |

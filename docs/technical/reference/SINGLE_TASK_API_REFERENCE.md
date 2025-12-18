# 单任务与文件操作 HTTP API 参考

本文件与 FastAPI/Celery 实现及 `WorkflowContext` 数据结构对齐，提供 `/v1/tasks` 单任务调用与 `/v1/files` 文件操作接口的完整示例。示例统一使用：
- 基础地址：`http://localhost:8788`
- 示例任务：`task_id=task-demo-001`
- 示例回调：`http://localhost:5678/webhook/demo-t1`
- 示例时间：`2025-12-17T12:00:00Z`

## 通用：单任务接口 (`/v1/tasks`)

### 创建任务：POST /v1/tasks
请求体（字段同 `SingleTaskRequest`，适用于所有节点）：
```json
{
  "task_name": "ffmpeg.extract_audio",
  "task_id": "task-demo-001",
  "callback": "http://localhost:5678/webhook/demo-t1",
  "input_data": {
    "video_path": "http://localhost:9000/yivideo/task-demo-001/demo.mp4"
  }
}
```

同步响应（`SingleTaskResponse`，不含结果）：
```json
{
  "task_id": "task-demo-001",
  "status": "pending",
  "message": "任务已创建并开始执行"
}
```

### 查询状态：GET /v1/tasks/{task_id}/status
返回最新工作流状态（`WorkflowContext` 序列化）并附带运行态字段（`status`/`updated_at`/`minio_files`/`callback_status` 等）。示例基于 `ffmpeg.extract_audio` 成功：
```json
{
  "workflow_id": "task-demo-001",
  "status": "completed",
  "create_at": "2025-12-17T12:00:00Z",
  "input_params": {
    "task_name": "ffmpeg.extract_audio",
    "input_data": {
      "video_path": "http://localhost:9000/yivideo/task-demo-001/demo.mp4"
    },
    "callback_url": "http://localhost:5678/webhook/demo-t1"
  },
  "shared_storage_path": "/share/workflows/task-demo-001",
  "stages": {
    "ffmpeg.extract_audio": {
      "status": "SUCCESS",
      "input_params": {
        "video_path": "/share/workflows/task-demo-001/demo.mp4"
      },
      "output": {
        "audio_path": "http://localhost:9000/yivideo/task-demo-001/demo.wav"
      },
      "error": null,
      "duration": 2.6
    }
  },
  "minio_files": [
    {
      "name": "demo.wav",
      "url": "http://localhost:9000/yivideo/task-demo-001/demo.wav",
      "type": "audio",
      "size": 102400
    }
  ],
  "callback_status": "sent",
  "error": null,
  "updated_at": "2025-12-17T12:00:03Z"
}
```

### 获取完整结果：GET /v1/tasks/{task_id}/result
与 `/status` 返回一致。

### 回调载荷
任务结束且回调合法时由网关发送（`callback_manager.send_result`，状态值 `completed` 或 `failed`；可带 `minio_files`）：
```json
{
  "task_id": "task-demo-001",
  "status": "completed",
  "result": { ...完整 WorkflowContext 同上... },
  "minio_files": [
    {
      "name": "demo.wav",
      "url": "http://localhost:9000/yivideo/task-demo-001/demo.wav",
      "type": "audio",
      "size": 102400
    }
  ],
  "timestamp": "2025-12-17T12:00:03Z"
}
```

## 节点清单与示例（/v1/tasks）
下列示例均为“完整 WorkflowContext”形态：顶层字段 + 对应节点阶段输出。仅替换 `task_name` 与 `input_data` 即可调用。

### FFmpeg 系列

#### ffmpeg.extract_keyframes
请求体：
```json
{
  "task_name": "ffmpeg.extract_keyframes",
  "task_id": "task-demo-001",
  "callback": "http://localhost:5678/webhook/demo-t1",
  "input_data": {
    "video_path": "http://localhost:9000/yivideo/task-demo-001/demo.mp4"
  }
}
```
WorkflowContext 示例：
```json
{
  "workflow_id": "task-demo-001",
  "create_at": "2025-12-17T12:00:00Z",
  "input_params": {
    "task_name": "ffmpeg.extract_keyframes",
    "input_data": {
      "video_path": "http://localhost:9000/yivideo/task-demo-001/demo.mp4"
    },
    "callback_url": "http://localhost:5678/webhook/demo-t1"
  },
  "shared_storage_path": "/share/workflows/task-demo-001",
  "stages": {
    "ffmpeg.extract_keyframes": {
      "status": "SUCCESS",
      "input_params": {
        "video_path": "/share/workflows/task-demo-001/demo.mp4"
      },
      "output": {
        "keyframe_dir": "/share/workflows/task-demo-001/keyframes",
        "keyframe_minio_url": "http://localhost:9000/yivideo/task-demo-001/keyframes/",
        "keyframe_compressed_archive_url": "http://localhost:9000/yivideo/task-demo-001/keyframes.zip",
        "keyframe_files_count": 100,
        "keyframe_compression_info": {
          "files_count": 100,
          "compression_ratio": 0.42
        }
      },
      "error": null,
      "duration": 3.2
    }
  },
  "error": null
}
```
参数表：
| 参数 | 类型 | 必需 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `video_path` | string | 是 | - | 输入视频路径（HTTP/MinIO/本地 `/share`） |
| `keyframe_sample_count` | integer | 否 | 100 | 抽取帧数 |
| `upload_keyframes_to_minio` | bool | 否 | false | 是否上传关键帧目录 |
| `compress_keyframes_before_upload` | bool | 否 | false | 压缩后上传关键帧目录 |
| `keyframe_compression_format` | string | 否 | zip | 压缩格式 |
| `keyframe_compression_level` | string | 否 | default | 压缩等级 |
| `delete_local_keyframes_after_upload` | bool | 否 | false | 上传后删除本地关键帧 |

#### ffmpeg.extract_audio
请求体：同通用示例，仅 `task_name` 变更。
WorkflowContext 示例：见通用 `/status` 示例（输出 `audio_path`）。
参数表：
| 参数 | 类型 | 必需 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `video_path` | string | 是 | - | 输入视频路径 |

#### ffmpeg.crop_subtitle_images
请求体：
```json
{
  "task_name": "ffmpeg.crop_subtitle_images",
  "task_id": "task-demo-001",
  "callback": "http://localhost:5678/webhook/demo-t1",
  "input_data": {
    "video_path": "http://localhost:9000/yivideo/task-demo-001/demo.mp4",
    "subtitle_area": [0, 918, 1920, 1080],
    "upload_cropped_images_to_minio": true,
    "compress_directory_before_upload": true
  }
}
```
WorkflowContext 示例：
```json
{
  "workflow_id": "task-demo-001",
  "create_at": "2025-12-17T12:00:00Z",
  "input_params": {
    "task_name": "ffmpeg.crop_subtitle_images",
    "input_data": {
      "video_path": "http://localhost:9000/yivideo/task-demo-001/demo.mp4",
      "subtitle_area": [0, 918, 1920, 1080],
      "upload_cropped_images_to_minio": true,
      "compress_directory_before_upload": true
    },
    "callback_url": "http://localhost:5678/webhook/demo-t1"
  },
  "shared_storage_path": "/share/workflows/task-demo-001",
  "stages": {
    "ffmpeg.crop_subtitle_images": {
      "status": "SUCCESS",
      "input_params": {
        "video_path": "/share/workflows/task-demo-001/demo.mp4",
        "subtitle_area": [0, 918, 1920, 1080]
      },
      "output": {
        "cropped_images_path": "/share/workflows/task-demo-001/cropped_images",
        "cropped_images_minio_url": "http://localhost:9000/yivideo/task-demo-001/cropped_images",
        "cropped_images_files_count": 150,
        "cropped_images_uploaded_files": ["frame_0001.jpg", "frame_0002.jpg"],
        "compressed_archive_url": "http://localhost:9000/yivideo/task-demo-001/cropped_images.zip",
        "compression_info": {
          "files_count": 150,
          "compression_ratio": 0.55
        }
      },
      "error": null,
      "duration": 8.5
    }
  },
  "error": null
}
```
参数表：
| 参数 | 类型 | 必需 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `video_path` | string | 是 | - | 输入视频路径 |
| `subtitle_area` | array | 否 | 自动检测 | `[x1,y1,x2,y2]`，未提供时尝试 `paddleocr.detect_subtitle_area` 输出 |
| `upload_cropped_images_to_minio` | bool | 否 | false | 上传裁剪图到 MinIO |
| `compress_directory_before_upload` | bool | 否 | false | 上传前压缩目录 |
| `compression_format` | string | 否 | zip | 压缩格式 |
| `compression_level` | string | 否 | default | 压缩等级 |
| `delete_local_cropped_images_after_upload` | bool | 否 | false | 上传后删除本地文件 |
| `decode_processes` | integer | 否 | 10 | 解码并发进程数 |

#### ffmpeg.split_audio_segments
请求体：
```json
{
  "task_name": "ffmpeg.split_audio_segments",
  "task_id": "task-demo-001",
  "callback": "http://localhost:5678/webhook/demo-t1",
  "input_data": {
    "audio_path": "http://localhost:9000/yivideo/task-demo-001/demo.wav",
    "subtitle_path": "http://localhost:9000/yivideo/task-demo-001/subtitle.srt",
    "group_by_speaker": true,
    "output_format": "wav"
  }
}
```
WorkflowContext 示例：
```json
{
  "workflow_id": "task-demo-001",
  "create_at": "2025-12-17T12:00:00Z",
  "input_params": {
    "task_name": "ffmpeg.split_audio_segments",
    "input_data": {
      "audio_path": "http://localhost:9000/yivideo/task-demo-001/demo.wav",
      "subtitle_path": "http://localhost:9000/yivideo/task-demo-001/subtitle.srt",
      "group_by_speaker": true,
      "output_format": "wav"
    },
    "callback_url": "http://localhost:5678/webhook/demo-t1"
  },
  "shared_storage_path": "/share/workflows/task-demo-001",
  "stages": {
    "ffmpeg.split_audio_segments": {
      "status": "SUCCESS",
      "input_params": {
        "audio_path": "/share/workflows/task-demo-001/demo.wav",
        "subtitle_path": "/share/workflows/task-demo-001/subtitle.srt",
        "group_by_speaker": true,
        "output_format": "wav"
      },
      "output": {
        "audio_segments_dir": "/share/workflows/task-demo-001/audio_segments",
        "audio_source": "/share/workflows/task-demo-001/demo.wav",
        "subtitle_source": "/share/workflows/task-demo-001/subtitle.srt",
        "total_segments": 148,
        "successful_segments": 148,
        "failed_segments": 0,
        "total_duration": 1200.5,
        "processing_time": 45.2,
        "audio_format": "wav",
        "sample_rate": 16000,
        "channels": 1,
        "split_info_file": "/share/workflows/task-demo-001/audio_segments/split_info.json",
        "segments_count": 148,
        "speaker_summary": {
          "SPEAKER_00": {
            "count": 80,
            "duration": 650.3
          },
          "SPEAKER_01": {
            "count": 68,
            "duration": 550.2
          }
        }
      },
      "error": null,
      "duration": 12.3
    }
  },
  "error": null
}
```
参数表（常用）：
| 参数 | 类型 | 必需 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `audio_path` | string | 否 | 智能源选择 | 未提供则尝试 `audio_separator.separate_vocals` 或 `ffmpeg.extract_audio` |
| `subtitle_path` | string | 否 | 智能源选择 | 未提供则尝试 `wservice.generate_subtitle_files` 输出 |
| `group_by_speaker` | bool | 否 | false | 按说话人分组 |
| `output_format` | string | 否 | "wav" | 输出格式 |
| `sample_rate` | integer | 否 | 16000 | 采样率 |
| `channels` | integer | 否 | 1 | 声道数 |
| `min_segment_duration` | number | 否 | 1.0 | 最短片段秒数 |
| `max_segment_duration` | number | 否 | 30.0 | 最长片段秒数 |
| `include_silence` | bool | 否 | false | 是否保留静音片段 |
| `enable_concurrent` | bool | 否 | true | 是否并发切分 |
| `max_workers` | integer | 否 | 8 | 并发线程数 |
| `concurrent_timeout` | integer | 否 | 600 | 并发超时秒数 |

### Faster-Whisper

#### faster_whisper.transcribe_audio
请求体：
```json
{
  "task_name": "faster_whisper.transcribe_audio",
  "task_id": "task-demo-001",
  "callback": "http://localhost:5678/webhook/demo-t1",
  "input_data": {
    "audio_path": "http://localhost:9000/yivideo/task-demo-001/demo.wav"
  }
}
```
WorkflowContext 示例：
```json
{
  "workflow_id": "task-demo-001",
  "create_at": "2025-12-17T12:00:00Z",
  "input_params": {
    "task_name": "faster_whisper.transcribe_audio",
    "input_data": {
      "audio_path": "http://localhost:9000/yivideo/task-demo-001/demo.wav"
    },
    "callback_url": "http://localhost:5678/webhook/demo-t1"
  },
  "shared_storage_path": "/share/workflows/task-demo-001",
  "stages": {
    "faster_whisper.transcribe_audio": {
      "status": "SUCCESS",
      "input_params": {
        "audio_source": "input_data",
        "audio_path": "http://localhost:9000/yivideo/task-demo-001/demo.wav",
        "enable_word_timestamps": true
      },
      "output": {
        "segments_file": "http://localhost:9000/yivideo/task-demo-001/transcribe_data_abcd1234.json",
        "audio_duration": 125.5,
        "language": "zh",
        "transcribe_duration": 45.2,
        "model_name": "base",
        "device": "cuda",
        "enable_word_timestamps": true,
        "statistics": {
          "total_segments": 120,
          "total_words": 850,
          "transcribe_duration": 45.2,
          "average_segment_duration": 1.2
        },
        "segments_count": 120
      },
      "error": null,
      "duration": 45.2
    }
  },
  "error": null
}
```
参数表：
| 参数 | 类型 | 必需 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `audio_path` | string | 否 | 智能源选择 | 未提供时尝试人声/默认音频；支持 HTTP/MinIO |
| `enable_word_timestamps` | bool | 否 | config 默认 | 是否启用词级时间戳 |

### Audio Separator

#### audio_separator.separate_vocals
请求体：
```json
{
  "task_name": "audio_separator.separate_vocals",
  "task_id": "task-demo-001",
  "callback": "http://localhost:5678/webhook/demo-t1",
  "input_data": {
    "audio_path": "http://localhost:9000/yivideo/task-demo-001/demo.wav",
    "audio_separator_config": {
      "model_name": "UVR-MDX-NET-Inst_HQ_5.onnx"
    }
  }
}
```
WorkflowContext 示例：
```json
{
  "workflow_id": "task-demo-001",
  "create_at": "2025-12-17T12:00:00Z",
  "input_params": {
    "task_name": "audio_separator.separate_vocals",
    "input_data": {
      "audio_path": "http://localhost:9000/yivideo/task-demo-001/demo.wav",
      "audio_separator_config": {
        "model_name": "UVR-MDX-NET-Inst_HQ_5.onnx"
      }
    },
    "callback_url": "http://localhost:5678/webhook/demo-t1"
  },
  "shared_storage_path": "/share/workflows/task-demo-001",
  "stages": {
    "audio_separator.separate_vocals": {
      "status": "SUCCESS",
      "input_params": {
        "audio_source": "input_data",
        "audio_path": "http://localhost:9000/yivideo/task-demo-001/demo.wav",
        "model_name": "UVR-MDX-NET-Inst_HQ_5.onnx",
        "quality_mode": "default"
      },
      "output": {
        "all_audio_files": [
          "/share/workflows/task-demo-001/audio/audio_separated/demo_(Vocals)_UVR-MDX-NET-Inst_HQ_5.flac",
          "/share/workflows/task-demo-001/audio/audio_separated/demo_(Instrumental)_UVR-MDX-NET-Inst_HQ_5.flac"
        ],
        "vocal_audio": "/share/workflows/task-demo-001/audio/audio_separated/demo_(Vocals)_UVR-MDX-NET-Inst_HQ_5.flac",
        "vocal_audio_minio_url": "http://localhost:9000/yivideo/task-demo-001/audio/audio_separated/demo_(Vocals)_UVR-MDX-NET-Inst_HQ_5.flac",
        "all_audio_minio_urls": [
          "http://localhost:9000/yivideo/task-demo-001/audio/audio_separated/demo_(Vocals)_UVR-MDX-NET-Inst_HQ_5.flac",
          "http://localhost:9000/yivideo/task-demo-001/audio/audio_separated/demo_(Instrumental)_UVR-MDX-NET-Inst_HQ_5.flac"
        ],
        "model_used": "UVR-MDX-NET-Inst_HQ_5.onnx",
        "quality_mode": "default"
      },
      "error": null,
      "duration": 30.5
    }
  },
  "error": null
}
```
参数表：
| 参数 | 类型 | 必需 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `audio_path` | string | 否 | 智能源选择 | 未提供则尝试上游音频/人声 |
| `audio_separator_config.model_name` | string | 否 | UVR-MDX-NET-Inst_HQ_5.onnx | 分离模型 |
| `audio_separator_config.quality_mode` | string | 否 | default | 模型质量/性能模式（high_quality/fast/default） |
| `audio_separator_config.use_vocal_optimization` | bool | 否 | false | 是否开启人声优化 |
| `audio_separator_config.vocal_optimization_level` | string | 否 | - | 人声优化等级 |

### Pyannote Audio

#### pyannote_audio.diarize_speakers
请求体：
```json
{
  "task_name": "pyannote_audio.diarize_speakers",
  "task_id": "task-demo-001",
  "callback": "http://localhost:5678/webhook/demo-t1",
  "input_data": {
    "audio_path": "http://localhost:9000/yivideo/task-demo-001/demo.wav"
  }
}
```
WorkflowContext 示例：
```json
{
  "workflow_id": "task-demo-001",
  "create_at": "2025-12-17T12:00:00Z",
  "input_params": {
    "task_name": "pyannote_audio.diarize_speakers",
    "input_data": {
      "audio_path": "http://localhost:9000/yivideo/task-demo-001/demo.wav"
    },
    "callback_url": "http://localhost:5678/webhook/demo-t1"
  },
  "shared_storage_path": "/share/workflows/task-demo-001",
  "stages": {
    "pyannote_audio.diarize_speakers": {
      "status": "SUCCESS",
      "input_params": {
        "audio_path": "/share/workflows/task-demo-001/demo.wav"
      },
      "output": {
        "diarization_file": "http://localhost:9000/yivideo/task-demo-001/diarization/diarization_result.json",
        "diarization_file_minio_url": "http://localhost:9000/yivideo/task-demo-001/diarization/diarization_result.json",
        "detected_speakers": ["SPEAKER_00", "SPEAKER_01"],
        "speaker_statistics": {
          "SPEAKER_00": {"segments": 80, "duration": 650.3},
          "SPEAKER_01": {"segments": 68, "duration": 550.2}
        },
        "total_speakers": 2,
        "total_segments": 148,
        "summary": "检测到 2 个说话人，共 148 个说话片段 (使用免费接口: base)",
        "execution_method": "subprocess",
        "execution_time": 60.0,
        "audio_source": "input_data",
        "api_type": "free",
        "model_name": "base",
        "use_paid_api": false
      },
      "error": null,
      "duration": 60.0
    }
  },
  "error": null
}
```
参数表：
| 参数 | 类型 | 必需 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `audio_path` | string | 否 | 智能源选择 | 未提供则尝试人声/默认音频 |
| `use_paid_api` | bool | 否 | false | 是否使用付费接口（需配置密钥） |

#### pyannote_audio.get_speaker_segments
请求体：
```json
{
  "task_name": "pyannote_audio.get_speaker_segments",
  "task_id": "task-demo-001",
  "callback": "http://localhost:5678/webhook/demo-t1",
  "input_data": {
    "diarization_file": "http://localhost:9000/yivideo/task-demo-001/diarization/diarization_result.json",
    "speaker": "SPEAKER_00"
  }
}
```
TaskStatusResponse 示例（结果字段承载任务返回）：
```json
{
  "workflow_id": "task-demo-001",
  "status": "completed",
  "create_at": "2025-12-17T12:00:00Z",
  "input_params": {
    "task_name": "pyannote_audio.get_speaker_segments",
    "input_data": {
      "diarization_file": "http://localhost:9000/yivideo/task-demo-001/diarization/diarization_result.json",
      "speaker": "SPEAKER_00"
    },
    "callback_url": "http://localhost:5678/webhook/demo-t1"
  },
  "shared_storage_path": "/share/workflows/task-demo-001",
  "result": {
    "success": true,
    "data": {
      "segments": [
        {"start": 0.0, "end": 5.2, "speaker": "SPEAKER_00", "duration": 5.2}
      ],
      "summary": "说话人 SPEAKER_00 的片段: 1 个"
    }
  },
  "error": null,
  "updated_at": "2025-12-17T12:00:05Z"
}
```
参数表：
| 参数 | 类型 | 必需 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `diarization_file` | string | 否 | 智能源选择 | 未提供则回退 `pyannote_audio.diarize_speakers` 输出 |
| `speaker` | string | 否 | - | 目标说话人标签，不填则返回全部片段统计 |

#### pyannote_audio.validate_diarization
请求体：
```json
{
  "task_name": "pyannote_audio.validate_diarization",
  "task_id": "task-demo-001",
  "callback": "http://localhost:5678/webhook/demo-t1",
  "input_data": {
    "diarization_file": "http://localhost:9000/yivideo/task-demo-001/diarization/diarization_result.json"
  }
}
```
TaskStatusResponse 示例（结果字段承载任务返回）：
```json
{
  "workflow_id": "task-demo-001",
  "status": "completed",
  "create_at": "2025-12-17T12:00:00Z",
  "input_params": {
    "task_name": "pyannote_audio.validate_diarization",
    "input_data": {
      "diarization_file": "http://localhost:9000/yivideo/task-demo-001/diarization/diarization_result.json"
    },
    "callback_url": "http://localhost:5678/webhook/demo-t1"
  },
  "shared_storage_path": "/share/workflows/task-demo-001",
  "result": {
    "success": true,
    "data": {
      "validation": {
        "valid": true,
        "total_segments": 148,
        "total_speakers": 2,
        "total_duration": 280.5,
        "avg_segment_duration": 1.9,
        "issues": []
      },
      "summary": "说话人分离结果有效"
    }
  },
  "error": null,
  "updated_at": "2025-12-17T12:00:06Z"
}
```
参数表：
| 参数 | 类型 | 必需 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `diarization_file` | string | 否 | 智能源选择 | 未提供则回退 `pyannote_audio.diarize_speakers` 输出 |

### PaddleOCR

#### paddleocr.detect_subtitle_area
请求体：
```json
{
  "task_name": "paddleocr.detect_subtitle_area",
  "task_id": "task-demo-001",
  "callback": "http://localhost:5678/webhook/demo-t1",
  "input_data": {
    "video_path": "http://localhost:9000/yivideo/task-demo-001/demo.mp4"
  }
}
```
WorkflowContext 示例：
```json
{
  "workflow_id": "task-demo-001",
  "create_at": "2025-12-17T12:00:00Z",
  "input_params": {
    "task_name": "paddleocr.detect_subtitle_area",
    "input_data": {
      "video_path": "http://localhost:9000/yivideo/task-demo-001/demo.mp4"
    },
    "callback_url": "http://localhost:5678/webhook/demo-t1"
  },
  "shared_storage_path": "/share/workflows/task-demo-001",
  "stages": {
    "paddleocr.detect_subtitle_area": {
      "status": "SUCCESS",
      "input_params": {
        "video_path": "/share/workflows/task-demo-001/demo.mp4"
      },
      "output": {
        "subtitle_area": [0, 918, 1920, 1080],
        "confidence": 0.93,
        "keyframe_dir": "http://localhost:9000/yivideo/task-demo-001/keyframes/"
      },
      "error": null,
      "duration": 6.5
    }
  },
  "error": null
}
```
参数表：
| 参数 | 类型 | 必需 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `video_path` | string | 是 | - | 输入视频路径 |

#### paddleocr.create_stitched_images
请求体：
```json
{
  "task_name": "paddleocr.create_stitched_images",
  "task_id": "task-demo-001",
  "callback": "http://localhost:5678/webhook/demo-t1",
  "input_data": {
    "cropped_images_path": "http://localhost:9000/yivideo/task-demo-001/cropped_images",
    "subtitle_area": [0, 918, 1920, 1080],
    "upload_stitched_images_to_minio": true,
    "auto_decompress": true
  }
}
```
WorkflowContext 示例：
```json
{
  "workflow_id": "task-demo-001",
  "create_at": "2025-12-17T12:00:00Z",
  "input_params": {
    "task_name": "paddleocr.create_stitched_images",
    "input_data": {
      "cropped_images_path": "http://localhost:9000/yivideo/task-demo-001/cropped_images",
      "subtitle_area": [0, 918, 1920, 1080],
      "upload_stitched_images_to_minio": true,
      "auto_decompress": true
    },
    "callback_url": "http://localhost:5678/webhook/demo-t1"
  },
  "shared_storage_path": "/share/workflows/task-demo-001",
  "stages": {
    "paddleocr.create_stitched_images": {
      "status": "SUCCESS",
      "input_params": {
        "cropped_images_path": "/share/workflows/task-demo-001/cropped_images",
        "subtitle_area": [0, 918, 1920, 1080]
      },
      "output": {
        "multi_frames_path": "/share/workflows/task-demo-001/multi_frames",
        "manifest_path": "/share/workflows/task-demo-001/multi_frames.json",
        "multi_frames_minio_url": "http://localhost:9000/yivideo/task-demo-001/stitched_images.zip",
        "manifest_minio_url": "http://localhost:9000/yivideo/task-demo-001/manifest/multi_frames.json",
        "stitched_images_count": 150,
        "compression_info": {
          "files_count": 150,
          "compression_ratio": 0.35
        }
      },
      "error": null,
      "duration": 12.8
    }
  },
  "error": null
}
```
参数表：
| 参数 | 类型 | 必需 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `cropped_images_path` | string | 是 | - | 裁剪图片目录或压缩包URL/MinIO路径 |
| `subtitle_area` | array | 否 | 自动继承 | `[x1,y1,x2,y2]`，未提供时回退 `paddleocr.detect_subtitle_area` |
| `upload_stitched_images_to_minio` | bool | 否 | true | 是否上传拼接结果到 MinIO（压缩上传） |
| `delete_local_stitched_images_after_upload` | bool | 否 | false | 上传后删除本地拼接结果 |
| `auto_decompress` | bool | 否 | true | 下载压缩包时自动解压 |
| `pipeline.concat_batch_size` | integer | 否 | 50 | 拼接批大小（来自配置） |
| `pipeline.stitching_workers` | integer | 否 | 10 | 拼接并发数（来自配置） |

#### paddleocr.perform_ocr
请求体：
```json
{
  "task_name": "paddleocr.perform_ocr",
  "task_id": "task-demo-001",
  "callback": "http://localhost:5678/webhook/demo-t1",
  "input_data": {
    "manifest_path": "http://localhost:9000/yivideo/task-demo-001/manifest/multi_frames.json",
    "multi_frames_path": "http://localhost:9000/yivideo/task-demo-001/multi_frames",
    "upload_ocr_results_to_minio": true
  }
}
```
WorkflowContext 示例：
```json
{
  "workflow_id": "task-demo-001",
  "create_at": "2025-12-17T12:00:00Z",
  "input_params": {
    "task_name": "paddleocr.perform_ocr",
    "input_data": {
      "manifest_path": "http://localhost:9000/yivideo/task-demo-001/manifest/multi_frames.json",
      "multi_frames_path": "http://localhost:9000/yivideo/task-demo-001/multi_frames",
      "upload_ocr_results_to_minio": true
    },
    "callback_url": "http://localhost:5678/webhook/demo-t1"
  },
  "shared_storage_path": "/share/workflows/task-demo-001",
  "stages": {
    "paddleocr.perform_ocr": {
      "status": "SUCCESS",
      "input_params": {
        "manifest_path": "http://localhost:9000/yivideo/task-demo-001/manifest/multi_frames.json",
        "multi_frames_path": "http://localhost:9000/yivideo/task-demo-001/multi_frames"
      },
      "output": {
        "ocr_results_path": "http://localhost:9000/yivideo/task-demo-001/ocr_results/ocr_results.json",
        "ocr_results_minio_url": "http://localhost:9000/yivideo/task-demo-001/ocr_results/ocr_results.json"
      },
      "error": null,
      "duration": 20.0
    }
  },
  "error": null
}
```
参数表：
| 参数 | 类型 | 必需 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `manifest_path` | string | 否 | 智能源选择 | 拼接图 manifest，本地或 MinIO/HTTP URL，未提供则回退 `paddleocr.create_stitched_images` 输出 |
| `multi_frames_path` | string | 否 | 智能源选择 | 拼接图目录，本地或 MinIO/HTTP URL，未提供则回退 `paddleocr.create_stitched_images` 输出 |
| `upload_ocr_results_to_minio` | bool | 否 | true | 是否上传 OCR 结果到 MinIO |
| `delete_local_ocr_results_after_upload` | bool | 否 | false | 上传后删除本地结果 |

#### paddleocr.postprocess_and_finalize
请求体：
```json
{
  "task_name": "paddleocr.postprocess_and_finalize",
  "task_id": "task-demo-001",
  "callback": "http://localhost:5678/webhook/demo-t1",
  "input_data": {
    "ocr_results_file": "http://localhost:9000/yivideo/task-demo-001/ocr_results/ocr_results.json",
    "manifest_file": "http://localhost:9000/yivideo/task-demo-001/manifest/multi_frames.json",
    "upload_final_results_to_minio": true
  }
}
```
WorkflowContext 示例：
```json
{
  "workflow_id": "task-demo-001",
  "create_at": "2025-12-17T12:00:00Z",
  "input_params": {
    "task_name": "paddleocr.postprocess_and_finalize",
    "input_data": {
      "ocr_results_file": "http://localhost:9000/yivideo/task-demo-001/ocr_results/ocr_results.json",
      "manifest_file": "http://localhost:9000/yivideo/task-demo-001/manifest/multi_frames.json",
      "upload_final_results_to_minio": true
    },
    "callback_url": "http://localhost:5678/webhook/demo-t1"
  },
  "shared_storage_path": "/share/workflows/task-demo-001",
  "stages": {
    "paddleocr.postprocess_and_finalize": {
      "status": "SUCCESS",
      "input_params": {
        "ocr_results_file": "http://localhost:9000/yivideo/task-demo-001/ocr_results/ocr_results.json",
        "manifest_file": "http://localhost:9000/yivideo/task-demo-001/manifest/multi_frames.json"
      },
      "output": {
        "srt_file": "/share/workflows/task-demo-001/demo.srt",
        "json_file": "/share/workflows/task-demo-001/demo.json"
      },
      "error": null,
      "duration": 10.0
    }
  },
  "error": null
}
```
参数表：
| 参数 | 类型 | 必需 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `ocr_results_file` | string | 否 | 智能源选择 | OCR 结果文件，本地或 MinIO/HTTP URL，未提供则回退 `paddleocr.perform_ocr` 输出 |
| `manifest_file` | string | 否 | 智能源选择 | 拼接图 manifest，本地或 MinIO/HTTP URL，未提供则回退 `paddleocr.create_stitched_images` 输出 |
| `upload_final_results_to_minio` | bool | 否 | true | 是否上传最终字幕到 MinIO |
| `delete_local_results_after_upload` | bool | 否 | false | 上传后删除本地结果 |

### IndexTTS

#### indextts.generate_speech
请求体：
```json
{
  "task_name": "indextts.generate_speech",
  "task_id": "task-demo-001",
  "callback": "http://localhost:5678/webhook/demo-t1",
  "input_data": {
    "text": "你好，欢迎使用 YiVideo。",
    "output_path": "/share/workflows/task-demo-001/tts.wav",
    "spk_audio_prompt": "http://localhost:9000/yivideo/task-demo-001/ref.wav",
    "voice": "zh_female_1"
  }
}
```
WorkflowContext 示例：
```json
{
  "workflow_id": "task-demo-001",
  "create_at": "2025-12-17T12:00:00Z",
  "input_params": {
    "task_name": "indextts.generate_speech",
    "input_data": {
      "text": "你好，欢迎使用 YiVideo。",
      "output_path": "/share/workflows/task-demo-001/tts.wav",
      "spk_audio_prompt": "http://localhost:9000/yivideo/task-demo-001/ref.wav",
      "voice": "zh_female_1"
    },
    "callback_url": "http://localhost:5678/webhook/demo-t1"
  },
  "shared_storage_path": "/share/workflows/task-demo-001",
  "stages": {
    "indextts.generate_speech": {
      "status": "SUCCESS",
      "input_params": {
        "reference_audio": "http://localhost:9000/yivideo/task-demo-001/ref.wav",
        "text_length": 12
      },
      "output": {
        "status": "success",
        "output_path": "/share/workflows/task-demo-001/tts.wav",
        "processing_time": 3.2,
        "task_id": "task-demo-001"
      },
      "error": null,
      "duration": 3.2
    }
  },
  "error": null
}
```
参数表：
| 参数 | 类型 | 必需 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `text` | string | 是 | - | 合成文本 |
| `output_path` | string | 是 | - | 目标输出路径（/share/ 下） |
| `spk_audio_prompt` | string | 是 | - | 说话人参考音频（HTTP/MinIO/本地） |
| `voice` | string | 否 | 默认音色 | 语音角色 |
| `emotion_reference` | string | 否 | - | 情感参考音频 |
| `emotion_alpha` | number | 否 | 0.65 | 情感强度 |
| `use_random` | bool | 否 | false | 是否随机采样 |

### WService 字幕优化

#### wservice.generate_subtitle_files
请求体：
```json
{
  "task_name": "wservice.generate_subtitle_files",
  "task_id": "task-demo-001",
  "callback": "http://localhost:5678/webhook/demo-t1",
  "input_data": {
    "segments_file": "http://localhost:9000/yivideo/task-demo-001/transcribe_data.json"
  }
}
```
WorkflowContext 示例：
```json
{
  "workflow_id": "task-demo-001",
  "create_at": "2025-12-17T12:00:00Z",
  "input_params": {
    "task_name": "wservice.generate_subtitle_files",
    "input_data": {
      "segments_file": "http://localhost:9000/yivideo/task-demo-001/transcribe_data.json"
    },
    "callback_url": "http://localhost:5678/webhook/demo-t1"
  },
  "shared_storage_path": "/share/workflows/task-demo-001",
  "stages": {
    "wservice.generate_subtitle_files": {
      "status": "SUCCESS",
      "input_params": {
        "segments_file": "http://localhost:9000/yivideo/task-demo-001/transcribe_data.json",
        "data_source": "input_data.segments_file"
      },
      "output": {
        "subtitle_path": "http://localhost:9000/yivideo/task-demo-001/subtitles/subtitle.srt",
        "json_path": "http://localhost:9000/yivideo/task-demo-001/subtitles/subtitle_subtitle.json",
        "subtitle_files": {
          "basic": "http://localhost:9000/yivideo/task-demo-001/subtitles/subtitle.srt",
          "with_speakers": "http://localhost:9000/yivideo/task-demo-001/subtitles/subtitle_with_speakers.srt",
          "word_timestamps": "http://localhost:9000/yivideo/task-demo-001/subtitles/subtitle_word_timestamps.json",
          "json": "http://localhost:9000/yivideo/task-demo-001/subtitles/subtitle_subtitle.json"
        }
      },
      "error": null,
      "duration": 5.0
    }
  },
  "error": null
}
```
参数表：
| 参数 | 类型 | 必需 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `segments_file` | string | 否 | 智能源选择 | 未提供则尝试 `faster_whisper.transcribe_audio` 输出 |
| `audio_duration` | number | 否 | 0 | 音频时长（可选） |
| `language` | string | 否 | unknown | 语言代码 |
| `output_filename` | string | 否 | 自动推断 | 输出文件前缀 |

#### wservice.correct_subtitles
请求体：
```json
{
  "task_name": "wservice.correct_subtitles",
  "task_id": "task-demo-001",
  "callback": "http://localhost:5678/webhook/demo-t1",
  "input_data": {
    "subtitle_path": "http://localhost:9000/yivideo/task-demo-001/subtitle.srt"
  }
}
```
WorkflowContext 示例：
```json
{
  "workflow_id": "task-demo-001",
  "create_at": "2025-12-17T12:00:00Z",
  "input_params": {
    "task_name": "wservice.correct_subtitles",
    "input_data": {
      "subtitle_path": "http://localhost:9000/yivideo/task-demo-001/subtitle.srt"
    },
    "callback_url": "http://localhost:5678/webhook/demo-t1"
  },
  "shared_storage_path": "/share/workflows/task-demo-001",
  "stages": {
    "wservice.correct_subtitles": {
      "status": "SUCCESS",
      "input_params": {
        "subtitle_path": "/share/workflows/task-demo-001/subtitle.srt"
      },
      "output": {
        "corrected_subtitle_path": "http://localhost:9000/yivideo/task-demo-001/subtitle_corrected.srt"
      },
      "error": null,
      "duration": 4.0
    }
  },
  "error": null
}
```
参数表：
| 参数 | 类型 | 必需 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `subtitle_path` | string | 是 | - | 输入字幕文件 |

#### wservice.ai_optimize_subtitles
请求体：
```json
{
  "task_name": "wservice.ai_optimize_subtitles",
  "task_id": "task-demo-001",
  "callback": "http://localhost:5678/webhook/demo-t1",
  "input_data": {
    "subtitle_path": "http://localhost:9000/yivideo/task-demo-001/subtitle_corrected.srt"
  }
}
```
WorkflowContext 示例：
```json
{
  "workflow_id": "task-demo-001",
  "create_at": "2025-12-17T12:00:00Z",
  "input_params": {
    "task_name": "wservice.ai_optimize_subtitles",
    "input_data": {
      "subtitle_path": "http://localhost:9000/yivideo/task-demo-001/subtitle_corrected.srt"
    },
    "callback_url": "http://localhost:5678/webhook/demo-t1"
  },
  "shared_storage_path": "/share/workflows/task-demo-001",
  "stages": {
    "wservice.ai_optimize_subtitles": {
      "status": "SUCCESS",
      "input_params": {
        "subtitle_path": "/share/workflows/task-demo-001/subtitle_corrected.srt"
      },
      "output": {
        "optimized_subtitle_path": "http://localhost:9000/yivideo/task-demo-001/subtitle_optimized.srt"
      },
      "error": null,
      "duration": 4.5
    }
  },
  "error": null
}
```
参数表：
| 参数 | 类型 | 必需 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `subtitle_path` | string | 是 | - | 需要优化的字幕文件 |

#### wservice.merge_speaker_segments
请求体：
```json
{
  "task_name": "wservice.merge_speaker_segments",
  "task_id": "task-demo-001",
  "callback": "http://localhost:5678/webhook/demo-t1",
  "input_data": {
    "segments_file": "http://localhost:9000/yivideo/task-demo-001/transcribe_data.json",
    "diarization_file": "http://localhost:9000/yivideo/task-demo-001/diarization/diarization_result.json"
  }
}
```
WorkflowContext 示例：
```json
{
  "workflow_id": "task-demo-001",
  "create_at": "2025-12-17T12:00:00Z",
  "input_params": {
    "task_name": "wservice.merge_speaker_segments",
    "input_data": {
      "segments_file": "http://localhost:9000/yivideo/task-demo-001/transcribe_data.json",
      "diarization_file": "http://localhost:9000/yivideo/task-demo-001/diarization/diarization_result.json"
    },
    "callback_url": "http://localhost:5678/webhook/demo-t1"
  },
  "shared_storage_path": "/share/workflows/task-demo-001",
  "stages": {
    "wservice.merge_speaker_segments": {
      "status": "SUCCESS",
      "input_params": {
        "segments_file": "http://localhost:9000/yivideo/task-demo-001/transcribe_data.json",
        "diarization_file": "http://localhost:9000/yivideo/task-demo-001/diarization/diarization_result.json"
      },
      "output": {
        "merged_segments": [
          {"start": 0.0, "end": 5.2, "speaker": "SPEAKER_00", "text": "示例文本"}
        ],
        "input_summary": {
          "transcript_segments_count": 148,
          "speaker_segments_count": 148,
          "merged_segments_count": 148,
          "data_source": "faster_whisper.transcribe_audio"
        }
      },
      "error": null,
      "duration": 5.0
    }
  },
  "error": null
}
```
参数表：
| 参数 | 类型 | 必需 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `segments_data` | array | 否 | - | 直接传入转录片段数据 |
| `speaker_segments_data` | array | 否 | - | 直接传入说话人片段数据 |
| `segments_file` | string | 否 | 智能源选择 | 未提供则回退 `faster_whisper.transcribe_audio` 输出 |
| `diarization_file` | string | 否 | 智能源选择 | 未提供则回退 `pyannote_audio.diarize_speakers` 输出 |

#### wservice.merge_with_word_timestamps
请求体：
```json
{
  "task_name": "wservice.merge_with_word_timestamps",
  "task_id": "task-demo-001",
  "callback": "http://localhost:5678/webhook/demo-t1",
  "input_data": {
    "segments_file": "http://localhost:9000/yivideo/task-demo-001/transcribe_data.json",
    "diarization_file": "http://localhost:9000/yivideo/task-demo-001/diarization/diarization_result.json"
  }
}
```
WorkflowContext 示例：
```json
{
  "workflow_id": "task-demo-001",
  "create_at": "2025-12-17T12:00:00Z",
  "input_params": {
    "task_name": "wservice.merge_with_word_timestamps",
    "input_data": {
      "segments_file": "http://localhost:9000/yivideo/task-demo-001/transcribe_data.json",
      "diarization_file": "http://localhost:9000/yivideo/task-demo-001/diarization/diarization_result.json"
    },
    "callback_url": "http://localhost:5678/webhook/demo-t1"
  },
  "shared_storage_path": "/share/workflows/task-demo-001",
  "stages": {
    "wservice.merge_with_word_timestamps": {
      "status": "SUCCESS",
      "input_params": {
        "segments_file": "http://localhost:9000/yivideo/task-demo-001/transcribe_data.json",
        "diarization_file": "http://localhost:9000/yivideo/task-demo-001/diarization/diarization_result.json"
      },
      "output": {
        "merged_segments": [
          {"start": 0.0, "end": 5.2, "speaker": "SPEAKER_00", "text": "示例文本", "words": []}
        ],
        "input_summary": {
          "transcript_segments_count": 148,
          "speaker_segments_count": 148,
          "merged_segments_count": 148,
          "data_source": "faster_whisper.transcribe_audio",
          "word_timestamps_required": true
        }
      },
      "error": null,
      "duration": 5.5
    }
  },
  "error": null
}
```
参数表：
| 参数 | 类型 | 必需 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `segments_data` | array | 否 | - | 直接传入含词级时间戳的转录片段 |
| `speaker_segments_data` | array | 否 | - | 直接传入说话人片段数据 |
| `segments_file` | string | 否 | 智能源选择 | 未提供则回退 `faster_whisper.transcribe_audio` 输出 |
| `diarization_file` | string | 否 | 智能源选择 | 未提供则回退 `pyannote_audio.diarize_speakers` 输出 |

#### wservice.prepare_tts_segments
请求体：
```json
{
  "task_name": "wservice.prepare_tts_segments",
  "task_id": "task-demo-001",
  "callback": "http://localhost:5678/webhook/demo-t1",
  "input_data": {
    "segments_file": "http://localhost:9000/yivideo/task-demo-001/transcribe_data.json"
  }
}
```
WorkflowContext 示例：
```json
{
  "workflow_id": "task-demo-001",
  "create_at": "2025-12-17T12:00:00Z",
  "input_params": {
    "task_name": "wservice.prepare_tts_segments",
    "input_data": {
      "segments_file": "http://localhost:9000/yivideo/task-demo-001/transcribe_data.json"
    },
    "callback_url": "http://localhost:5678/webhook/demo-t1"
  },
  "shared_storage_path": "/share/workflows/task-demo-001",
  "stages": {
    "wservice.prepare_tts_segments": {
      "status": "SUCCESS",
      "input_params": {
        "segments_file": "http://localhost:9000/yivideo/task-demo-001/transcribe_data.json"
      },
      "output": {
        "prepared_segments": [
          {"start": 0.0, "end": 5.2, "text": "示例文本"}
        ],
        "source_stage": "wservice.generate_subtitle_files",
        "total_segments": 100,
        "input_summary": {
          "original_segments_count": 120,
          "prepared_segments_count": 100,
          "data_source": "wservice.generate_subtitle_files"
        }
      },
      "error": null,
      "duration": 4.0
    }
  },
  "error": null
}
```
参数表：
| 参数 | 类型 | 必需 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `segments_data` | array | 否 | - | 直接传入字幕片段数据 |
| `segments_file` | string | 否 | 智能源选择 | 未提供则回退上游字幕输出 |
| `source_stage_names` | array | 否 | 默认搜索列表 | 自定义查找片段的上游阶段列表 |

## 文件操作接口 (`/v1/files`)

### DELETE /v1/files/directories?directory_path=
- 作用：删除本地 `/share` 目录（幂等），禁止路径遍历。
- 请求示例：`DELETE /v1/files/directories?directory_path=/share/workflows/task-demo-001`
- 响应示例：
```json
{
  "success": true,
  "message": "目录删除成功: /share/workflows/task-demo-001",
  "file_path": "/share/workflows/task-demo-001",
  "file_size": null
}
```

### DELETE /v1/files/{file_path}
- 作用：删除 MinIO 指定桶对象，默认桶 `yivideo`。
- 请求示例：`DELETE /v1/files/task-demo-001/demo.wav?bucket=yivideo`
- 响应示例：
```json
{
  "success": true,
  "message": "文件删除成功: task-demo-001/demo.wav",
  "file_path": "task-demo-001/demo.wav",
  "file_size": null
}
```

### POST /v1/files/upload
- 作用：流式上传文件到 MinIO。
- 请求示例（multipart）：`file=@demo.wav; file_path=task-demo-001/demo.wav; bucket=yivideo`
- 响应示例：
```json
{
  "file_path": "task-demo-001/demo.wav",
  "bucket": "yivideo",
  "download_url": "http://localhost:9000/yivideo/task-demo-001/demo.wav",
  "size": 102400,
  "uploaded_at": "2025-12-17T12:00:00Z",
  "content_type": "audio/wav"
}
```

### GET /v1/files/download/{file_path}
- 作用：下载 MinIO 文件，支持 `bucket` 参数（默认 yivideo）。
- 请求示例：`GET /v1/files/download/task-demo-001/demo.wav?bucket=yivideo`

---
*最后更新: 2025-12-17 | 文档版本: 1.1*

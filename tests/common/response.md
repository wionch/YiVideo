### 分离音频文件 - ffmpeg.extract_audio'

```json
[
    {
        "headers": {
            "host": "host.docker.internal:5678",
            "user-agent": "YiVideo-API-Gateway/1.0",
            "accept-encoding": "gzip, deflate",
            "accept": "*/*",
            "connection": "keep-alive",
            "content-type": "application/json",
            "content-length": "783"
        },
        "params": {},
        "query": {},
        "body": {
            "task_id": "task_id",
            "status": "completed",
            "result": {
                "workflow_id": "task_id",
                "create_at": "2025-12-19T17:29:19.782200",
                "input_params": {
                    "task_name": "ffmpeg.extract_audio",
                    "input_data": {
                        "video_path": "http://host.docker.internal:9000/yivideo/task_id/223.mp4"
                    },
                    "callback_url": "http://host.docker.internal:5678/webhook-waiting/2037/t1"
                },
                "shared_storage_path": "/share/workflows/task_id",
                "stages": {
                    "ffmpeg.extract_audio": {
                        "status": "SUCCESS",
                        "input_params": {
                            "video_path": "/share/workflows/task_id/223.mp4"
                        },
                        "output": {
                            "audio_path": "/share/workflows/task_id/audio/223.wav",
                            "audio_path_minio_url": "http://host.docker.internal:9000/yivideo/task_id/223.wav"
                        },
                        "error": null,
                        "duration": 3.3684327602386475
                    }
                },
                "error": null
            },
            "timestamp": "2025-12-19T17:29:23.537357Z"
        },
        "webhookUrl": "http://host.docker.internal:5678/webhook-test/t1",
        "executionMode": "test"
    }
]
```

### audio_separator 分离人声背景声

```json
[
    {
        "headers": {
            "host": "host.docker.internal:5678",
            "user-agent": "YiVideo-API-Gateway/1.0",
            "accept-encoding": "gzip, deflate",
            "accept": "*/*",
            "connection": "keep-alive",
            "content-type": "application/json",
            "content-length": "1466"
        },
        "params": {},
        "query": {},
        "body": {
            "task_id": "task_id",
            "status": "completed",
            "result": {
                "workflow_id": "task_id",
                "create_at": "2025-12-19T17:30:38.252969",
                "input_params": {
                    "task_name": "audio_separator.separate_vocals",
                    "input_data": {
                        "audio_path": "http://host.docker.internal:9000/yivideo/task_id/223.wav",
                        "audio_separator_config": {
                            "model_name": "UVR-MDX-NET-Inst_HQ_5.onnx"
                        }
                    },
                    "callback_url": "http://host.docker.internal:5678/webhook-waiting/2038/t_audio_sep"
                },
                "shared_storage_path": "/share/workflows/task_id",
                "stages": {
                    "audio_separator.separate_vocals": {
                        "status": "SUCCESS",
                        "input_params": {},
                        "output": {
                            "all_audio_files": ["/share/workflows/task_id/audio/audio_separated/223_(Vocals)_UVR-MDX-NET-Inst_HQ_5.flac", "/share/workflows/task_id/audio/audio_separated/223_(Instrumental)_UVR-MDX-NET-Inst_HQ_5.flac"],
                            "vocal_audio": "/share/workflows/task_id/audio/audio_separated/223_(Vocals)_UVR-MDX-NET-Inst_HQ_5.flac",
                            "vocal_audio_minio_url": "http://host.docker.internal:9000/yivideo/task_id/audio/audio_separated/223_(Vocals)_UVR-MDX-NET-Inst_HQ_5.flac",
                            "all_audio_minio_urls": ["http://host.docker.internal:9000/yivideo/task_id/audio/audio_separated/223_(Vocals)_UVR-MDX-NET-Inst_HQ_5.flac", "http://host.docker.internal:9000/yivideo/task_id/audio/audio_separated/223_(Instrumental)_UVR-MDX-NET-Inst_HQ_5.flac"],
                            "model_used": "UVR-MDX-NET-Inst_HQ_5.onnx",
                            "quality_mode": "default"
                        },
                        "error": null,
                        "duration": 53.1
                    }
                },
                "error": null
            },
            "timestamp": "2025-12-19T17:31:32.168243Z"
        },
        "webhookUrl": "http://host.docker.internal:5678/webhook-test/t_audio_sep",
        "executionMode": "test"
    }
]
```

### faster_whisper.transcribe_audio 转录文本

```json
[
    {
        "headers": {
            "host": "host.docker.internal:5678",
            "user-agent": "YiVideo-API-Gateway/1.0",
            "accept-encoding": "gzip, deflate",
            "accept": "*/*",
            "connection": "keep-alive",
            "content-type": "application/json",
            "content-length": "1362"
        },
        "params": {},
        "query": {},
        "body": {
            "task_id": "task_id",
            "status": "completed",
            "result": {
                "workflow_id": "task_id",
                "create_at": "2025-12-19T17:32:52.758749",
                "input_params": {
                    "task_name": "faster_whisper.transcribe_audio",
                    "input_data": {
                        "audio_path": "http://host.docker.internal:9000/yivideo/task_id/audio/audio_separated/223_(Vocals)_UVR-MDX-NET-Inst_HQ_5.flac"
                    },
                    "callback_url": "http://host.docker.internal:5678/webhook-waiting/2039"
                },
                "shared_storage_path": "/share/workflows/task_id",
                "stages": {
                    "faster_whisper.transcribe_audio": {
                        "status": "SUCCESS",
                        "input_params": {
                            "audio_source": "input_data",
                            "audio_path": "http://host.docker.internal:9000/yivideo/task_id/audio/audio_separated/223_(Vocals)_UVR-MDX-NET-Inst_HQ_5.flac"
                        },
                        "output": {
                            "segments_file": "/share/workflows/task_id/transcribe_data_task_id.json",
                            "audio_duration": 341.79775,
                            "language": "en",
                            "transcribe_duration": 35.47476577758789,
                            "model_name": "Systran/faster-whisper-large-v3",
                            "device": "cuda",
                            "enable_word_timestamps": true,
                            "statistics": {
                                "total_segments": 51,
                                "total_words": 567,
                                "transcribe_duration": 35.47476577758789,
                                "average_segment_duration": 5.803137254901962
                            },
                            "segments_count": 51,
                            "segments_file_minio_url": "http://host.docker.internal:9000/yivideo/task_id/transcribe_data_task_id.json"
                        },
                        "error": null,
                        "duration": 48.94585657119751
                    }
                },
                "error": null
            },
            "timestamp": "2025-12-19T17:33:41.941664Z"
        },
        "webhookUrl": "http://host.docker.internal:5678/webhook-test/d9490bdb-c1e3-42e7-b0ba-44883182b482",
        "executionMode": "test"
    }
]
```

### pyannote_audio.diarize_speakers 说话人识别

```json
[
    {
        "headers": {
            "host": "host.docker.internal:5678",
            "user-agent": "YiVideo-API-Gateway/1.0",
            "accept-encoding": "gzip, deflate",
            "accept": "*/*",
            "connection": "keep-alive",
            "content-type": "application/json",
            "content-length": "1474"
        },
        "params": {},
        "query": {},
        "body": {
            "task_id": "task_id",
            "status": "completed",
            "result": {
                "workflow_id": "task_id",
                "create_at": "2025-12-19T17:35:26.470132",
                "input_params": {
                    "task_name": "pyannote_audio.diarize_speakers",
                    "input_data": {
                        "audio_path": "http://host.docker.internal:9000/yivideo/task_id/audio/audio_separated/223_(Vocals)_UVR-MDX-NET-Inst_HQ_5.flac"
                    },
                    "callback_url": "http://host.docker.internal:5678/webhook-waiting/2040/t4"
                },
                "shared_storage_path": "/share/workflows/task_id",
                "stages": {
                    "pyannote_audio.diarize_speakers": {
                        "status": "SUCCESS",
                        "input_params": {
                            "audio_source": "unknown"
                        },
                        "output": {
                            "diarization_file": "/share/workflows/task_id/diarization/diarization_result.json",
                            "detected_speakers": ["SPEAKER_00"],
                            "speaker_statistics": {
                                "SPEAKER_00": {
                                    "segments": 62,
                                    "duration": 289.28812500000004,
                                    "words": 0
                                }
                            },
                            "total_speakers": 1,
                            "total_segments": 62,
                            "summary": "检测到 1 个说话人，共 62 个说话片段 (使用免费接口: pyannote/speaker-diarization-community-1)",
                            "execution_method": "subprocess",
                            "execution_time": 75.98068070411682,
                            "audio_source": "parameter/input_data",
                            "api_type": "free",
                            "model_name": "pyannote/speaker-diarization-community-1",
                            "use_paid_api": false,
                            "diarization_file_minio_url": "http://host.docker.internal:9000/yivideo/task_id/diarization/diarization_result.json"
                        },
                        "error": null,
                        "duration": 76.012855052948
                    }
                },
                "error": null
            },
            "timestamp": "2025-12-19T17:36:43.909713Z"
        },
        "webhookUrl": "http://host.docker.internal:5678/webhook-test/t4",
        "executionMode": "test"
    }
]
```

### 抽取视频帧 - ffmpeg.extract_keyframes

```json
[
    {
        "headers": {
            "host": "host.docker.internal:5678",
            "user-agent": "YiVideo-API-Gateway/1.0",
            "accept-encoding": "gzip, deflate",
            "accept": "*/*",
            "connection": "keep-alive",
            "content-type": "application/json",
            "content-length": "1338"
        },
        "params": {},
        "query": {},
        "body": {
            "task_id": "task_id",
            "status": "completed",
            "result": {
                "workflow_id": "task_id",
                "create_at": "2025-12-19T17:39:05.699397",
                "input_params": {
                    "task_name": "ffmpeg.extract_keyframes",
                    "input_data": {
                        "video_path": "http://host.docker.internal:9000/yivideo/task_id/223.mp4",
                        "upload_keyframes_to_minio": true,
                        "compress_keyframes_before_upload": true,
                        "keyframe_compression_format": "zip"
                    },
                    "callback_url": "http://host.docker.internal:5678/webhook-waiting/2041"
                },
                "shared_storage_path": "/share/workflows/task_id",
                "stages": {
                    "ffmpeg.extract_keyframes": {
                        "status": "SUCCESS",
                        "input_params": {
                            "video_path": "/share/workflows/task_id/223.mp4"
                        },
                        "output": {
                            "keyframe_dir": "/share/workflows/task_id/keyframes",
                            "keyframe_minio_url": "http://host.docker.internal:9000/yivideo/task_id/keyframes",
                            "keyframe_compressed_archive_url": "http://host.docker.internal:9000/yivideo/task_id/keyframes/keyframes_compressed.zip",
                            "keyframe_files_count": 100,
                            "keyframe_compression_info": {
                                "original_size": 10998926,
                                "compressed_size": 10703338,
                                "compression_ratio": 0.026874260268684447,
                                "files_count": 100,
                                "compression_time": 0.4116044044494629,
                                "checksum": "440cdc68d7a06d44c4699164a83bfb8ac647b158e8691db36c76b2db43855f56",
                                "format": "zip"
                            }
                        },
                        "error": null,
                        "duration": 5.393212556838989
                    }
                },
                "error": null
            },
            "timestamp": "2025-12-19T17:39:11.157666Z"
        },
        "webhookUrl": "http://host.docker.internal:5678/webhook-test/6747f37b-48e9-4b14-aa74-858a3a3137b0",
        "executionMode": "test"
    }
]
```

### 分割字幕条 - ffmpeg.crop_subtitle_images

```json
[
    {
        "headers": {
            "host": "host.docker.internal:5678",
            "user-agent": "YiVideo-API-Gateway/1.0",
            "accept-encoding": "gzip, deflate",
            "accept": "*/*",
            "connection": "keep-alive",
            "content-type": "application/json",
            "content-length": "1435"
        },
        "params": {},
        "query": {},
        "body": {
            "task_id": "task_id",
            "status": "completed",
            "result": {
                "workflow_id": "task_id",
                "create_at": "2025-12-19T17:40:55.574174",
                "input_params": {
                    "task_name": "ffmpeg.crop_subtitle_images",
                    "input_data": {
                        "video_path": "http://host.docker.internal:9000/yivideo/task_id/223.mp4",
                        "subtitle_area": [0, 607, 1280, 679],
                        "upload_cropped_images_to_minio": true,
                        "compress_directory_before_upload": true,
                        "compression_format": "zip",
                        "compression_level": "default"
                    },
                    "callback_url": "http://host.docker.internal:5678/webhook-waiting/2042/t3"
                },
                "shared_storage_path": "/share/workflows/task_id",
                "stages": {
                    "ffmpeg.crop_subtitle_images": {
                        "status": "SUCCESS",
                        "input_params": {
                            "video_path": "/share/workflows/task_id/223.mp4"
                        },
                        "output": {
                            "cropped_images_path": "/share/workflows/task_id/cropped_images/frames",
                            "cropped_images_minio_url": "http://host.docker.internal:9000/yivideo/task_id/cropped_images",
                            "compressed_archive_url": "http://host.docker.internal:9000/yivideo/task_id/cropped_images/frames_compressed.zip",
                            "cropped_images_files_count": 8202,
                            "compression_info": {
                                "original_size": 194080122,
                                "compressed_size": 193156903,
                                "compression_ratio": 0.004756896226600693,
                                "files_count": 8202,
                                "compression_time": 7.908844470977783,
                                "checksum": "be90eb30df99309bd6d2aadc5ab615a5ece311d880416f371c23053e2a21dbd4",
                                "format": "zip"
                            }
                        },
                        "error": null,
                        "duration": 23.2634117603302
                    }
                },
                "error": null
            },
            "timestamp": "2025-12-19T17:41:18.957192Z"
        },
        "webhookUrl": "http://host.docker.internal:5678/webhook-test/t3",
        "executionMode": "test"
    }
]
```

### 检查字幕区域 - paddleocr.detect_subtitle_area

```json
[
    {
        "headers": {
            "host": "host.docker.internal:5678",
            "user-agent": "YiVideo-API-Gateway/1.0",
            "accept-encoding": "gzip, deflate",
            "accept": "*/*",
            "connection": "keep-alive",
            "content-type": "application/json",
            "content-length": "1030"
        },
        "params": {},
        "query": {},
        "body": {
            "task_id": "task_id",
            "status": "completed",
            "result": {
                "workflow_id": "task_id",
                "create_at": "2025-12-19T17:42:41.133347",
                "input_params": {
                    "task_name": "paddleocr.detect_subtitle_area",
                    "input_data": {
                        "keyframe_dir": "http://host.docker.internal:9000/yivideo/task_id/keyframes/keyframes_compressed.zip",
                        "download_from_minio": true
                    },
                    "callback_url": "http://host.docker.internal:5678/webhook-waiting/2043"
                },
                "shared_storage_path": "/share/workflows/task_id",
                "stages": {
                    "paddleocr.detect_subtitle_area": {
                        "status": "SUCCESS",
                        "input_params": {},
                        "output": {
                            "subtitle_area": [0, 607, 1280, 679],
                            "downloaded_keyframes_dir": "/share/workflows/task_id/downloaded_keyframes",
                            "input_source": "url_download",
                            "url_download_result": {
                                "total_files": 100,
                                "downloaded_files_count": 100,
                                "downloaded_local_dir": "/share/workflows/task_id/downloaded_keyframes",
                                "original_url": "/share/workflows/task_id/downloaded_keyframes"
                            }
                        },
                        "error": null,
                        "duration": 38.96100926399231
                    }
                },
                "error": null
            },
            "timestamp": "2025-12-19T17:43:20.277695Z"
        },
        "webhookUrl": "http://host.docker.internal:5678/webhook-test/6747f37b-48e9-4b14-aa74-858a3a3137b0",
        "executionMode": "test"
    }
]
```

### 合并字幕条 - paddleocr.create_stitched_images

```json
[
    {
        "headers": {
            "host": "host.docker.internal:5678",
            "user-agent": "YiVideo-API-Gateway/1.0",
            "accept-encoding": "gzip, deflate",
            "accept": "*/*",
            "connection": "keep-alive",
            "content-type": "application/json",
            "content-length": "1567"
        },
        "params": {},
        "query": {},
        "body": {
            "task_id": "task_id",
            "status": "completed",
            "result": {
                "workflow_id": "task_id",
                "create_at": "2025-12-19T17:44:17.256367",
                "input_params": {
                    "task_name": "paddleocr.create_stitched_images",
                    "input_data": {
                        "cropped_images_path": "http://host.docker.internal:9000/yivideo/task_id/cropped_images/frames_compressed.zip",
                        "subtitle_area": [0, 607, 1280, 679],
                        "upload_stitched_images_to_minio": true,
                        "auto_decompress": true
                    },
                    "callback_url": "http://host.docker.internal:5678/webhook-waiting/2044/t3"
                },
                "shared_storage_path": "/share/workflows/task_id",
                "stages": {
                    "paddleocr.create_stitched_images": {
                        "status": "SUCCESS",
                        "input_params": {
                            "cropped_images_path": "http://host.docker.internal:9000/yivideo/task_id/cropped_images/frames_compressed.zip",
                            "subtitle_area": [0, 607, 1280, 679]
                        },
                        "output": {
                            "multi_frames_path": "/share/workflows/task_id/multi_frames",
                            "manifest_path": "/share/workflows/task_id/multi_frames.json",
                            "multi_frames_minio_url": "http://host.docker.internal:9000/yivideo/task_id/stitched_images/multi_frames_compressed.zip",
                            "compression_info": {
                                "original_size": 250840772,
                                "compressed_size": 239589424,
                                "compression_ratio": 0.044854542227289906,
                                "files_count": 821,
                                "compression_time": 10.598302125930786,
                                "checksum": "30444115f0aee886f404fc942a09f99f0fdacc2c722230aa8139575a9b462a2d",
                                "format": "zip"
                            },
                            "stitched_images_count": 821,
                            "manifest_minio_url": "http://host.docker.internal:9000/yivideo/task_id/manifest/multi_frames.json"
                        },
                        "error": null,
                        "duration": 30.788655042648315
                    }
                },
                "error": null
            },
            "timestamp": "2025-12-19T17:44:48.105151Z"
        },
        "webhookUrl": "http://host.docker.internal:5678/webhook-test/t3",
        "executionMode": "test"
    }
]
```

### OCR 识别 - paddleocr.perform_ocr

```json
[
    {
        "headers": {
            "host": "host.docker.internal:5678",
            "user-agent": "YiVideo-API-Gateway/1.0",
            "accept-encoding": "gzip, deflate",
            "accept": "*/*",
            "connection": "keep-alive",
            "content-type": "application/json",
            "content-length": "1155"
        },
        "params": {},
        "query": {},
        "body": {
            "task_id": "task_id",
            "status": "completed",
            "result": {
                "workflow_id": "task_id",
                "create_at": "2025-12-19T17:45:29.097809",
                "input_params": {
                    "task_name": "paddleocr.perform_ocr",
                    "input_data": {
                        "manifest_path": "http://host.docker.internal:9000/yivideo/task_id/manifest/multi_frames.json",
                        "multi_frames_path": "http://host.docker.internal:9000/yivideo/task_id/stitched_images/multi_frames_compressed.zip",
                        "upload_ocr_results_to_minio": true
                    },
                    "callback_url": "http://host.docker.internal:5678/webhook-waiting/2045/t3"
                },
                "shared_storage_path": "/share/workflows/task_id",
                "stages": {
                    "paddleocr.perform_ocr": {
                        "status": "SUCCESS",
                        "input_params": {
                            "manifest_path": "http://host.docker.internal:9000/yivideo/task_id/manifest/multi_frames.json",
                            "multi_frames_path": "http://host.docker.internal:9000/yivideo/task_id/stitched_images/multi_frames_compressed.zip"
                        },
                        "output": {
                            "ocr_results_path": "/share/workflows/task_id/ocr_results.json",
                            "ocr_results_minio_url": "http://host.docker.internal:9000/yivideo/task_id/ocr_results/ocr_results.json"
                        },
                        "error": null,
                        "duration": 166.86453533172607
                    }
                },
                "error": null
            },
            "timestamp": "2025-12-19T17:48:16.089122Z"
        },
        "webhookUrl": "http://host.docker.internal:5678/webhook-test/t3",
        "executionMode": "test"
    }
]
```

### 删除目录

```json
[
    {
        "success": true,
        "message": "目录删除成功: /share/workflows/asr_subtitle_1765312066975",
        "file_path": "/share/workflows/asr_subtitle_1765312066975",
        "file_size": null
    }
]
```

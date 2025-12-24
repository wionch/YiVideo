# 实施任务清单

## 任务依赖关系

```
Phase 1: 基础设施
├─ Task 1.1: 创建路径工具函数
└─ Task 1.2: 更新 StateManager

Phase 2: Worker 节点迁移 (可并行)
├─ Task 2.1: FFmpeg 服务
├─ Task 2.2: Faster-Whisper 服务
├─ Task 2.3: Audio Separator 服务
├─ Task 2.4: Pyannote Audio 服务
├─ Task 2.5: PaddleOCR 服务
├─ Task 2.6: WService 字幕服务
└─ Task 2.7: IndexTTS 服务

Phase 3: 测试与文档
├─ Task 3.1: 集成测试
├─ Task 3.2: 更新 API 文档
└─ Task 3.3: 兼容性验证
```

---

## Phase 1: 基础设施

### Task 1.1: 创建路径工具函数

**目标**: 实现统一的路径生成和解析工具

**文件**:
- 新建: `services/common/path_builder.py`

**功能需求**:
1. `build_node_output_path(task_id, node_name, file_type, filename)` - 生成节点输出路径
2. `build_temp_path(task_id, node_name, filename)` - 生成临时文件路径
3. `build_minio_path(task_id, node_name, file_type, filename)` - 生成 MinIO 路径
4. `parse_node_path(path)` - 解析路径获取节点和类型信息
5. 向后兼容: 支持识别旧路径格式

**验证**:
- [x] 单元测试覆盖所有路径生成场景
- [x] 旧路径解析测试通过

**预计工作量**: 4 小时

**实施状态**: ✅ **已完成** (2025-12-24)

---

### Task 1.2: 更新 StateManager

**目标**: 修改 MinIO 上传路径生成逻辑

**文件**:
- `services/common/state_manager.py`
- `services/common/minio_directory_upload.py`

**变更点**:
1. 引入 `path_builder` 模块
2. 更新 `_upload_file_to_minio()` 方法,使用新的路径生成逻辑
3. 更新目录上传函数,保持路径结构一致性
4. 添加节点名称传递机制 (从 context 或 stage 信息中提取)

**验证**:
- [x] MinIO 上传路径符合新规范
- [x] 本地路径与 MinIO 路径结构一致
- [x] 单元测试通过

**预计工作量**: 6 小时

**实施状态**: ✅ **已完成** (2025-12-24)

**实施说明**:
- 已在 `state_manager.py` 中引入 `convert_local_to_minio_path()` 函数
- 更新了文件上传路径生成逻辑 (单个文件和数组文件)
- 更新了目录压缩上传路径生成逻辑
- 路径转换逻辑支持新旧格式兼容

---

## Phase 2: Worker 节点迁移

### Task 2.1: FFmpeg 服务

**目标**: 更新所有 FFmpeg 节点的输出路径

**文件**:
- `services/workers/ffmpeg_service/executors/extract_audio_executor.py`
- `services/workers/ffmpeg_service/executors/extract_keyframes_executor.py`
- `services/workers/ffmpeg_service/app/tasks.py` (crop_subtitle_images, split_audio_segments)

**变更点**:
1. 替换硬编码路径为 `path_builder` 调用
2. 更新输出字段名 (保持向后兼容)
3. 调整临时文件路径

**路径映射**:
| 旧路径 | 新路径 |
|--------|--------|
| `{task_id}/audio/demo.wav` | `{task_id}/nodes/ffmpeg.extract_audio/audio/demo.wav` |
| `{task_id}/keyframes/` | `{task_id}/nodes/ffmpeg.extract_keyframes/images/keyframes/` |
| `{task_id}/cropped_images/` | `{task_id}/nodes/ffmpeg.crop_subtitle_images/images/cropped/` |
| `{task_id}/audio_segments/` | `{task_id}/nodes/ffmpeg.split_audio_segments/audio/segments/` |

**验证**:
- [ ] 单元测试通过
- [ ] 集成测试验证文件可正常生成和访问

**预计工作量**: 8 小时

---

### Task 2.2: Faster-Whisper 服务

**目标**: 更新 ASR 节点输出路径

**文件**:
- `services/workers/faster_whisper_service/executors/transcribe_executor.py`
- `services/workers/faster_whisper_service/app/tasks.py`

**变更点**:
1. 更新 `transcribe_data_{workflow_short_id}.json` 保存路径
2. 临时文件路径迁移到 `temp/faster_whisper.transcribe_audio/`

**路径映射**:
| 旧路径 | 新路径 |
|--------|--------|
| `{task_id}/transcribe_data_xxx.json` | `{task_id}/nodes/faster_whisper.transcribe_audio/data/transcribe_data_xxx.json` |
| `{task_id}/tmp/faster_whisper_result_xxx.json` | `{task_id}/temp/faster_whisper.transcribe_audio/result_xxx.json` |

**验证**:
- [ ] 转录结果文件路径正确
- [ ] 下游节点可正常读取

**预计工作量**: 4 小时

---

### Task 2.3: Audio Separator 服务

**目标**: 更新音频分离节点路径

**文件**:
- `services/workers/audio_separator_service/executors/separate_vocals_executor.py`
- `services/workers/audio_separator_service/app/config.py`

**变更点**:
1. 更新 `output_dir` 配置默认值
2. 修改分离音频文件保存路径

**路径映射**:
| 旧路径 | 新路径 |
|--------|--------|
| `{task_id}/audio/audio_separated/demo_(Vocals).flac` | `{task_id}/nodes/audio_separator.separate_vocals/audio/demo_(Vocals).flac` |

**验证**:
- [ ] 分离音频文件路径正确
- [ ] MinIO 上传路径一致

**预计工作量**: 3 小时

---

### Task 2.4: Pyannote Audio 服务

**目标**: 更新说话人分离节点路径

**文件**:
- `services/workers/pyannote_audio_service/executors/diarize_speakers_executor.py`
- `services/workers/pyannote_audio_service/executors/validate_diarization_executor.py`
- `services/workers/pyannote_audio_service/executors/get_speaker_segments_executor.py`

**变更点**:
1. 更新 `diarization/` 目录路径
2. 调整结果文件命名和存储位置

**路径映射**:
| 旧路径 | 新路径 |
|--------|--------|
| `{task_id}/diarization/diarization_result.json` | `{task_id}/nodes/pyannote_audio.diarize_speakers/data/diarization_result.json` |

**验证**:
- [ ] 分离结果文件路径正确
- [ ] 下游合并节点可正常读取

**预计工作量**: 4 小时

---

### Task 2.5: PaddleOCR 服务

**目标**: 更新 OCR 相关节点路径

**文件**:
- `services/workers/paddleocr_service/executors/detect_subtitle_area_executor.py`
- `services/workers/paddleocr_service/executors/create_stitched_images_executor.py`
- `services/workers/paddleocr_service/executors/perform_ocr_executor.py`
- `services/workers/paddleocr_service/executors/postprocess_and_finalize_executor.py`

**变更点**:
1. 更新关键帧下载目录
2. 更新拼接图保存路径
3. 更新 OCR 结果保存路径
4. 更新最终字幕文件路径

**路径映射**:
| 旧路径 | 新路径 |
|--------|--------|
| `{task_id}/downloaded_keyframes/` | `{task_id}/temp/paddleocr.detect_subtitle_area/keyframes/` |
| `{task_id}/multi_frames/` | `{task_id}/nodes/paddleocr.create_stitched_images/images/stitched/` |
| `{task_id}/ocr_results.json` | `{task_id}/nodes/paddleocr.perform_ocr/data/ocr_results.json` |
| `{task_id}/demo.srt` | `{task_id}/nodes/paddleocr.postprocess_and_finalize/subtitles/demo.srt` |

**验证**:
- [ ] 所有中间文件路径正确
- [ ] 最终字幕文件可正常生成

**预计工作量**: 8 小时

---

### Task 2.6: WService 字幕服务

**目标**: 更新字幕处理节点路径

**文件**:
- `services/workers/wservice/executors/generate_subtitle_files_executor.py`
- `services/workers/wservice/executors/merge_with_word_timestamps_executor.py`
- `services/workers/wservice/app/tasks.py`

**变更点**:
1. 更新 `subtitles/` 目录路径
2. 更新合并结果文件路径
3. 调整临时文件路径

**路径映射**:
| 旧路径 | 新路径 |
|--------|--------|
| `{task_id}/subtitles/subtitle.srt` | `{task_id}/nodes/wservice.generate_subtitle_files/subtitles/subtitle.srt` |
| `{task_id}/transcribe_data_word_timestamps_merged.json` | `{task_id}/nodes/wservice.merge_with_word_timestamps/data/merged.json` |

**验证**:
- [ ] 字幕文件路径正确
- [ ] 合并结果可正常访问

**预计工作量**: 6 小时

---

### Task 2.7: IndexTTS 服务

**目标**: 更新 TTS 节点路径 (如需要)

**文件**:
- `services/workers/indextts_service/executors/generate_speech_executor.py`

**变更点**:
1. 确认当前 TTS 输出路径是否需要调整
2. 如需要,更新为新路径规范

**验证**:
- [ ] TTS 输出路径符合规范 (如有变更)

**预计工作量**: 2 小时

---

## Phase 3: 测试与文档

### Task 3.1: 集成测试

**目标**: 验证新路径在完整工作流中的正确性

**测试用例**:
1. 端到端工作流测试 (ASR → 字幕生成 → MinIO 上传)
2. 路径解析测试 (新旧路径兼容性)
3. MinIO 上传下载测试
4. 临时文件清理测试

**文件**:
- 新建: `tests/integration/test_standardized_paths.py`

**验证**:
- [ ] 所有集成测试通过
- [ ] 路径一致性检查通过
- [ ] 无路径相关错误日志

**预计工作量**: 8 小时

---

### Task 3.2: 更新 API 文档

**目标**: 更新文档中的路径示例

**文件**:
- `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`

**变更点**:
1. 更新所有节点的输出路径示例
2. 添加路径规范说明章节
3. 更新 MinIO URL 示例

**验证**:
- [ ] 文档示例与实际输出一致
- [ ] 路径规范章节清晰易懂

**预计工作量**: 4 小时

---

### Task 3.3: 兼容性验证

**目标**: 确保新旧路径共存不影响现有功能

**测试场景**:
1. 旧任务数据读取 (模拟历史数据)
2. 新任务使用新路径
3. 路径解析函数正确识别新旧格式

**验证**:
- [ ] 旧路径数据可正常读取
- [ ] 新路径数据正常生成
- [ ] 无兼容性问题报告

**预计工作量**: 4 小时

---

## 总计工作量估算

| 阶段 | 任务数 | 预计工作量 |
|------|--------|-----------|
| Phase 1: 基础设施 | 2 | 10 小时 |
| Phase 2: Worker 迁移 | 7 | 35 小时 |
| Phase 3: 测试与文档 | 3 | 16 小时 |
| **总计** | **12** | **61 小时** |

**建议实施周期**: 2 周 (考虑代码审查和返工时间)

---

## 里程碑

- [x] **Milestone 1** (Week 1): Phase 1 完成,核心路径工具可用 ✅ **已完成 (2025-12-24)**
- [ ] **Milestone 2** (Week 1-2): Phase 2 完成,所有节点迁移完成
- [ ] **Milestone 3** (Week 2): Phase 3 完成,测试通过,文档更新
- [ ] **Milestone 4** (Week 2): 代码审查通过,合并到主分支

# 提案：标准化文件路径结构

## Why

当前各个工作节点产出的文件保存路径缺乏统一规范,导致以下问题:

1. **可维护性差**: 不同节点使用不同的子目录命名,开发者难以快速定位文件
2. **可追溯性弱**: 无法从路径直观判断文件来源节点和处理阶段
3. **MinIO 与本地路径不一致**: 增加了外部系统集成的复杂度
4. **临时文件管理混乱**: 临时文件散落各处,清理困难,浪费磁盘空间

建立统一的路径规范可以显著提升系统的可维护性、可追溯性和运维效率,为未来的扩展和优化奠定基础。

## 概述 (Summary)

当前各个工作节点产出的文件保存路径缺乏统一规范,导致路径混乱、难以维护和追踪。本提案旨在建立一套专业的、符合行业最佳实践的文件路径组织规范,统一本地存储(`/share`)和对象存储(MinIO)的路径结构。

## 动机 (Motivation)

### 当前问题

1. **路径不一致**: 不同节点使用不同的子目录命名和组织方式
   - 示例: `audio/audio_separated` vs `diarization` vs `subtitles` vs `cropped_images`

2. **缺乏层次结构**: 文件直接堆积在 task_id 目录下,无法快速定位特定节点的输出

3. **MinIO 与本地路径不对齐**: 本地路径为 `/share/workflows/{task_id}/audio/demo.wav`,但 MinIO 可能是 `{task_id}/demo.wav`,缺乏一致性

4. **临时文件管理混乱**: 临时文件散落在各处,清理困难

5. **可追溯性差**: 无法从路径直观判断文件来源节点和处理阶段

### 业务价值

- **提升可维护性**: 统一路径规范降低开发和运维成本
- **增强可追溯性**: 从路径即可识别文件来源和处理流程
- **简化清理逻辑**: 规范化路径便于批量清理和生命周期管理
- **改善用户体验**: 一致的 MinIO URL 结构便于外部系统集成

## 调研 (Research)

### 行业最佳实践

参考主流视频处理平台和数据管道系统的路径组织模式:

1. **按阶段分层**: `{project}/{task_id}/{stage}/{artifact_type}/{files}`
2. **语义化命名**: 目录名清晰表达内容类型 (如 `audio/`, `video/`, `subtitles/`)
3. **时间戳隔离**: 临时文件使用时间戳或 UUID 避免冲突
4. **本地与远程对齐**: 对象存储路径镜像本地结构,便于同步和备份

### 节点覆盖度验证

经过系统性代码扫描,项目中共有 **22 个 Celery 任务节点**,分布在 7 个服务中:

| 服务 | 节点数 | 涉及文件操作 |
|------|--------|-------------|
| FFmpeg | 4 | 4 个 (全部) |
| Faster-Whisper | 1 | 1 个 (全部) |
| Audio Separator | 1 | 1 个 (全部) |
| Pyannote Audio | 3 | 3 个 (全部) |
| PaddleOCR | 4 | 4 个 (全部) |
| WService | 6 | 6 个 (全部) |
| IndexTTS | 3 | 1 个 (generate_speech) |

**覆盖情况**:
- 本提案覆盖 **20 个文件操作节点** (100% 覆盖率)
- 排除 2 个仅返回配置数据的节点 (`indextts.list_voice_presets`, `indextts.get_model_info`)

### 当前路径分析

通过代码扫描发现的典型路径模式:

```python
# 当前实现 (不一致)
/share/workflows/{task_id}/audio/demo.wav                    # ffmpeg.extract_audio
/share/workflows/{task_id}/audio/audio_separated/...        # audio_separator
/share/workflows/{task_id}/diarization/...                  # pyannote_audio
/share/workflows/{task_id}/subtitles/...                    # wservice
/share/workflows/{task_id}/cropped_images/...               # ffmpeg.crop
/share/workflows/{task_id}/keyframes/...                    # ffmpeg.extract_keyframes
/share/workflows/{task_id}/tmp/...                          # 临时文件
```

MinIO 路径当前主要为: `{task_id}/{filename}`,缺乏节点和类型信息。

## 提议的解决方案 (Proposed Solution)

### 标准路径结构

#### 本地存储 (`/share`)

```
/share/workflows/{task_id}/
├── nodes/                          # 节点输出根目录
│   ├── {node_name}/                # 节点专属目录 (如 ffmpeg.extract_audio)
│   │   ├── audio/                  # 音频文件
│   │   ├── video/                  # 视频文件
│   │   ├── images/                 # 图片文件
│   │   ├── subtitles/              # 字幕文件
│   │   ├── data/                   # JSON/文本数据
│   │   └── archives/               # 压缩包
│   └── ...
├── temp/                           # 临时文件 (统一管理)
│   └── {node_name}/                # 按节点隔离临时文件
└── metadata/                       # 元数据文件 (可选,用于审计)
    └── manifest.json
```

#### MinIO 对象存储

```
{bucket}/{task_id}/
├── nodes/
│   ├── {node_name}/
│   │   ├── audio/
│   │   ├── video/
│   │   ├── images/
│   │   ├── subtitles/
│   │   ├── data/
│   │   └── archives/
│   └── ...
└── temp/                           # 临时文件 (可选上传)
```

### 路径映射示例

| 节点 | 输出类型 | 本地路径 | MinIO 路径 |
|------|---------|---------|-----------|
| `ffmpeg.extract_audio` | 音频文件 | `/share/workflows/{task_id}/nodes/ffmpeg.extract_audio/audio/demo.wav` | `{task_id}/nodes/ffmpeg.extract_audio/audio/demo.wav` |
| `audio_separator.separate_vocals` | 分离音频 | `/share/workflows/{task_id}/nodes/audio_separator.separate_vocals/audio/demo_(Vocals).flac` | `{task_id}/nodes/audio_separator.separate_vocals/audio/demo_(Vocals).flac` |
| `pyannote_audio.diarize_speakers` | 分离结果 | `/share/workflows/{task_id}/nodes/pyannote_audio.diarize_speakers/data/diarization_result.json` | `{task_id}/nodes/pyannote_audio.diarize_speakers/data/diarization_result.json` |
| `paddleocr.create_stitched_images` | 拼接图 | `/share/workflows/{task_id}/nodes/paddleocr.create_stitched_images/images/multi_frames/` | `{task_id}/nodes/paddleocr.create_stitched_images/images/multi_frames/` |
| `wservice.generate_subtitle_files` | 字幕文件 | `/share/workflows/{task_id}/nodes/wservice.generate_subtitle_files/subtitles/subtitle.srt` | `{task_id}/nodes/wservice.generate_subtitle_files/subtitles/subtitle.srt` |

### 关键设计决策

1. **引入 `nodes/` 层级**: 明确区分节点输出与临时文件/元数据
2. **节点名作为目录**: 使用完整节点名 (如 `ffmpeg.extract_audio`) 而非简写,提升可读性
3. **类型子目录**: 在节点目录下按文件类型分类 (`audio/`, `video/`, `data/` 等)
4. **本地与 MinIO 对齐**: 保持相同的目录结构,仅根路径不同
5. **临时文件隔离**: 统一放在 `temp/{node_name}/` 下,便于清理

### 向后兼容性

**破坏性变更**: 是

- 现有代码中硬编码的路径需要全面更新
- 已存储的历史数据路径不变,仅影响新任务

**迁移策略**:
- 新任务立即使用新路径规范
- 旧任务数据保持不变,通过 `task_id` 时间戳判断使用哪套路径逻辑
- 提供路径转换工具函数,支持新旧路径的兼容读取

## 非目标 (Non-Goals)

- 不迁移历史数据 (已完成任务的文件路径保持不变)
- 不改变 `WorkflowContext` 的核心数据结构
- 不引入新的存储后端或文件系统

## 影响范围 (Impact)

### 受影响的模块

1. **所有 Worker 节点**: 需要更新文件输出路径逻辑
   - `services/workers/ffmpeg_service/`
   - `services/workers/faster_whisper_service/`
   - `services/workers/audio_separator_service/`
   - `services/workers/pyannote_audio_service/`
   - `services/workers/paddleocr_service/`
   - `services/workers/wservice/`
   - `services/workers/indextts_service/`

2. **StateManager**: 更新 MinIO 上传路径生成逻辑
   - `services/common/state_manager.py`

3. **文件服务**: 更新路径解析和下载逻辑
   - `services/common/file_service.py`
   - `services/common/minio_directory_upload.py`

4. **临时文件工具**: 更新临时路径生成
   - `services/common/temp_path_utils.py`

5. **API 文档**: 更新路径示例
   - `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`

### 测试需求

- 单元测试: 验证路径生成函数的正确性
- 集成测试: 验证新路径在完整工作流中的可用性
- 兼容性测试: 验证新旧路径的共存逻辑

## 替代方案 (Alternatives Considered)

### 方案 A: 扁平化路径 (不推荐)

```
/share/workflows/{task_id}/{node_name}_{file_type}_{filename}
```

**优点**: 路径简短
**缺点**:
- 文件混乱,难以浏览
- 不支持目录级别的批量操作
- 压缩包等复杂输出难以组织

### 方案 B: 按文件类型分层 (不推荐)

```
/share/workflows/{task_id}/audio/{node_name}/demo.wav
```

**优点**: 按类型聚合便于查找同类文件
**缺点**:
- 无法快速定位特定节点的所有输出
- 跨类型节点 (如同时输出音频和字幕) 文件分散

### 方案 C: 时间戳目录 (过度设计)

```
/share/workflows/{task_id}/{timestamp}/{node_name}/...
```

**优点**: 支持同一节点多次执行
**缺点**:
- 当前系统基于 task_id 复用,不需要时间戳隔离
- 增加路径复杂度,违反 KISS 原则

**最终选择**: 提议的方案 (按节点分层 + 类型子目录) 平衡了可读性、可维护性和实用性。

## 实施计划 (Implementation Plan)

见 `tasks.md`

## 风险与缓解 (Risks & Mitigation)

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 路径更新遗漏导致文件找不到 | 高 | 全面的集成测试 + 代码审查 |
| MinIO 路径变更影响外部系统 | 中 | 文档更新 + 版本化 API 响应 |
| 临时文件清理逻辑失效 | 低 | 新增专门的清理测试用例 |
| 开发周期延长 | 中 | 分阶段实施,优先核心节点 |

## 成功指标 (Success Metrics)

- [ ] 所有节点输出路径符合新规范
- [ ] MinIO URL 与本地路径结构一致
- [ ] 集成测试覆盖率 > 90%
- [ ] 文档更新完成
- [ ] 无路径相关的生产问题报告 (实施后 2 周)

## 提案验证 (Proposal Validation)

### 节点覆盖度检查

✅ **验证完成** (2025-12-24)

- **全量节点**: 22 个 Celery 任务节点
- **文件操作节点**: 20 个
- **提案覆盖**: 20 个 (100%)
- **合理排除**: 2 个配置查询节点

### 路径模式完整性检查

✅ **验证完成**

提案已覆盖所有发现的路径模式:
- ✅ 直接子目录: `audio/`, `keyframes/`, `subtitles/`
- ✅ 嵌套子目录: `audio/audio_separated/`, `diarization/`
- ✅ 临时文件: `tmp/`, `download_*_{timestamp}/`
- ✅ 混合路径: `cropped_images/`, `multi_frames/`

### OpenSpec 规范验证

✅ **通过验证**

```bash
openspec validate standardize-file-path-structure
# ✅ Change 'standardize-file-path-structure' is valid
```

## 参考资料 (References)

- [SINGLE_TASK_API_REFERENCE.md](docs/technical/reference/SINGLE_TASK_API_REFERENCE.md)
- [项目架构规范](openspec/specs/project-architecture/spec.md)
- [本地目录管理规范](openspec/specs/local-directory-management/spec.md)
- [复核报告](openspec/changes/standardize-file-path-structure/REVIEW.md) (内部文档)

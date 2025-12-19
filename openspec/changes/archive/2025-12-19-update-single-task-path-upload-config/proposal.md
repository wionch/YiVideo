## Change: 单任务节点路径返回双轨与上传开关

## Why
- 现有单任务文档部分节点仅展示本地路径或仅展示 MinIO URL，缺少“本地+远程”并行示例，集成方容易误判可用字段。
- state_manager 在更新 WorkflowContext 时总是尝试上传并覆盖路径，config.yml 缺少上传开关，导致远程路径出现/缺失不可控。
- 需要在文档、规格与配置层同步定义“本地路径始终可用，远程路径由上传开关决定”的规则。

## Research (REQUIRED)
### What was inspected
- Specs:
  - `openspec/specs/single-task-api-docs/spec.md:20-37`（输出路径场景仅要求“以本地路径为主”，未涵盖上传开关/双路径展示）
- Docs:
  - `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:162-289`（`ffmpeg.extract_audio`/`ffmpeg.split_audio_segments` 仅给出本地输出）
  - `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:324-374`（`faster_whisper.transcribe_audio` 仅本地 `segments_file`）
  - `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:464-513`（`pyannote_audio.diarize_speakers` 输出示例只给远程 `diarization_file`）
  - `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:934-970`（`wservice.correct_subtitles` 输出示例只给远程 `corrected_subtitle_path`）
- Code:
  - `services/workers/ffmpeg_service/app/tasks.py:275-425`（`extract_audio` 输出仅 `audio_path` 本地）
  - `services/workers/ffmpeg_service/app/tasks.py:760-1027`（`split_audio_segments` 输出本地目录/文件，未生成 MinIO URL）
  - `services/workers/faster_whisper_service/app/tasks.py:440-673`（`transcribe_audio` 输出本地 `segments_file`）
  - `services/workers/pyannote_audio_service/app/tasks.py:76-363`（`diarize_speakers` 输出本地 `diarization_file`，可选 `diarization_file_minio_url`）
  - `services/workers/wservice/app/tasks.py:933-1027`（`correct_subtitles` 输出本地 `corrected_subtitle_path`，无上传字段）
  - `services/common/state_manager.py:59-168,275-277`（`_upload_files_to_minio` 在每次 `update_workflow_state` 时无条件尝试上传并覆盖路径）
- Config:
  - `config.yml` 未声明任何上传/MinIO 自动开关（`grep -n "upload" config.yml` 无结果）
- Commands:
  - `openspec list`
  - `openspec list --specs`
  - `grep -n "upload" config.yml`

### Findings (with evidence)
- Finding 1: state_manager 始终执行 `_upload_files_to_minio`，缺少配置开关，导致是否产生 MinIO URL 不可控。
  - Evidence: `services/common/state_manager.py:59-168,275-277` 展示无条件上传流程；`config.yml` 无相关开关（grep 无匹配）。
  - Decision: Doc+Code+Spec（新增 config 开关并在文档/规格声明本地路径恒定、远程路径受开关控制）。

- Finding 2: `ffmpeg.extract_audio`、`ffmpeg.split_audio_segments`、`faster_whisper.transcribe_audio` 文档仅列本地路径；实际代码仅返回本地路径，远程路径需依赖上传流程。
  - Evidence: 文档 `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:162-289,324-374`；代码 `services/workers/ffmpeg_service/app/tasks.py:275-425,760-1027`，`services/workers/faster_whisper_service/app/tasks.py:440-673`。
  - Decision: Doc+Spec（所有节点输出示例改为“本地路径 + 可选远程 URL”，并引用上传开关）。

- Finding 3: `pyannote_audio.diarize_speakers` 文档仅展示 MinIO URL，忽略本地路径与可选 `diarization_file_minio_url`。
  - Evidence: 文档 `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:464-513`；代码 `services/workers/pyannote_audio_service/app/tasks.py:76-363` 输出包含本地与可选远程字段。
  - Decision: Doc+Spec（双路径示例，明确远程字段受上传开关约束）。

- Finding 4: `wservice.correct_subtitles` 文档输出为远程 URL，但实现仅返回本地路径（远程仅可能由自动上传产生）。
  - Evidence: 文档 `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:934-970`；代码 `services/workers/wservice/app/tasks.py:933-1027` 仅设置本地路径字段。
  - Decision: Doc+Spec（改为本地+可选远程描述，并与上传开关关联）。

- Finding 5: 多数节点输出字段名不含 `minio`，但 state_manager 上传后会直接用 MinIO URL 覆盖原字段，造成“名称是本地、值是远程”的混用；尚无全节点输出审核。
  - Evidence: `services/common/state_manager.py:78-106` 将 `segments_file/audio_path/video_path/subtitle_path/output_path` 直接替换为 MinIO URL；`docs/technical/reference/SINGLE_TASK_API_REFERENCE.md` 多节点输出未区分本地/远程字段，且未覆盖所有节点（音频分离、PaddleOCR、TTS、字幕生成/合并等）。
  - Decision: Doc+Code+Spec（state_manager 上传时保留原本地字段，远程写入 `*_minio_url`/`minio_files` 等专用字段；文档要求全节点输出以“本地+可选远程”呈现并全量审计）。

### Why this approach (KISS/YAGNI check)
- 引入单一全局上传开关（默认保持当前行为）避免在每个节点重复新增参数。
- 文档统一双轨输出格式，减少集成方猜测；不引入新的存储后端或回调机制。
- 非目标：不调整各任务的业务逻辑或新增上传流水线，仅控制是否执行已有上传流程并完善文档。

## What Changes
- 在 config.yml 增加“自动上传到 MinIO”开关，并在 state_manager 读取该开关决定是否触发 `_upload_files_to_minio`。
- 调整 state_manager 上传行为：不覆盖原本地字段，远程 URL 写入 `*_minio_url`/`minio_files` 等专用字段。
- 对 `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md` 中所有节点输出示例执行“本地+可选远程”审计，补齐缺失节点并纠正字段名/值不匹配。
- 更新 `single-task-api-docs` 规格，要求节点章节同时展示本地/远程路径、上传开关说明及字段命名规则；补充 `project-architecture` 规格以覆盖上传开关与“追加而非覆盖”行为。

## Impact
- Affected specs:
  - `single-task-api-docs`（MODIFIED：输出示例需双轨并标注上传开关与字段命名规则）
  - `project-architecture`（ADDED：上传行为可配置且不得覆盖本地字段）
- Affected code/docs:
  - `services/common/state_manager.py`（读取开关、可禁用上传）
  - `config.yml`（新增开关）
  - `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`（各节点输出示例与说明）
- Risks: 默认值需兼容现有依赖远程 URL 的集成；state_manager 不再覆盖本地字段后需确保消费方读取远程字段；文档改动需覆盖所有节点避免遗漏。

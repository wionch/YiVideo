## Traceability (Research → Tasks)
- Finding 1 → 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7
- Finding 2 → 1.8
- Finding 3 → 1.9, 1.10

## 1. Implementation

- [x] 1.1 补充 `pyannote_audio.get_speaker_segments` 单任务小节
  - Evidence: proposal.md → Research → Finding 1 (Decision: 补文档并与节点一致)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:461-560`
  - Commands:
    - `grep -n "pyannote_audio.get_speaker_segments" docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 该节点示例与节点文档/代码一致，grep 能找到标题。

- [x] 1.2 补充 `pyannote_audio.validate_diarization` 单任务小节
  - Evidence: proposal.md → Research → Finding 1 (Decision: 补文档并与节点一致)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:561-620`
  - Commands:
    - `grep -n "pyannote_audio.validate_diarization" docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 文档新增请求体、WorkflowContext 输出和参数表，grep 能找到标题。

- [x] 1.3 补充 `paddleocr.postprocess_and_finalize` 单任务小节
  - Evidence: proposal.md → Research → Finding 1 (Decision: 补文档并与节点一致)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:640-780`
  - Commands:
    - `grep -n "paddleocr.postprocess_and_finalize" docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 文档新增该节点示例并与节点文档/代码产出一致。

- [x] 1.4 补充 `wservice.merge_speaker_segments` 单任务小节
  - Evidence: proposal.md → Research → Finding 1 (Decision: 补文档并与节点一致)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:940-1020`
  - Commands:
    - `grep -n "wservice.merge_speaker_segments" docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 文档新增该节点示例且字段对齐代码，grep 能找到标题。

- [x] 1.5 补充 `wservice.merge_with_word_timestamps` 单任务小节
  - Evidence: proposal.md → Research → Finding 1 (Decision: 补文档并与节点一致)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:1020-1100`
  - Commands:
    - `grep -n "wservice.merge_with_word_timestamps" docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 文档新增该节点示例且字段对齐代码，grep 能找到标题。

- [x] 1.6 补充 `wservice.prepare_tts_segments` 单任务小节
  - Evidence: proposal.md → Research → Finding 1 (Decision: 补文档并与节点一致)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:1100-1180`
  - Commands:
    - `grep -n "wservice.prepare_tts_segments" docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 文档新增该节点示例且字段对齐代码，grep 能找到标题。

- [x] 1.7 更新 `/v1/tasks/supported-tasks` 返回值涵盖全部支持单步任务的节点
  - Evidence: proposal.md → Research → Finding 1 (Decision: 更新路由输出，排除不支持单步的节点)
  - Edit scope: `services/api_gateway/app/single_task_api.py:307-349`
  - Commands:
    - `python -m compileall services/api_gateway/app/single_task_api.py`
  - Done when: supported_tasks 列表包含所有支持单步任务的 Celery 任务名，且不含不支持的节点。

- [x] 1.8 更新 `paddleocr.perform_ocr` 请求/输出示例为 manifest/multi_frames + ocr_results
  - Evidence: proposal.md → Research → Finding 2 (Decision: 更新示例与参数表)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:640-700`
  - Commands:
    - `grep -n "paddleocr.perform_ocr" docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 请求体使用 manifest_path/multi_frames_path，输出展示 ocr_results_path/ocr_results_minio_url，与代码一致。

- [x] 1.9 调整 `/v1/tasks` 状态/结果示例的创建时间字段描述以匹配实际响应
  - Evidence: proposal.md → Research → Finding 3 (Decision: 统一 create_at 字段)
  - Edit scope: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:9-80`
  - Commands:
    - `grep -n "create_at" -n docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
  - Done when: 文档示例字段与最终 API 响应一致（创建时间字段不被模型丢弃）。

- [x] 1.10 对齐状态响应模型/序列化以保留创建时间字段
  - Evidence: proposal.md → Research → Finding 3 (Decision: 统一 create_at 字段)
  - Edit scope: `services/api_gateway/app/single_task_models.py:15-80`
  - Commands:
    - `python -m compileall services/api_gateway/app/single_task_models.py`
  - Done when: TaskStatusResponse 与执行器返回的创建时间字段对齐（create_at 或等价字段）且编译通过。

## 2. Validation

- [x] 2.1 OpenSpec strict validation
  - Evidence: proposal.md → Research → Finding 1
  - Commands:
    - `openspec validate update-single-task-doc-consistency --strict`
  - Done when: 命令退出码为 0。

- [x] 2.2 Project checks
  - Evidence: proposal.md → Research → Finding 3
  - Commands:
    - `python -m compileall services/api_gateway/app`
  - Done when: 编译通过且无新增错误。

## 3. Self-check (ENFORCED)

- [x] 3.1 Each task touches exactly one file in Edit scope.
- [x] 3.2 Each task references exactly one Finding.
- [x] 3.3 No task contains conditional language (if needed/必要时/可能/按需/...).
- [x] 3.4 Each task includes Commands and an objective Done when.

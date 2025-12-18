# Change: 为单任务节点补充功能介绍与概述

## Why
当前单任务 API 文档的节点小节直接进入请求示例与参数表，没有任何功能介绍/概述，读者难以在查阅参数前快速理解节点用途与产出，增加了使用门槛并且不利于对照 `/v1/tasks/supported-tasks` 进行节点选择。

## Research (REQUIRED)

### What was inspected
- Specs:
  - `openspec/specs/single-task-api-docs/spec.md`: 行 20-25 仅要求节点列出请求/参数/输出示例，与 `/v1/tasks/supported-tasks` 对齐，但未要求功能介绍段落。
- Docs:
  - `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:102-168`：`ffmpeg.extract_keyframes` 等节点标题后直接出现“请求体/WorkflowContext/参数表”，没有功能描述。
  - `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:325-360`：`faster_whisper.transcribe_audio` 同样缺少功能介绍段落。
  - `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:463-510`：`pyannote_audio.diarize_speakers` 段落无任何功能概述文字。
  - `grep -n "功能" docs/technical/reference/SINGLE_TASK_API_REFERENCE.md` 无匹配，印证全文未包含功能介绍关键词。

### Findings (with evidence)
- Finding 1: 单任务节点文档段落缺少功能介绍/概述，读者只能从参数表或输出字段推测用途。  
  - Evidence: `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md:102-168`、`:325-360`、`:463-510` 显示各节点标题后直接进入请求/参数内容，无功能文字；`grep -n "功能" ...` 返回空。  
  - Decision: Doc+Spec —— 需要在每个节点小节补充功能介绍，并在规范层面要求保留该结构，避免后续遗漏。
- Finding 2: `single-task-api-docs` 规格的“单任务节点分节示例”未规定功能概述内容，导致文档缺口没有规范支撑。  
  - Evidence: `openspec/specs/single-task-api-docs/spec.md:20-25` 仅要求请求示例、参数表和输出示例，与 `/v1/tasks/supported-tasks` 对齐；未提及功能概述。  
  - Decision: Spec delta —— 更新该 requirement，强制每个节点小节在请求示例前包含功能概述（用途/核心输入输出/适用注意）。

### Why this approach (KISS/YAGNI check)
- 仅补充文档描述与相应规范要求，不改代码或接口行为，属于最小变更。
- 功能概述写在每个节点开头即可，不引入额外格式或重复段落，避免过度设计。
- 不新增模板或工具；直接复用现有文档结构。

## What Changes
- 更新 `single-task-api-docs` 规格，要求每个单任务节点文档小节在请求示例前提供功能概述（用途、输入预期、核心输出/上传、副作用或限制）。
- 在 `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md` 为当前列出的所有单任务节点（FFmpeg/Faster-Whisper/Audio Separator/Pyannote/PaddleOCR/IndexTTS/WService）补充对应的功能介绍/概述文案，保持与节点行为及参数/输出示例一致。

## Impact
- Affected specs:
  - `single-task-api-docs`（MODIFIED Requirement: 单任务节点分节示例，新增功能概述要求）
- Affected docs:
  - `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`（为所有单任务节点段落添加功能概述文本）
- Rollout / migration notes:
  - 无接口变更；文档更新后需与 `/v1/tasks/supported-tasks` 列表一致。
- Risks:
  - 功能概述措辞需与实际行为一致，需基于现有参数/输出示例与任务实现核对，避免误导用户。

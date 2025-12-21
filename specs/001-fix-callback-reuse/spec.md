# Feature Specification: callback 复用覆盖修复

**Feature Branch**: `001-fix-callback-reuse`  
**Created**: 2025-12-21  
**Status**: Draft  
**Input**: 场景还原：1）执行 ffmpeg 提取音频创建任务，成功；2）再次提取音频命中复用；3）执行一次 audio_separator 人声分离正常；4）再提取音频不再复用且 Redis 任务数据被覆盖，原提取阶段丢失。要求排查所有单任务节点，找出未集成 callback 复用的节点并修复；参考 `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md` 与已归档提案 `openspec/changes/archive/2025-12-21-update-single-task-callback-reuse`。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 复用命中保持阶段完整 (Priority: P1)

当用户在同一 `task_id` 下多次调用 `ffmpeg.extract_audio`，即使期间插入其他节点（如 `audio_separator.separate_vocals`），仍希望再次调用时立即命中复用并返回原有提取结果，不出现阶段被覆盖或丢失。

**Why this priority**: 直接影响用户对缓存复用的信任度，错误会导致重复计算和结果缺失。

**Independent Test**: 按场景 1→2→3→4 顺序调用接口，验证第 4 次 `ffmpeg.extract_audio` 同步响应 `status=completed` 且包含 `reuse_info.reuse_hit=true` 与历史提取阶段。

**Acceptance Scenarios**:

1. **Given** 已有 `task_id` 存在 `ffmpeg.extract_audio` 成功阶段且后续追加了其他节点阶段， **When** 再次提交同 `task_name` 请求含 callback， **Then** 同步响应返回 `status=completed`、`reuse_info.reuse_hit=true`，且 `stages.ffmpeg.extract_audio` 原样保留。
2. **Given** 复用命中， **When** 查询 `/v1/tasks/{task_id}/status`， **Then** `stages` 同时包含历史提取阶段与新增加的分离阶段，没有被覆盖或移除。

---

### User Story 2 - 等待态复用不重复调度 (Priority: P2)

当同一 `task_id` 下某节点已在执行中（`pending/running`），用户再次发起同节点请求希望系统返回等待态且不产生第二次调度，最终回调沿用首次执行结果。

**Why this priority**: 防止重复占用算力和冲突输出，保障一致性。

**Independent Test**: 启动一次节点请求后立即以相同 `task_id+task_name` 重试，确认同步响应为 `pending` 且 `reuse_info.state=pending`，无新任务排队。

**Acceptance Scenarios**:

1. **Given** Redis 已存在同 `task_id+task_name` 状态为 `pending` 或 `running` 的阶段， **When** 收到带 callback 的重复请求， **Then** 同步响应 `status=pending`、`reuse_info.reuse_hit=true` 且无新的阶段条目追加。
2. **Given** 首次执行完成， **When** 监听回调或查询状态， **Then** 只收到一次最终结果，`stages` 中该节点阶段未重复或覆盖其他节点数据。

---

### User Story 3 - 文档覆盖所有节点的复用规则 (Priority: P3)

文档使用者需要在节点说明中看到复用判定规则、返回示例与字段含义，以便正确接入和排查。

**Why this priority**: 文档清晰度决定外部集成是否正确使用复用特性。

**Independent Test**: 检查 `SINGLE_TASK_API_REFERENCE.md` 各节点小节是否包含复用说明与 `reuse_info` 示例，与实际行为一致。

**Acceptance Scenarios**:

1. **Given** 查看任一单任务节点文档小节， **When** 检索复用相关描述， **Then** 能找到判定条件、命中/等待/未命中返回形态及字段说明。
2. **Given** 对照接口行为执行复用命中与等待用例， **When** 核对文档示例， **Then** 字段与流程与实际响应一致。

---

### Edge Cases

- 重复请求时缓存阶段存在但 `output` 为空或 `status=FAILED`，应视为未命中并按正常流程执行，同时保持其他阶段不受影响。
- 不同节点交错写入同一 `task_id` 时，追加新阶段不得移除或覆盖已有阶段字段（含 `input_params/output/error/duration`）。
- 复用命中时 callback 地址更换：需要使用最新 callback 发送结果，但不可改写历史阶段内容。
- 没有提供 callback 时，复用逻辑仍应生效并在状态查询返回复用结果。

## Clarifications

### Session 2025-12-21
- Q: 是否需要对 `SINGLE_TASK_API_REFERENCE.md` 中所有单任务节点逐一排查并在文档标注复用判定与示例？ → A: 是，需对文档列出的全部单任务节点（ffmpeg/faster_whisper/audio_separator/pyannote_audio/paddleocr/indextts/wservice 等）逐一排查并在节点小节明确复用判定条件、命中/等待/未命中示例与字段。
- Q: pytest 等测试如何执行（宿主机无环境）？ → A: 所有 pytest/验证命令必须在目标容器内执行，先在容器内 `pip install pytest`（如镜像受限需加 `--break-system-packages`），再运行测试。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 系统 MUST 在写入单任务状态时按 `task_id` 累积所有 `task_name` 阶段，追加或更新目标阶段时不得删除或覆盖同一 `task_id` 下的其他阶段字段与 TTL。
- **FR-002**: 系统 MUST 在接收含 callback 的单任务请求时，对所有文档列出的单任务节点（ffmpeg、faster_whisper、audio_separator、pyannote_audio、paddleocr、indextts、wservice 相关节点等）执行 `task_id+task_name` 复用判定：成功阶段且 `output` 非空即直接返回命中结果与 `reuse_info`，同步响应 `status=completed` 且不触发二次调度。
- **FR-003**: 系统 MUST 在复用命中但状态为 `pending/running` 时，返回 `status=pending`、`reuse_info.state=pending`，不重复调度、不新增阶段记录，并保持原阶段后续完成后正常回调。
- **FR-004**: 系统 MUST 在复用未命中（阶段不存在、`output` 为空或 `status=FAILED`）时走常规调度，完成后写入新阶段且保留既有阶段数据，响应与回调携带 `reuse_info.reuse_hit=false`。
- **FR-005**: 文档 MUST 在 `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md` 中更新复用说明，覆盖通用流程与所有节点小节：描述判定条件、命中/等待/未命中时的 `status` 与 `reuse_info` 字段，并示例阶段数据不会被覆盖；每个单任务节点需逐项展示复用判定字段与示例，确保无遗漏。

### Key Entities *(include if feature involves data)*

- **WorkflowContext**: 表示单任务生命周期的数据载体，包含 `workflow_id`、`create_at`、`input_params`、`shared_storage_path`、`stages` 字典及 `error/status`。需求聚焦于 `stages` 累积与查询完整性。
- **Stage Entry**: `stages[task_name]` 对象，包含 `status`、`input_params`、`output`、`error`、`duration`。复用判定依赖该对象的 `status` 与 `output` 完整性，更新时不得影响其他 `task_name` 的阶段。
- **reuse_info（响应/回调字段）**: 在复用命中或等待时返回，包含 `reuse_hit`、`task_name`、`source`、`cached_at`（命中）或 `state=pending`（等待）。用于向调用方声明复用结果来源与当前状态。

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 对文档列出的全部单任务节点执行同一 `task_id+task_name` 的重复调用（包含跨节点先后顺序），命中条件满足时同步响应与回调均返回 `reuse_info.reuse_hit=true` 且不触发新的执行，复用命中率在具备缓存条件的用例中达到 100%。
- **SC-002**: 在包含至少 3 个不同节点的串联调用后，再次请求任一已成功节点，其 `stages` 查询结果始终保留所有历史阶段数据且新增阶段不覆盖旧字段，人工核对不少于 3 组用例均通过。
- **SC-003**: 针对 `pending/running` 状态重复请求的测试中，同一节点仅产生一次实际执行，重复请求同步响应均为 `status=pending` 且 `reuse_info.state=pending`，无重复队列或重复阶段记录。
- **SC-004**: `SINGLE_TASK_API_REFERENCE.md` 显示复用说明与示例覆盖通用流程和每个节点小节，经人工检查节点列表 100% 有复用描述且字段与真实响应一致。 

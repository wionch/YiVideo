# Change: 对齐工作流节点文档与实现行为

## Why
`WORKFLOW_NODES_REFERENCE.md` 中的输入/输出描述与实际节点实现不一致（faster_whisper、wservice、audio_separator 等），导致按文档配置的工作流无法复现或参数缺失。

## What Changes
- 校正 faster_whisper.transcribe_audio 的参数来源优先级和输出字段描述，使其与现有代码一致。
- 补充 wservice.generate_subtitle_files 的必需/可选参数及对上游输出的依赖，明确缺失时的报错路径。
- 更新 audio_separator.separate_vocals 的参数优先级与可覆盖配置说明，反映 `audio_separator_config` 实际支持项。
- 视需要补充跨节点示例/依赖说明，避免单任务/工作流模式歧义。

## Impact
- 受影响文档：`docs/technical/reference/WORKFLOW_NODES_REFERENCE.md`
- 受影响代码理解：`services/workers/faster_whisper_service/app/tasks.py`, `services/workers/wservice/app/tasks.py`, `services/workers/audio_separator_service/app/tasks.py`
- 行为风险：无（文档对齐现状）；如后续选择补充代码输出需另行评估。

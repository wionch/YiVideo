## Conclusions
- 现有 `WORKFLOW_NODES_REFERENCE.md` 描述与实现不一致：`faster_whisper.transcribe_audio` 文档宣称输出/来源包含 `audio_path` 且优先顺序为分离→ffmpeg→参数，但代码先用 `get_param_with_fallback` 覆盖、输出缺少 `audio_path`，字段集不同（仅 `segments_file` 等）。  
- `wservice.generate_subtitle_files` 文档只列 `segments_file/diarization_file` 节点参数，但代码还消费 `audio_duration/language/output_filename`，并在无 `segments_file` 时要求上游提供 `audio_path`，当前 faster_whisper 输出缺少该字段导致文档工作流不可用。  
- `audio_separator.separate_vocals` 文档未提到 `audio_separator_config` 的覆盖字段（quality_mode/model_type/use_vocal_optimization/vocal_optimization_level），且实际优先取 ffmpeg 输出音频，节点参数/输入数据只能在缺省时生效。

## Evidence
- 文档：`docs/technical/reference/WORKFLOW_NODES_REFERENCE.md` (e.g., lines 708-757, 2335-2386, 863-911) 描述的参数/输出与代码不匹配。  
- 代码：  
  - `services/workers/faster_whisper_service/app/tasks.py:441-657` 输出仅含 `segments_file` 等且音频源优先从节点/输入数据获取。  
  - `services/workers/wservice/app/tasks.py:520-594` 需要 `audio_path` 当缺少 `segments_file`，并读取 `audio_duration/language/output_filename`。  
  - `services/workers/audio_separator_service/app/tasks.py:70-189` 先查 ffmpeg 输出，再看 `audio_path/video_path`，并处理 `audio_separator_config` 额外参数。  
- Celery 背景：绑定任务使 `self` 可用并支持重试/回调（/celery/celery docs “Bound tasks”），与当前各节点 `bind=True` 行为一致。

## Open Questions
- 期望的对齐方向：更新文档以反映当前行为，还是调整代码以符合现有文档（会引入行为变更/兼容性风险）？  
- 如果只改文档，是否需要补充 API 示例/依赖矩阵以覆盖单任务模式和上游缺失时的报错路径？  
- 需要同时更新其他引用文档（如 API/guide 文件）吗，或仅限主参考文档？

## Recommended Approach (with trade-offs)
- **首选：文档对齐现状** —— 更新 `WORKFLOW_NODES_REFERENCE.md` 描述输入来源优先级、必需字段与实际输出字段集合。风险低，无行为变更，最快落地；但若现有行为本身不符合产品预期，问题继续存在。  
- **可选：最小代码补位** —— 若希望维持文档体验，可在后续实现中让 `transcribe_audio` 输出 `audio_path`（或 `generate_subtitle_files` 放宽要求），需要进一步需求确认，涉及行为变更和回归测试。

## Affected Files (probable edits)
- `docs/technical/reference/WORKFLOW_NODES_REFERENCE.md`
- 参考/交叉验证：`services/workers/faster_whisper_service/app/tasks.py`, `services/workers/wservice/app/tasks.py`, `services/workers/audio_separator_service/app/tasks.py`

## Tooling Notes
- sequential-thinking completed; serena search used to locate task definitions; context7 pulled Celery bound-task behaviors to confirm bind=True semantics.

# Research

## 结论
- 报错源于 `services/common/subprocess_utils.py` 的 `run_with_popen` 未接受 `stage_name`，调用方将其作为 kwarg 传入，最终透传到 `subprocess.Popen` 触发 `__init__` unexpected keyword argument 错误。
- 受影响调用方至少有：
  - `services/workers/pyannote_audio_service/app/tasks.py` 在 diarization 子进程调用时传 `stage_name="pyannote_audio_subprocess"`（参考行 240 左右）。
  - `services/workers/audio_separator_service/app/model_manager.py` 子进程调用传 `stage_name="audio_separator_subprocess"`（行 90 左右）。
  - `services/workers/ffmpeg_service/app/modules/audio_splitter.py` 多处 `stage_name`（行 112、218 等）。
- 现有日志行为依赖 `stage_name` 作为日志前缀，因此应在 wrapper 内兼容处理，而非要求调用侧删除参数。

## 证据 (serena)
- `services/workers/pyannote_audio_service/app/tasks.py:240` 附近：`run_with_popen(..., stage_name="pyannote_audio_subprocess", ...)`。
- `services/workers/audio_separator_service/app/model_manager.py:84-111`：`run_with_popen` 传 `stage_name`。
- `services/workers/ffmpeg_service/app/modules/audio_splitter.py:104-121, 204-224`：`run_with_popen` 传 `stage_name`。

## context7 记录
- 尝试 `context7 resolve python subprocess` 未得到 Python stdlib 相关条目，可视为无可用第三方库指引。本次变更为内部 wrapper 兼容性修复，不需额外依赖文档。

## 未决问题
- 是否需要为 wrapper 增加对其他自定义参数的白名单或过滤？当前仅发现 `stage_name`。
- 是否需要在日志中保留 `stage_name` 与 `log_prefix` 并存（目前方案是映射为日志前缀）。

## 推荐方案
- 在 `run_with_popen` 增加可选 `stage_name` 参数，若提供则赋值给 `log_prefix`，避免透传给 `subprocess.Popen`。
- 保持其余行为不变，确保调用方无需改动。
- 验证：重跑触发 pyannote diarize 任务（同 n8n 请求），观察不再抛出 unexpected keyword argument，并生成 diarization 输出；可选对 audio_separator/ffmpeg 调用做一次快速 smoke。并观察实时日志仍含 stage 前缀。

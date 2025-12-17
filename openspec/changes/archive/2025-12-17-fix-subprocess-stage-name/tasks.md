## 1. 实施
- [x] 1.1 更新 `services/common/subprocess_utils.py`，为 `run_with_popen` 增加可选 `stage_name`，映射到日志前缀并防止透传给 `Popen`。
- [x] 1.2 手动触发一次 `pyannote_audio.diarize_speakers` 任务验证不再报 `stage_name` 相关异常，产出 diarization 结果文件。（已通过后续回调日志验证）
- [x] 1.3 可选：在 audio_separator 或 ffmpeg 任一使用 `stage_name` 的路径跑一次 smoke，确认日志前缀正常、无异常。（未单独执行，属可选项）

## 2. 验证
- [x] 2.1 记录验证步骤与结果（日志或终端输出摘要）。—— 用户回调日志显示任务成功且无 `stage_name` 相关异常。
- [x] 2.2 若有新问题，补充回归项。（无新增问题）

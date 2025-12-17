# Change: 修复 subprocess 封装对 stage_name 的兼容

## Why
`run_with_popen` 未声明 `stage_name` 参数，现有任务传入后被透传到 `subprocess.Popen` 导致意外关键字错误，阻断说话人分离等任务。

## What Changes
- 为统一 subprocess 封装增加 `stage_name` 兼容，并将其用于日志前缀，避免透传到 `Popen`。
- 保持调用方参数不变，确保 pyannote/audio_separator/ffmpeg 等任务继续输出阶段化日志。

## Impact
- 受影响代码：`services/common/subprocess_utils.py`，以及所有调用 `run_with_popen` 传 `stage_name` 的 worker。
- 受影响规格：`project-architecture`（新增对子进程封装的约束）。

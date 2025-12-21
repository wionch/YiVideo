## ADDED Requirements

### Requirement: 统一子进程封装支持阶段化日志
统一子进程执行封装 MUST 接受阶段化日志参数并避免将非 `subprocess.Popen` 支持的字段透传，以保证现有任务的阶段日志可用且执行不会因意外关键字失败。

#### Scenario: 带 stage_name 的子进程执行
- **WHEN** 任一 worker 通过 `services.common.subprocess_utils.run_with_popen` 执行命令并传入 `stage_name`
- **THEN** 子进程正常启动且不会因未知关键字报错
- **AND** 日志前缀使用传入的阶段名便于溯源

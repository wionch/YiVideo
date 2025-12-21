# project-architecture Specification

## Purpose
TBD - created by archiving change refactor-redundant-utilities. Update Purpose after archive.
## Requirements
### Requirement: 集中式配置管理

所有微服务 MUST 使用集中式配置加载器，以确保持一致的行为和热重载能力。

#### Scenario: 服务加载配置
- **WHEN** 服务 worker 启动或需要配置值时
- **THEN** 它必须调用 `services.common.config_loader.get_config()`
- **AND** 它不得实现自己的配置文件读取逻辑

### Requirement: 统一字幕处理

所有字幕解析、生成和修改逻辑 MUST 由通用字幕模块处理。

#### Scenario: 写入 SRT 文件
- **WHEN** 任务需要生成 SRT 文件时
- **THEN** 它必须使用 `services.common.subtitle.subtitle_parser`
- **AND** 它不得使用临时的字符串格式化函数

#### Scenario: 解析字幕文件
- **WHEN** 任务需要解析 SRT 或 JSON 字幕文件时
- **THEN** 它必须使用 `services.common.subtitle.subtitle_parser`

### Requirement: 统一子进程封装支持阶段化日志
统一子进程执行封装 MUST 接受阶段化日志参数并避免将非 `subprocess.Popen` 支持的字段透传，以保证现有任务的阶段日志可用且执行不会因意外关键字失败。

#### Scenario: 带 stage_name 的子进程执行
- **WHEN** 任一 worker 通过 `services.common.subprocess_utils.run_with_popen` 执行命令并传入 `stage_name`
- **THEN** 子进程正常启动且不会因未知关键字报错
- **AND** 日志前缀使用传入的阶段名便于溯源

### Requirement: MinIO 上传行为可配置
系统 SHALL 通过集中式配置控制自动上传到 MinIO 的行为，保持默认向后兼容并允许显式关闭。

#### Scenario: 关闭自动上传
- **WHEN** `config.yml` 设置 `core.auto_upload_to_minio=false`
- **THEN** `services/common/state_manager.update_workflow_state` SHALL 跳过 `_upload_files_to_minio`，保持各阶段输出为本地路径
- **AND** 文档中远程 URL 字段必须标注为“可选且仅在上传开启时出现”

#### Scenario: 开启自动上传（默认）
- **WHEN** `core.auto_upload_to_minio=true`（默认值）
- **THEN** state_manager SHALL 上传工作流输出并写入对应 `*_minio_url`/`minio_files` 字段，同时保留本地字段值不被覆盖
- **AND** 节点级 upload_* 参数（如存在）仍需为 true 才生成对应远程字段

### Requirement: 上传后保留本地文件并通过显式接口清理
系统 SHALL 在上传阶段产物到 MinIO 后保留本地 `/share` 内的文件或目录，删除动作必须通过显式清理接口触发。

#### Scenario: 上传成功后保留本地副本
- **WHEN** 任一 worker 将阶段输出（文件或目录）上传到 MinIO（无论全局 `core.auto_upload_to_minio` 或节点级 upload_* 开启）
- **THEN** 阶段输出中的本地路径必须继续存在且保持可读
- **AND** 上传成功不得触发自动删除该本地路径

#### Scenario: 由显式删除请求触发清理
- **WHEN** 需要清理工作流产物目录
- **THEN** 平台 SHALL 通过 `DELETE /v1/files/directories?directory_path=<path>` 触发删除
- **AND** 不得依赖任务内部的上传后自动清理开关

#### Scenario: 后续任务复用本地产物
- **WHEN** 后续任务或调试流程访问已上传阶段的本地路径
- **THEN** 该路径必须存在直至被显式清理，不得因为上传成功被提前移除


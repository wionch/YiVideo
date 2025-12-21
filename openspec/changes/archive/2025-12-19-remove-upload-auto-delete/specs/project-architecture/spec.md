## ADDED Requirements
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

## ADDED Requirements
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

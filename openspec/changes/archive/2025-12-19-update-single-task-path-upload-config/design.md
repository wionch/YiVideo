## Context
- 文档存在“只展示本地”或“只展示 MinIO URL”的节点示例，而任务实现与 state_manager 会决定是否产生远程 URL。
- state_manager 在每次 `update_workflow_state` 时无条件执行 `_upload_files_to_minio`，config.yml 没有开关，无法显式关闭上传。
- 需要以最小改动引入可配置的上传行为，并在文档中统一双轨（本地+远程）输出格式。

## Goals / Non-Goals
- Goals:
  - 新增全局配置控制自动上传到 MinIO，默认保持当前自动上传行为。
  - 更新单任务文档输出示例为“本地路径 + 可选远程 URL”，并标注该远程字段受全局开关和节点 upload_* 参数共同控制。
  - 规格层要求文档体现上述双轨输出与配置依赖。
- Non-Goals:
  - 不引入新的存储后端或回调机制。
  - 不改动各任务的业务输入输出结构（除上传开关判断）。
  - 不新增节点级上传参数（已有 upload_* 参数保持不变）。

## Decisions
- 全局上传开关：在 `config.yml` 下新增 `core.auto_upload_to_minio`（bool，默认 `true`），state_manager 读取后决定是否执行 `_upload_files_to_minio`。开关为 false 时仅保留本地路径，不尝试上传。
- 保留本地字段，远程使用专用字段：state_manager 上传成功后不覆盖原字段，而是追加 `*_minio_url` 或 `minio_files`（目录/多文件）等远程字段，确保字段名与值语义一致。
- 文档双轨格式：每个节点的输出示例都包含本地路径字段；仅当全局开关为 true 且节点 upload_* 参数为 true（若存在）时，文档展示对应的 `*_minio_url`/`minio_files` 可选字段，并明确为“可选输出”。
- 对无上传参数的节点（如 `ffmpeg.extract_audio`、`ffmpeg.split_audio_segments`、`faster_whisper.transcribe_audio`、`wservice.correct_subtitles`），远程 URL 仅在全局开关启用时出现，文档需要说明来源（state_manager 自动上传）。

## Risks / Trade-offs
- 关闭自动上传可能影响依赖 MinIO URL 的下游调用；默认保持 true，并在文档中突出开关行为减少误用。
- state_manager 读取 config 需保证性能，可通过一次性加载配置避免频繁 IO。
- 追加远程字段可能需要消费方适配，不再能依赖原字段自动切换为 URL。

## Migration Plan
1) 在 config.yml 添加 `core.auto_upload_to_minio` 默认 true，state_manager 读取该值后包装 `_upload_files_to_minio` 调用。
2) state_manager 上传时保留本地字段，远程写入专用字段。
3) 更新单任务文档所有节点输出示例，加入“本地+可选远程”描述并提及开关/字段命名。
4) 更新 `single-task-api-docs` 与 `project-architecture` 规格，覆盖双轨展示、字段命名与配置要求。
5) `openspec validate <change-id> --strict`，必要时补充 docs/spec 行文检查。

## Open Questions
- 是否需要未来的节点级覆盖开关（高优先级 per-node toggle）？当前决定不做，若有需求再追加 proposal。

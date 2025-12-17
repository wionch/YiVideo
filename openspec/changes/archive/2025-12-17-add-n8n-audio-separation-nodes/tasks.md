## 1. Implementation

- [x] 1.1 在 YiVideo 侧补齐 `audio_separator.separate_vocals` 输出：统一为“vocal_audio + all_audio_files”结构，兼容不同模型返回的多轨结果。
- [x] 1.2 对齐单任务模式参数读取：支持从 `input_data.audio_separator_config`（以及必要时 `input_data.model_name/quality_mode`）读取模型参数，并将优先级定义为 `node_params` > `input_data` > `config.yml`，确保可固定且回传 `UVR-MDX-NET-Inst_HQ_5.onnx`。
- [x] 1.3 扩展 API Gateway `_extract_file_paths` 覆盖 `vocal_audio`/`all_audio_files`，确保 callback `minio_files` 包含分离产物 URL。
- [x] 1.4 使用 n8n MCP 更新工作流 `YiVideoNodes`（id: `ijOqn9Dh0EX32tN5`），新增 audio_separator 请求节点与对应 Wait 节点，并配置唯一 `webhookSuffix`。（最终由人工在 n8n 编辑器完成配置并验证回调）
- [x] 1.5 （可选）新增一个 Code/Set 节点：从 callback payload 提取并输出 `vocals_url` 与 `all_audio_urls`。（同上，已在 n8n 中手动完成并确认输出）
- [x] 1.6 更新节点参考文档 `docs/technical/reference/WORKFLOW_NODES_REFERENCE.md`：单任务输入参数与输出字段与实现保持一致，并标注固定模型要求。
- [x] 1.7 运行与验证：
  - `openspec validate add-n8n-audio-separation-nodes --strict`
  - n8n 节点执行验证：**已完成**（手动在 n8n 中配置 audio_separator 节点并触发单步任务，确认回调包含 `vocal_audio_minio_url` 与 `all_audio_minio_urls`）

## 2. Notes / Dependencies

- 确认 `audio_separator_service` 容器内可访问 `UVR-MDX-NET-Inst_HQ_5.onnx`（模型卷映射或缓存策略）。
- 确认 n8n 的 `resumeUrl` 对 API Gateway 可达且通过 callback URL 校验（非 localhost/127.0.0.1/.local）。

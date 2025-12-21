## ADDED Requirements

### Requirement: 单任务模式支持固定 MDX 模型

音频分离服务 SHALL 支持在单任务模式（`POST /v1/tasks`）中通过 `input_data` 显式指定并固定使用 MDX 模型文件名。

#### Scenario: 使用 input_data 指定 UVR-MDX-NET-Inst_HQ_5.onnx

- **GIVEN** 用户通过单任务接口调用 `audio_separator.separate_vocals`
- **WHEN** 请求 `input_data.audio_separator_config.model_name="UVR-MDX-NET-Inst_HQ_5.onnx"`
- **THEN** 任务 MUST 使用该模型进行分离
- **AND** 输出中 MUST 能体现实际使用模型（例如 `model_used="UVR-MDX-NET-Inst_HQ_5.onnx"`）
- **AND** 若 `config.yml` 中存在不同默认值，系统 SHALL 仍以该请求参数为准

#### Scenario: 请求参数优先级覆盖 config 默认值

- **GIVEN** `config.yml.audio_separator_service` 设置了默认 `model_type` 或 `default_model`
- **WHEN** 单任务请求或 node_params 提供 `audio_separator_config`
- **THEN** 系统 MUST 按以下优先级解析模型：`node_params.audio_separator_config` > `input_data.audio_separator_config` > `config.yml` 默认值
- **AND** 最终 `model_used` MUST 反映该优先级的生效结果

### Requirement: 输出同时包含人声与全部音轨

音频分离服务 SHALL 在输出中同时提供“人声”与“全部音轨列表”两种结构，以兼容不同模型拆分出的多轨结果。

#### Scenario: 输出包含 vocal_audio 与 all_audio_files

- **GIVEN** 分离任务执行成功
- **WHEN** 任务返回 `stages.audio_separator.separate_vocals.output`
- **THEN** 输出 MUST 包含：
  - `vocal_audio`（人声文件路径）
  - `all_audio_files`（数组，列出本次分离产生的所有音频文件路径，顺序与模型输出保持一致）
- **AND** `all_audio_files` SHOULD 始终包含 `vocal_audio` 对应的路径

#### Scenario: 输出 MinIO URL 结构与本地结构一致

- **GIVEN** 已将分离结果上传到 MinIO
- **WHEN** 返回任务输出
- **THEN** 输出 MUST 额外提供：
  - `vocal_audio_minio_url`（人声文件的 MinIO 下载 URL）
  - `all_audio_minio_urls`（数组，列出所有音轨的 MinIO 下载 URL；与 `all_audio_files` 一一对应）

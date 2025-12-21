# audio-separator-service Specification

## Purpose
TBD - created by archiving change unify-parameter-management. Update Purpose after archive.
## Requirements
### Requirement: 统一音频源参数获取逻辑

音频分离任务**SHALL**使用统一的参数获取机制，通过 `get_param_with_fallback` 函数实现多级参数回退。

#### 当前实现（存在问题）
音频分离任务在 `audio_separator_service/app/tasks.py` 中使用手动参数回退逻辑（第118-126行），存在以下问题：
- 代码重复，与其他服务不一致
- 不支持完整的单任务模式特性
- 维护复杂，难以扩展

#### 期望行为（统一后）
```python
# 统一的参数获取方式
audio_path = get_param_with_fallback(
    "audio_path", 
    resolved_params, 
    workflow_context,
    fallback_from_input_data=True,
    fallback_from_stage="ffmpeg.extract_audio"
)
```

#### 保持不变的行为
- 智能音频源选择的优先级逻辑：人声音频 → 默认音频 → 参数传入
- 输入文件验证和下载逻辑
- 音频分离核心功能
- 输出数据结构和格式

#### Scenario: 单任务模式参数获取
- **WHEN** 通过 `/v1/tasks` 接口调用 `audio_separator.separate_vocals`
- **AND** 提供 `input_data.audio_path` 或 `input_data.video_path`
- **THEN** 系统应正确获取音频文件路径并执行分离
- **验证点**: 支持动态引用 `${{...}}` 语法

#### Scenario: 工作流模式参数回退
- **WHEN** 在工作流中调用 `audio_separator.separate_vocals`
- **AND** 未在节点参数中明确提供 `audio_path`
- **THEN** 系统应回退到上游节点 `ffmpeg.extract_audio` 的输出
- **验证点**: 智能源选择逻辑保持完全一致

#### Scenario: 错误处理和日志
- **WHEN** 参数获取失败或文件不存在
- **THEN** 应提供清晰的错误信息，包含音频源选择的调试信息
- **验证点**: 日志应记录实际使用的音频源和路径

### Requirement: 兼容性保证

音频分离服务**MUST**保持与现有工作流配置的完全兼容性。

#### 兼容性要求
- ✅ 现有工作流配置无需修改
- ✅ API调用方式保持一致
- ✅ 智能音频源选择行为不变
- ✅ 输出数据格式完全兼容

#### Scenario: 现有工作流兼容性
- **WHEN** 使用现有的工作流配置调用音频分离任务
- **THEN** 系统应产生与重构前完全相同的结果
- **验证点**: 输出文件路径、内容和元数据完全一致

#### Scenario: 错误情况兼容性
- **WHEN** 遇到文件不存在或权限错误时
- **THEN** 错误信息和处理方式与重构前相同
- **验证点**: 错误代码、消息和处理逻辑保持一致

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


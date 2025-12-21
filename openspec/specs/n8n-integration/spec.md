# n8n-integration Specification

## Purpose
TBD - created by archiving change create-n8n-asr-subtitle-workflow. Update Purpose after archive.
## Requirements
### Requirement: ASR字幕提取工作流

系统 SHALL 提供一个 n8n 工作流模板，通过音频转录方式从视频中提取字幕并生成 JSON 格式字幕文件。

#### Scenario: 完整ASR字幕提取流程

- **GIVEN** 用户有一个存储在 MinIO 中的视频文件
- **WHEN** 用户在 n8n 中手动触发 "YiVideo-ASR字幕提取" 工作流
- **THEN** 系统依次执行以下步骤：
  1. 调用 `ffmpeg.extract_audio` 从视频提取音频
  2. 调用 `faster_whisper.transcribe_audio` 进行语音转录
  3. 调用 `wservice.generate_subtitle_files` 生成字幕文件
- **AND** 每个步骤通过 callback 机制异步等待完成
- **AND** 最终输出包含 subtitle_path、json_path、speaker_srt_path

#### Scenario: 任务间数据传递

- **GIVEN** 音频提取任务已完成并返回 audio_path
- **WHEN** 语音转录任务被触发
- **THEN** 任务自动从上一步回调数据中获取 audio_path 作为输入
- **AND** 转录完成后返回 segments_file 供下一步使用

#### Scenario: 异步回调等待

- **GIVEN** 一个 YiVideo 单任务正在执行
- **WHEN** 任务完成（成功或失败）
- **THEN** YiVideo 通过 callback URL 通知 n8n
- **AND** n8n Wait 节点恢复执行并继续工作流

### Requirement: n8n工作流配置规范

n8n 工作流 SHALL 遵循以下配置规范以确保与 YiVideo 系统的正确集成。

#### Scenario: HTTP请求节点配置

- **GIVEN** 需要调用 YiVideo 单任务 API
- **WHEN** 配置 n8n httpRequest 节点
- **THEN** 节点配置必须包含：
  - method: "POST"
  - url: "http://api_gateway/v1/tasks"
  - sendBody: true
  - specifyBody: "json"
  - jsonBody: 包含 task_name, task_id, callback, input_data

#### Scenario: Wait节点配置

- **GIVEN** 需要等待 YiVideo 任务完成回调
- **WHEN** 配置 n8n wait 节点
- **THEN** 节点配置必须包含：
  - resume: "webhook"
  - httpMethod: "POST"
  - options.webhookSuffix: 唯一的步骤标识符

### Requirement: Pyannote 说话人分离节点

系统 SHALL 在 n8n 工作流中提供调用 `pyannote_audio.diarize_speakers` 的节点模板，并通过 webhook Wait 节点等待回调。

#### Scenario: 配置 Pyannote 请求节点

- **GIVEN** 需要在 n8n 发起说话人分离任务
- **WHEN** 配置 HTTP Request 节点调用 YiVideo 单任务 API
- **THEN** 节点配置必须包含：
  - method: "POST"
  - url: "http://api_gateway/v1/tasks"
  - sendBody: true, specifyBody: "json"
  - jsonBody: 包含 task_name="pyannote_audio.diarize_speakers", task_id、callback（指向 Wait 节点的 resumeUrl 路径）、input_data.audio_path 示例（MinIO URL）

#### Scenario: 配置 Pyannote Wait 节点

- **GIVEN** 需要等待 `pyannote_audio.diarize_speakers` 的回调
- **WHEN** 配置 n8n Wait 节点
- **THEN** 节点配置必须包含：
  - resume: "webhook"
  - httpMethod: "POST"
  - options.webhookSuffix: 唯一的步骤标识符
  - 与请求节点通过主线连接，确保回调命中该 Wait 节点

### Requirement: Audio Separator 人声/多轨分离节点（固定 UVR-MDX-NET-Inst_HQ_5.onnx）

系统 SHALL 在 n8n 工作流 `YiVideoNodes` 中提供调用 `audio_separator.separate_vocals` 的节点模板，用于从输入音频中获得“人声”以及“全部分离音轨（all）”两类产物，并强制使用 `UVR-MDX-NET-Inst_HQ_5.onnx` 模型。

#### Scenario: 配置 Audio Separator 请求节点

- **GIVEN** 需要在 n8n 发起音频分离任务
- **WHEN** 配置 HTTP Request 节点调用 YiVideo 单任务 API
- **THEN** 节点配置必须包含：
  - method: "POST"
  - url: "http://api_gateway/v1/tasks"
  - sendBody: true, specifyBody: "json"
  - jsonBody: 包含
    - task_name="audio_separator.separate_vocals"
    - task_id（占位符/变量）
    - callback（指向 Wait 节点的 resumeUrl 路径）
    - input_data.audio_path（示例：MinIO URL）
    - input_data.audio_separator_config.model_name="UVR-MDX-NET-Inst_HQ_5.onnx"

#### Scenario: 配置 Audio Separator Wait 节点

- **GIVEN** 需要等待 `audio_separator.separate_vocals` 的回调
- **WHEN** 配置 n8n Wait 节点
- **THEN** 节点配置必须包含：
  - resume: "webhook"
  - httpMethod: "POST"
  - options.webhookSuffix: 唯一的步骤标识符（例如 "t_audio_sep"）
  - 与请求节点通过主线连接，确保回调命中该 Wait 节点

#### Scenario: 获取人声与全部音轨的输出 URL

- **GIVEN** YiVideo 已通过 callback 返回 `result` 与 `minio_files`
- **WHEN** n8n 需要将分离结果作为后续节点输入
- **THEN** 工作流应能得到两个字段：
  - `vocals_url`（人声音频下载 URL）
  - `all_audio_urls`（数组，包含该次分离产生的所有音轨下载 URL，至少含一条与 `vocals_url` 相同）
- **AND** 这两个字段来源 SHOULD 优先使用 callback 的 `minio_files`（避免依赖 `/share` 挂载）

### Requirement: 视频到字幕提取的完整n8n工作流

系统 SHALL 提供一个完整的 n8n 工作流模板，实现从视频文件到字幕提取的自动化处理流程。

#### Scenario: 完整视频字幕提取工作流

- **GIVEN** 用户有一个存储在 MinIO 中的视频文件（示例：http://host.docker.internal:9000/yivideo/task_id/223.mp4）
- **WHEN** 用户在 n8n 中手动触发 "YiVideo-视频字幕提取工作流"
- **THEN** 系统依次执行以下步骤：
  1. 设置固定参数（task_id、video_path）
  2. 调用 `ffmpeg.extract_audio` 从视频提取音频
  3. 调用 `audio_separator.separate_vocals` 分离人声和背景声（使用 UVR-MDX-NET-Inst_HQ_5.onnx 模型）
  4. 调用 `faster_whisper.transcribe_audio` 转录人声音频为文本
  5. 调用 `pyannote_audio.diarize_speakers` 识别说话人
- **AND** 每个步骤通过 callback 机制异步等待完成
- **AND** 节点间使用 `{{$('节点名').stages['步骤名'].output.字段名}}` 格式传递数据

#### Scenario: 参数设置和初始化

- **GIVEN** 工作流开始执行
- **WHEN** 配置 Set 节点设置初始参数
- **THEN** 节点必须设置以下固定值：
  - task_id: "video_subtitle_task_001"
  - video_path: "http://host.docker.internal:9000/yivideo/task_id/223.mp4"

#### Scenario: 音频提取配置

- **GIVEN** 需要从视频提取音频
- **WHEN** 配置 HTTP Request 节点调用 ffmpeg.extract_audio
- **THEN** 节点配置必须包含：
  - method: "POST"
  - url: "http://api_gateway/v1/tasks"
  - jsonBody:
    ```
    {
      "task_name": "ffmpeg.extract_audio",
      "task_id": "{{$('Edit Fields').item.json.task_id}}",
      "callback": "{{ $execution.resumeUrl }}/t_extract_audio",
      "input_data": {
        "video_path": "{{$('Edit Fields').item.json.video_path}}"
      }
    }
    ```
- **AND** 后续 Wait 节点配置 webhookSuffix 为 "t_extract_audio"

#### Scenario: 人声分离配置

- **GIVEN** 音频提取完成，需要分离人声
- **WHEN** 配置 HTTP Request 节点调用 audio_separator.separate_vocals
- **THEN** 节点配置必须包含：
  - method: "POST"
  - url: "http://api_gateway/v1/tasks"
  - jsonBody:
    ```
    {
      "task_name": "audio_separator.separate_vocals",
      "task_id": "{{$('Edit Fields').item.json.task_id}}",
      "callback": "{{ $execution.resumeUrl }}/t_audio_sep",
      "input_data": {
        "audio_path": "{{$('Wait:音频提取完成').item.json.body.result.stages['ffmpeg.extract_audio'].output.audio_path_minio_url}}",
        "audio_separator_config": {
          "model_name": "UVR-MDX-NET-Inst_HQ_5.onnx"
        }
      }
    }
    ```
- **AND** 使用 audio_path_minio_url 优先，如不存在则使用 audio_path

#### Scenario: 语音转录配置

- **GIVEN** 人声分离完成，需要转录语音
- **WHEN** 配置 HTTP Request 节点调用 faster_whisper.transcribe_audio
- **THEN** 节点配置必须包含：
  - method: "POST"
  - url: "http://api_gateway/v1/tasks"
  - jsonBody:
    ```
    {
      "task_name": "faster_whisper.transcribe_audio",
      "task_id": "{{$('Edit Fields').item.json.task_id}}",
      "callback": "{{ $execution.resumeUrl }}/t_whisper",
      "input_data": {
        "audio_path": "{{$('Wait:人声分离完成').item.json.body.minio_files[0].url}}"
      }
    }
    ```
- **AND** 从 minio_files 数组中获取人声音频 URL（第一个文件通常是Vocals）

#### Scenario: 说话人识别配置

- **GIVEN** 语音转录完成，需要识别说话人
- **WHEN** 配置 HTTP Request 节点调用 pyannote_audio.diarize_speakers
- **THEN** 节点配置必须包含：
  - method: "POST"
  - url: "http://api_gateway/v1/tasks"
  - jsonBody:
    ```
    {
      "task_name": "pyannote_audio.diarize_speakers",
      "task_id": "{{$('Edit Fields').item.json.task_id}}",
      "callback": "{{ $execution.resumeUrl }}/t_pyannote",
      "input_data": {
        "audio_path": "{{$('Wait:人声分离完成').item.json.body.minio_files[0].url}}"
      }
    }
    ```
- **AND** 使用与人声转录相同的音频源进行说话人识别

#### Scenario: 数据传递验证

- **GIVEN** 工作流执行过程中
- **WHEN** 验证节点间数据传递
- **THEN** 每个节点的输出必须包含：
  - task_id 保持一致
  - 正确的阶段结果在 stages 对象中
  - minio_files 数组包含输出文件 URL
- **AND** 下一个节点能够正确引用上一个节点的输出

### Requirement: 视频到字幕提取的n8n工作流模板
系统SHALL提供一个预配置的n8n工作流模板，实现从视频输入到字幕输出的完整处理流程。

#### Scenario: 工作流创建
- **WHEN** 用户通过n8n MCP工具请求创建视频到字幕工作流
- **THEN** 系统创建包含5个核心节点的工作流：参数设置→音频提取→人声分离→语音转录→说话人识别

#### Scenario: 数据传递验证
- **WHEN** 工作流执行时
- **THEN** 每个节点的输出正确传递给下一个节点作为输入

#### Scenario: 任务ID一致性
- **WHEN** 工作流中的多个YiVideo任务被调用
- **THEN** 所有任务使用统一的task_id参数


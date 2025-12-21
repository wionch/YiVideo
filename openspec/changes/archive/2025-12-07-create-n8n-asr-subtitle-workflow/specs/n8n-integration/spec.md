## ADDED Requirements

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

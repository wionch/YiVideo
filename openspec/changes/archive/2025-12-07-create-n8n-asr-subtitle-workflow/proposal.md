# Change: 创建 n8n ASR字幕提取工作流

## Why

用户需要通过 n8n 工作流平台与 YiVideo 系统集成，实现视频音频转录并生成 JSON 格式字幕文件的自动化流程。当前系统已具备完整的单任务 API，但缺少现成的 n8n 工作流模板来演示和简化这一常见用例。

## What Changes

### 1. 代码变更：增强 wservice.generate_subtitle_files 单任务模式支持

修改 `services/workers/wservice/app/tasks.py` 中的 `generate_subtitle_files` 函数：

- **新增 input_data 参数支持**：
  - `segments_file`: 转录数据文件路径（JSON格式，支持MinIO URL）
  - `audio_duration`: 音频时长（可选）
  - `language`: 语言代码（可选）
  - `output_filename`: 输出文件名前缀（可选）

- **新增 JSON 格式字幕输出**：
  - 始终生成 `{filename}_subtitle.json` 文件
  - 输出中增加 `json_path` 字段

- **智能参数获取逻辑**：
  - 优先从 `input_data.segments_file` 获取（单任务模式）
  - 回退到 `faster_whisper.transcribe_audio` 阶段输出（工作流模式）

### 2. 创建 n8n 工作流

- 创建一个新的 n8n 工作流，命名为 "YiVideo-ASR字幕提取"
- 工作流通过调用 YiVideo 单任务 API (`/v1/tasks`) 实现以下处理链：
  1. `ffmpeg.extract_audio` - 从视频提取音频
  2. `faster_whisper.transcribe_audio` - 语音转录
  3. `wservice.generate_subtitle_files` - 生成字幕文件（JSON/SRT格式）
- 使用 n8n 的 Wait 节点配合 callback 机制实现异步任务等待
- 工作流输出包含：subtitle_path (SRT格式)、json_path (JSON格式)

## Impact

- Affected specs: wservice 服务规格（新增单任务模式支持）
- Affected code: `services/workers/wservice/app/tasks.py`
- External systems: n8n 工作流平台

## Technical Approach

### 通信模式（参考现有 YiVideoNodes 工作流）

1. **HTTP Request 节点**: 调用 `http://api_gateway/v1/tasks` 创建任务
2. **Wait 节点**: 使用 webhook 模式等待任务完成回调
3. **Callback URL**: 使用 `{{ $execution.resumeUrl }}/stepN` 格式

### 数据流

```
手动触发
    │
    ▼
┌─────────────────────────────────┐
│ 1. ffmpeg.extract_audio        │
│    input: video_path (MinIO URL)│
│    output: audio_path          │
└─────────────────────────────────┘
    │ callback
    ▼
┌─────────────────────────────────┐
│ 2. faster_whisper.transcribe   │
│    input: audio_path           │
│    output: segments_file       │
└─────────────────────────────────┘
    │ callback
    ▼
┌─────────────────────────────────┐
│ 3. wservice.generate_subtitle  │
│    input: segments_file        │
│    output: subtitle files      │
└─────────────────────────────────┘
    │ callback
    ▼
输出结果 (JSON/SRT路径)
```

### n8n 节点配置

| 节点类型 | 名称 | 用途 |
|---------|------|------|
| manualTrigger | 手动触发 | 工作流入口 |
| httpRequest | 提取音频 | 调用 ffmpeg.extract_audio |
| wait | 等待音频提取 | 异步等待回调 |
| httpRequest | 语音转录 | 调用 faster_whisper.transcribe_audio |
| wait | 等待转录完成 | 异步等待回调 |
| httpRequest | 生成字幕文件 | 调用 wservice.generate_subtitle_files |
| wait | 等待字幕生成 | 异步等待回调 |
| set | 输出结果 | 格式化最终输出 |

## Out of Scope

- 不修改 YiVideo 系统代码
- 不创建新的 API 端点
- 不涉及 OCR 字幕提取流程（这是 ASR 方式）

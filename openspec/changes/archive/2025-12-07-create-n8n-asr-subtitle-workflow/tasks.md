# Tasks: 创建 n8n ASR字幕提取工作流

## 1. 代码变更

- [x] 1.1 修改 wservice.generate_subtitle_files 支持单任务模式 input_data 参数
- [x] 1.2 添加 segments_file 参数支持（支持MinIO URL下载）
- [x] 1.3 添加 JSON 格式字幕文件输出（json_path）
- [x] 1.4 验证代码语法正确

## 2. 准备工作

- [x] 2.1 确认 n8n 服务可访问 (http://host.docker.internal:5678)
- [x] 2.2 确认 YiVideo API Gateway 可访问 (http://api_gateway)
- [x] 2.3 确认 MinIO 服务可访问 (http://host.docker.internal:9000)

## 3. 创建 n8n 工作流

- [x] 3.1 使用 n8n API 创建工作流 "YiVideo-ASR字幕提取"
- [x] 3.2 配置手动触发节点
- [x] 3.3 配置音频提取节点 (ffmpeg.extract_audio)
- [x] 3.4 配置音频提取等待节点 (Wait with webhook)
- [x] 3.5 配置语音转录节点 (faster_whisper.transcribe_audio)
- [x] 3.6 配置转录等待节点 (Wait with webhook)
- [x] 3.7 配置字幕生成节点 (wservice.generate_subtitle_files)
- [x] 3.8 配置字幕生成等待节点 (Wait with webhook)
- [x] 3.9 配置输出结果节点 (Set node)
- [x] 3.10 配置节点连接关系

## 4. 验证

- [x] 4.1 验证工作流创建成功
- [x] 4.2 验证工作流结构正确
- [x] 4.3 添加 "yivideo" 标签

## 实现结果

### 工作流信息

- **工作流名称**: YiVideo-ASR字幕提取
- **工作流ID**: `bi7YX7v8dOnU9UX4`
- **标签**: yivideo
- **状态**: inactive (需要手动激活)

### 工作流结构

```
手动触发 → 提取音频 → 等待音频提取 → 语音转录 → 等待转录完成 → 生成字幕文件 → 等待字幕生成 → 输出结果
```

### 使用说明

1. 在 n8n 中打开工作流 "YiVideo-ASR字幕提取"
2. 修改 "提取音频" 节点中的 `video_path` 为实际的视频文件 MinIO URL
3. 手动触发工作流执行
4. 最终输出包含:
   - `subtitle_path`: SRT格式字幕文件路径
   - `json_path`: JSON格式字幕文件路径

### 代码变更文件

- `services/workers/wservice/app/tasks.py`: 增强 `generate_subtitle_files` 支持单任务模式

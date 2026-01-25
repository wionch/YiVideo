# YiVideo AI 字幕优化功能技术说明文档

## 文档版本

- **版本**: v2.0
- **最后更新**: 2026-01-24
- **维护者**: YiVideo 开发团队

---

## 目录

1. [概述](#概述)
2. [核心功能](#核心功能)
3. [技术架构](#技术架构)
4. [工作流程](#工作流程)
5. [API 接口](#api-接口)
6. [配置参数](#配置参数)
7. [AI 提供商支持](#ai-提供商支持)
8. [错误处理](#错误处理)
9. [使用示例](#使用示例)
10. [最佳实践](#最佳实践)
11. [故障排查](#故障排查)

---

## 概述

### 功能定位

AI 字幕优化功能用于对 ASR 生成的字幕进行**纯文本纠错**，并在本地将优化后的文本**映射回原始词级时间戳**。该能力拆分为两个独立节点：

- `wservice.ai_optimize_text`：AI 纯文本纠错
- `wservice.rebuild_subtitle_with_words`：本地词级重构

### 设计原则

- **AI 仅做全文纠错**，输入/输出均为纯文本
- **本地仅做词级重构**，时间戳不变
- 节点**可独立调用**，也可在工作流中串联使用

---

## 核心功能

### 1. AI 纯文本纠错

- 修正错别字、标点、大小写、空格与格式问题
- 禁止增删内容、语序重排、合并/拆分句子
- 输出为优化后的完整正文文本

### 2. 词级时间戳重构

- 以 `segments[].words` 为对齐基准，仅替换 `word` 文本
- 保持 words **数量、顺序、start/end 不变**
- 重建 `segments[].text` 与 `words[].word`

---

## 技术架构

```
API /v1/tasks
   ↓
wservice.ai_optimize_text (纯文本纠错)
   ↓
wservice.rebuild_subtitle_with_words (词级重构)
```

关键组件：

- `SubtitleExtractor`：读取 `segments_file` 并合并全文
- `PromptLoader`：加载系统提示词（支持 override）
- `AIProviderFactory`：选择模型提供商
- `WordAligner`：词级对齐并回填

---

## 工作流程

### 独立节点使用

- `wservice.ai_optimize_text`：输入 `segments_file`，输出 `optimized_text` 与文件
- `wservice.rebuild_subtitle_with_words`：输入 `segments_file` + `optimized_text/optimized_text_file`，输出重建后的 segments

### 串联流程（推荐）

```
faster_whisper.transcribe_audio
  → wservice.ai_optimize_text
  → wservice.rebuild_subtitle_with_words
  → wservice.generate_subtitle_files (可选)
```

---

## API 接口

通过 `/v1/tasks` 调用。完整请求与响应示例请参考：
`docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`

---

## 配置参数

### wservice.ai_optimize_text（input_data）

| 参数 | 类型 | 必需 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `segments_file` | string | 是 | - | 转录 JSON（含 segments/words） |
| `provider` | string | 否 | deepseek | AI 提供商 |
| `timeout` | integer | 否 | 300 | 超时时间（秒） |
| `max_retries` | integer | 否 | 3 | 最大重试次数 |
| `system_prompt_override` | string | 否 | - | 覆盖系统提示词路径 |

说明：系统提示词默认读取 `config/system_prompt/subtitle_optimization.md`。

### wservice.rebuild_subtitle_with_words（input_data）

| 参数 | 类型 | 必需 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `segments_file` | string | 是 | - | 转录 JSON（含 words） |
| `optimized_text` | string | 否 | - | AI 优化后的纯文本 |
| `optimized_text_file` | string | 否 | - | 优化文本文件路径 |

说明：`optimized_text` 与 `optimized_text_file` 二选一。

---

## AI 提供商支持

支持 DeepSeek、Gemini、智谱 AI、火山引擎、OpenAI 兼容接口。通过 `provider` 选择。

---

## 错误处理

### AI 纠错节点

- 缺少 `segments_file`：返回错误
- AI 请求失败：按 `max_retries` 重试，失败返回错误
- 优化文本为空：返回错误

### 本地重构节点

- 缺少 `optimized_text/optimized_text_file`：返回错误
- 对齐失败：返回错误（不修改时间戳）

---

## 使用示例

### 示例 1：AI 纯文本纠错（单任务）

```json
{
  "task_name": "wservice.ai_optimize_text",
  "task_id": "task-demo-001",
  "callback": "http://localhost:5678/webhook/demo-t1",
  "input_data": {
    "segments_file": "http://localhost:9000/yivideo/task-demo-001/transcribe_data.json",
    "provider": "deepseek"
  }
}
```

### 示例 2：本地词级重构（单任务）

```json
{
  "task_name": "wservice.rebuild_subtitle_with_words",
  "task_id": "task-demo-001",
  "callback": "http://localhost:5678/webhook/demo-t1",
  "input_data": {
    "segments_file": "http://localhost:9000/yivideo/task-demo-001/transcribe_data.json",
    "optimized_text_file": "http://localhost:9000/yivideo/task-demo-001/optimized_text.txt"
  }
}
```

### 示例 3：工作流串联

```json
{
  "workflow_id": "wf-subtitle-pipeline-001",
  "callback": "http://localhost:5678/webhook/workflow",
  "workflow_config": {
    "nodes": [
      "faster_whisper.transcribe_audio",
      "wservice.ai_optimize_text",
      "wservice.rebuild_subtitle_with_words",
      "wservice.generate_subtitle_files"
    ]
  },
  "input_params": {
    "video_path": "http://localhost:9000/yivideo/demo.mp4"
  }
}
```

---

## 最佳实践

- 对长文本优先选择支持长上下文的 `provider`
- 通过动态引用传递 `segments_file`，减少硬编码路径
- 仅在需要时使用 `system_prompt_override`

---

## 故障排查

### 问题 1: 缺少转录文件

**症状**:
```
ValueError: 缺少必需参数: segments_file
```

**解决方案**:
- 确认 `segments_file` 路径正确
- 在工作流中使用动态引用 `${{faster_whisper.transcribe_audio.segments_file}}`

### 问题 2: AI 请求失败

**排查步骤**:
1. 检查对应提供商的 API 密钥
2. 查看网络连接与超时配置
3. 降低并发（若上层调用存在并发）

### 问题 3: 优化文本为空

**解决方案**:
- 检查系统提示词内容
- 验证模型返回是否为纯文本正文

---

**文档结束**

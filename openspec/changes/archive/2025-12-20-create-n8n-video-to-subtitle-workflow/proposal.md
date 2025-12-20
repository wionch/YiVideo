# Change: 使用n8n MCP创建视频到字幕提取的自动化工作流

## Why
为YiVideo平台创建一个完整的n8n自动化工作流，实现从视频输入到字幕输出的端到端处理流程，提高视频处理效率并为用户提供可视化的工作流编排能力。

## Research (REQUIRED)

### What was inspected
- n8n MCP服务状态：
  - 使用 `mcp__n8n-mcp__n8n_health_check` 确认n8n API可用
  - API URL: `http://host.docker.internal:5678`
  - MCP版本: 2.12.2
- 测试工作流 (`8t3fq4aMxV7fPiFR`)：
  - 通过 `mcp__n8n-mcp__n8n_get_workflow` 获取完整工作流结构
  - 理解了n8n的节点连接方式和数据传递机制
- YiVideo API文档 (`docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`)：
  - 详细研究了ffmpeg、audio_separator、faster_whisper、pyannote_audio节点的输入输出格式
  - 确认了各节点的数据结构和字段路径

### Findings (with evidence)

- Finding 1: n8n MCP工具完全可用
  - Evidence: `mcp__n8n-mcp__n8n_health_check` 返回成功状态
  - Decision: 可以使用n8n MCP创建工作流

- Finding 2: n8n工作流采用"设置参数→处理→等待回调"的模式
  - Evidence: 测试工作流显示的模式：Edit Fields → HttpRequest → Wait(webhook)
  - Decision: 新工作流将采用相同的模式

- Finding 3: 节点间数据传递使用 `{{$('节点名').item.json.路径}}` 格式
  - Evidence: 测试工作流中 `{{$('Wait').item.json.body.result.stages['ffmpeg.extract_audio'].output.audio_path}}`
  - Decision: 使用该格式实现跨节点数据引用

- Finding 4: YiVideo各节点的关键输出路径已明确
  - Evidence: API文档详细说明了每个节点的输出结构
  - Decision: 按照文档路径引用各节点输出

### Why this approach (KISS/YAGNI check)
- 最小化实现：仅包含必需的5个处理节点
- 复用现有模式：基于测试工作流的成功模式
- 明确数据流：每个节点的输入输出都有明确定义
- 拒绝过度设计：不添加额外的条件分支或复杂逻辑

- 明确拒绝的替代方案：
  - 不使用并行处理（增加复杂性）
  - 不添加错误处理分支（偏离核心目标）
  - 不实现动态任务配置（不符合当前需求）

- 非目标（Out of Scope）：
  - 不实现OCR字幕识别
  - 不添加字幕AI优化
  - 不实现多语言支持

## What Changes
- 创建新的n8n工作流：包含5个核心处理节点的完整视频到字幕提取流程
- 验证工作流正确性：确保节点间数据传递路径准确
- 文档化工作流：提供清晰的工作流说明文档

## Impact
- 受影响的规格：
  - `openspec/specs/n8n-integration/spec.md` (ADDED: 新工作流模板要求)
- 新增n8n工作流：通过MCP工具创建并部署
- 风险：
  - 节点间数据引用路径可能需要调试
  - 异步任务执行时间不确定
## ADDED Requirements

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
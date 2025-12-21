## ADDED Requirements

### Requirement: 集中式配置管理

所有微服务 MUST 使用集中式配置加载器，以确保持一致的行为和热重载能力。

#### Scenario: 服务加载配置
- **WHEN** 服务 worker 启动或需要配置值时
- **THEN** 它必须调用 `services.common.config_loader.get_config()`
- **AND** 它不得实现自己的配置文件读取逻辑

### Requirement: 统一字幕处理

所有字幕解析、生成和修改逻辑 MUST 由通用字幕模块处理。

#### Scenario: 写入 SRT 文件
- **WHEN** 任务需要生成 SRT 文件时
- **THEN** 它必须使用 `services.common.subtitle.subtitle_parser`
- **AND** 它不得使用临时的字符串格式化函数

#### Scenario: 解析字幕文件
- **WHEN** 任务需要解析 SRT 或 JSON 字幕文件时
- **THEN** 它必须使用 `services.common.subtitle.subtitle_parser`

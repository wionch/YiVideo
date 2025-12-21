# paddleocr-detect-subtitle-area Specification

## Purpose
TBD - created by archiving change fix-paddleocr-url-handling. Update Purpose after archive.
## Requirements
### Requirement: 字幕区域检测任务支持灵活的MinIO URL识别
`paddleocr.detect_subtitle_area` 任务 SHALL能够正确处理各种格式的MinIO URL输入，包括标准配置的主机名和非标准主机名（如 `host.docker.internal`）。

#### Scenario: 处理标准MinIO URL
- **WHEN** 输入URL为 `http://minio:9000/yivideo/task_id/keyframes`
- **THEN** 任务识别为MinIO URL并正确下载关键帧目录

#### Scenario: 处理非标准主机名MinIO URL
- **WHEN** 输入URL为 `http://host.docker.internal:9000/yivideo/task_id/keyframes`
- **THEN** 任务识别为MinIO URL并正确下载关键帧目录

#### Scenario: 处理minio://格式URL
- **WHEN** 输入URL为 `minio://yivideo/task_id/keyframes`
- **THEN** 任务识别为MinIO URL并正确下载关键帧目录

#### Scenario: 处理本地目录路径
- **WHEN** 输入为本地目录路径 `/share/keyframes`
- **THEN** 任务直接使用本地目录进行字幕区域检测

#### Scenario: 验证关键帧目录存在性
- **WHEN** 已获取到关键帧目录路径
- **THEN** 任务验证目录存在且包含关键帧文件，否则抛出适当的错误信息

#### Scenario: 关键帧目录获取逻辑
- **WHEN** 任务需要获取关键帧目录时
- **THEN** 任务 SHALL按照以下优先级：
  1. 从 `keyframe_dir` 参数直接获取
  2. 从上游 `ffmpeg.extract_keyframes` 阶段输出获取
  3. 对URL格式进行MinIO识别和下载处理
  4. 验证最终目录的有效性

## ADDED Requirements

### Requirement: 修复模块导入错误确保任务正常执行
paddleocr.detect_subtitle_area 任务 SHALL 确保所有依赖模块能够正常导入，避免 ModuleNotFoundError。

#### Scenario: decoder模块导入修复
- **GIVEN** paddleocr.detect_subtitle_area 任务开始执行
- **AND** 需要导入 decoder.py 中的 GPUDecoder 类
- **WHEN** 系统加载模块时
- **THEN** decoder.py 成功从 services.common.progress_logger 导入 create_progress_bar
- **AND** 不出现 ModuleNotFoundError
- **AND** GPUDecoder 类可以正常实例化

#### Scenario: change_detector模块导入修复
- **GIVEN** 字幕区域检测涉及变化检测功能
- **AND** 需要导入 change_detector.py 中的 ChangeDetector 类
- **WHEN** 系统加载模块时
- **THEN** change_detector.py 成功从 services.common.progress_logger 导入 create_stage_progress
- **AND** 不出现 ModuleNotFoundError
- **AND** ChangeDetector 类可以正常实例化

#### Scenario: 任务完整执行
- **GIVEN** 使用有效的视频文件和关键帧
- **AND** 调用 paddleocr.detect_subtitle_area 任务
- **WHEN** 任务执行过程涉及模块导入和解码
- **THEN** 任务成功完成
- **AND** 不出现 ModuleNotFoundError
- **AND** 返回正确的字幕区域检测结果


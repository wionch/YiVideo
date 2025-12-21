## ADDED Requirements
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
# paddleocr-detect-subtitle-area Specification Delta

## MODIFIED Requirements

### Requirement: 字幕区域检测任务支持灵活的MinIO URL识别
`paddleocr.detect_subtitle_area` 任务 SHALL能够正确处理各种格式的MinIO URL输入，包括标准配置的主机名、非标准主机名（如 `host.docker.internal`）、以及压缩包文件URL。

#### Scenario: 处理标准MinIO URL
- **WHEN** 输入URL为 `http://minio:9000/yivideo/task_id/keyframes`
- **THEN** 任务识别为MinIO URL并正确下载关键帧目录

#### Scenario: 处理非标准主机名MinIO URL
- **WHEN** 输入URL为 `http://host.docker.internal:9000/yivideo/task_id/keyframes`
- **THEN** 任务识别为MinIO URL并正确下载关键帧目录

#### Scenario: 处理minio://格式URL
- **WHEN** 输入URL为 `minio://yivideo/task_id/keyframes`
- **THEN** 任务识别为MinIO URL并正确下载关键帧目录

#### Scenario: 处理压缩包URL
- **WHEN** 输入URL为 `http://host.docker.internal:9000/yivideo/task_id/keyframes/keyframes_compressed.zip`
- **AND** `auto_decompress` 参数为 `true`（默认值）
- **THEN** 任务识别为压缩包URL，下载并自动解压到本地目录

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
  4. 如果是压缩包且`auto_decompress`为true，自动解压
  5. 验证最终目录的有效性

## ADDED Requirements

### Requirement: 支持大量关键帧的处理（修复参数列表过长问题）
`paddleocr.detect_subtitle_area` 任务 SHALL能够处理任意数量的关键帧文件（包括10000+个文件），而不受系统命令行参数长度限制。

#### Scenario: 处理大量关键帧文件
- **WHEN** 关键帧目录包含10000+个图片文件
- **THEN** 任务通过临时文件传递文件路径列表给子进程，成功完成字幕区域检测

#### Scenario: 临时文件自动清理
- **WHEN** 任务执行完成或发生异常时
- **THEN** 任务 SHALL自动清理所有创建的临时文件

#### Scenario: 向后兼容小文件集
- **WHEN** 关键帧目录包含少量文件（<100个）
- **THEN** 任务的行为和性能与之前版本保持一致

### Requirement: 自动解压MinIO压缩包
`download_keyframes_directory` 函数 SHALL支持自动检测和解压MinIO中的压缩包文件。

#### Scenario: 自动检测压缩包URL
- **WHEN** MinIO URL指向`.zip`或`.tar.gz`文件
- **THEN** 函数识别为压缩包格式

#### Scenario: 下载并解压压缩包
- **WHEN** URL指向压缩包且`auto_decompress`为true
- **THEN** 函数下载压缩包并解压到目标目录，返回解压后的文件列表

#### Scenario: 禁用自动解压
- **WHEN** `auto_decompress`参数为false
- **THEN** 函数下载压缩包文件但不解压，保持原始压缩包文件

#### Scenario: 压缩包下载失败处理
- **WHEN** 压缩包下载或解压失败时
- **THEN** 函数返回明确的错误信息，区分下载失败和解压失败

### Requirement: auto_decompress参数支持
`paddleocr.detect_subtitle_area` 任务 SHALL支持`auto_decompress`参数来控制压缩包的自动解压行为。

#### Scenario: 默认启用自动解压
- **WHEN** 未指定`auto_decompress`参数
- **THEN** 参数默认值为`true`，自动解压压缩包

#### Scenario: 明确禁用自动解压
- **WHEN** `auto_decompress`参数设置为`false`
- **THEN** 任务下载压缩包但不解压，直接使用压缩包文件路径

#### Scenario: 从workflow_context继承参数
- **WHEN** `auto_decompress`未在`input_data`中指定
- **THEN** 任务尝试从`workflow_context`中获取该参数

### Requirement: 拼接图像任务支持压缩包输入
`paddleocr.create_stitched_images` 任务 SHALL能够处理MinIO上的压缩包输入（如压缩的裁剪图像目录）。

#### Scenario: 识别压缩包格式输入
- **WHEN** `cropped_images_path` 参数指向MinIO上的压缩包（如`.zip`）
- **THEN** 任务识别该输入为压缩包

#### Scenario: 下载并解压
- **WHEN** 输入为压缩包URL
- **THEN** 任务自动下载并解压到临时目录，并使用该目录作为后续拼接脚本的输入

#### Scenario: 解压后结构验证
- **WHEN** 压缩包解压完成
- **THEN** 任务验证解压后的目录是否包含图像文件或符合预期的结构

#### Scenario: 清理临时解压目录
- **WHEN** 任务完成（无论成功或失败）
- **THEN** 任务自动清理下载和解压产生的临时目录

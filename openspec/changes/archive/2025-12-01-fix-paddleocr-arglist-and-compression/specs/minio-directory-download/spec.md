# minio-directory-download Specification Delta

## ADDED Requirements

### Requirement: MinIO压缩包下载和解压功能
`minio_directory_download` 模块 SHALL提供下载和自动解压MinIO压缩包文件的能力。

#### Scenario: 检测压缩包URL
- **WHEN** 调用`is_archive_url(url)`函数
- **AND** URL指向`.zip`、`.tar.gz`等压缩包文件
- **THEN** 函数返回`True`

#### Scenario: 检测普通目录URL
- **WHEN** 调用`is_archive_url(url)`函数
- **AND** URL指向普通目录或文件
- **THEN** 函数返回`False`

#### Scenario: 下载并解压压缩包
- **WHEN** 调用`download_and_extract_archive(minio_url, local_dir)`
- **THEN** 函数执行以下步骤：
  1. 下载压缩包到临时目录
  2. 调用`decompress_archive`解压到目标目录
  3. 清理临时压缩包文件
  4. 返回包含`success`、`extracted_files`等信息的结果字典

#### Scenario: 压缩包下载失败
- **WHEN** 压缩包下载过程中发生网络错误
- **THEN** 函数返回包含`success=False`和具体错误信息的结果字典

#### Scenario: 压缩包解压失败
- **WHEN** 压缩包下载成功但解压失败
- **THEN** 函数清理已下载的压缩包文件，返回包含解压失败信息的结果字典

### Requirement: 扩展download_directory_from_minio支持压缩包
`download_directory_from_minio` 函数 SHALL自动检测URL是否指向压缩包，并支持自动解压。

#### Scenario: 自动处理压缩包URL
- **WHEN** `minio_url`指向`.zip`文件
- **AND** URL被识别为压缩包
- **THEN** 函数调用`download_and_extract_archive`下载并解压（如果启用了自动解压）

#### Scenario: 保持原有目录下载行为
- **WHEN** `minio_url`指向普通目录
- **THEN** 函数使用原有的目录遍历下载逻辑

#### Scenario: 压缩包下载不解压
- **WHEN** 调用者明确指定不解压（如果API支持该选项）
- **THEN** 函数仅下载压缩包文件到目标目录

#### Scenario: 返回格式一致性
- **WHEN** 使用任何下载方式（压缩包或目录）
- **THEN** 函数返回一致的结果字典格式，包含`success`、`total_files`、`downloaded_files`等字段

### Requirement: 临时文件管理
压缩包下载功能 SHALL正确管理临时文件，防止磁盘空间泄漏。

#### Scenario: 正常流程临时文件清理
- **WHEN** 压缩包下载并解压完成
- **THEN** 函数自动删除临时压缩包文件

#### Scenario: 异常流程临时文件清理
- **WHEN** 下载或解压过程中发生异常
- **THEN** 函数在`finally`块中清理所有临时文件

#### Scenario: 使用tempfile模块
- **WHEN** 需要创建临时文件时
- **THEN** 函数使用Python的`tempfile`模块确保文件名唯一性和安全性

# 修复残留 /tmp 使用 - 简化实施清单

## 目标

直接替换所有残留的 `/tmp` 使用，遵循 KISS、DRY、SOLID、YAGNI 原则。

## 阶段 1：创建简单工具函数

### 1.1 创建临时路径生成工具

-   [ ] 1.1.1 创建 `services/common/temp_path_utils.py`
    -   [ ] 实现简单的 `get_temp_path(workflow_id, suffix)` 函数
    -   [ ] 包含必要的导入：os, time, uuid
    -   [ ] 添加基本的错误处理

## 阶段 2：逐个替换问题文件

### 2.1 修复 MinIO 目录上传服务 (最高优先级)

-   [ ] 2.1.1 修改 `services/common/minio_directory_upload.py`
    -   [ ] 导入 `get_temp_path` 函数
    -   [ ] 替换第 137 行的 `tempfile.gettempdir()` 使用
    -   [ ] 验证路径生成正确

### 2.2 修复 MinIO 目录下载服务

-   [ ] 2.2.1 修改 `services/common/minio_directory_download.py`
    -   [ ] 导入 `get_temp_path` 函数
    -   [ ] 替换第 90 行的 `tempfile.NamedTemporaryFile` 使用
    -   [ ] 更新文件操作逻辑

### 2.3 修复 PaddleOCR 服务

-   [ ] 2.3.1 修改 `services/workers/paddleocr_service/app/tasks.py`
    -   [ ] 导入 `get_temp_path` 函数
    -   [ ] 替换第 305 行的临时文件创建逻辑
    -   [ ] 更新 JSON 文件写入方式

### 2.4 修复 Audio Separator 服务

-   [ ] 2.4.1 修改 `services/workers/audio_separator_service/app/model_manager.py`
    -   [ ] 导入 `get_temp_path` 函数
    -   [ ] 替换第 59 行的临时文件创建逻辑

### 2.5 修复 API Gateway MinIO 服务

-   [ ] 2.5.1 修改 `services/api_gateway/app/minio_service.py`
    -   [ ] 导入 `get_temp_path` 函数
    -   [ ] 替换第 66 行和第 183 行的 `tempfile.NamedTemporaryFile` 使用

## 阶段 3：验证替换完整性

### 3.1 代码检查

-   [ ] 3.1.1 使用搜索工具验证无残留 `/tmp` 使用
    ```bash
    grep -r "/tmp" --include="*.py" .
    grep -r "tempfile\.gettempdir\|tempfile\.NamedTemporaryFile" --include="*.py" .
    ```
-   [ ] 3.1.2 检查所有修改文件的语法正确性
-   [ ] 3.1.3 确保导入语句正确添加

### 3.2 功能验证

-   [ ] 3.2.1 运行单元测试确保功能正常
-   [ ] 3.2.2 检查容器日志确认无 `/tmp` 路径
-   [ ] 3.2.3 验证临时文件创建和清理机制

## 完成标准

-   [ ] 所有 `/tmp` 使用被基于工作流 ID 的路径替换
-   [ ] 容器日志中不再出现 `/tmp` 路径
-   [ ] 所有服务工作流正常运行
-   [ ] 代码简洁，易于理解和维护

## 预期效果

-   ✅ 最小的代码变更
-   ✅ 消除所有 `/tmp` 使用
-   ✅ 提高安全性
-   ✅ 易于理解和维护

## 简化设计原则

-   **KISS**: 直接替换，不创建复杂抽象
-   **DRY**: 只有一个简单的 `get_temp_path()` 函数
-   **SOLID**: 每个函数都有单一职责
-   **YAGNI**: 只解决当前问题，不为未来设计

## 变更总结

本变更是对残留 `/tmp` 使用的直接修复，通过创建简单的路径生成函数并逐个替换问题代码，实现最小化的变更。遵循软件工程最佳实践，确保代码简洁、可维护，同时提高系统安全性。

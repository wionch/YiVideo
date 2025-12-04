# 变更：彻底替换残留的系统级 /tmp 目录使用

## 背景

在完成 `refactor-directory-usage` 提案后，经过实际运行验证发现项目中仍然存在多处使用系统级 `/tmp` 目录的情况。这些遗漏的临时文件使用会导致：

1. **安全风险持续存在**：临时文件仍在系统级目录中，存在权限和清理问题
2. **功能缺陷**：从容器日志显示压缩上传过程中仍在使用 `/tmp` 目录
3. **不一致性**：部分功能使用新的目录规范，部分仍在使用旧路径

### 日志证据

容器执行日志显示：

```
[2025-12-04 08:43:28,748: INFO/ForkPoolWorker-31] 开始压缩目录: /share/workflows/task_id/cropped_images/frames -> /tmp/frames_compressed_1764837808_c0febec5.zip
```

这明确证实了压缩上传功能仍在使用系统级 `/tmp` 目录。

## 变更内容

### 遗漏的/tmp 使用位置

经过详细代码审查，发现以下位置仍在使用系统级临时目录：

1. **`services/common/minio_directory_upload.py`**

    - 第 137 行：`tempfile.gettempdir()` (向后兼容模式)
    - 影响：压缩上传临时文件

2. **`services/common/minio_directory_download.py`**

    - 第 90 行：`tempfile.NamedTemporaryFile(delete=False, suffix=suffix)`
    - 影响：压缩包下载和临时存储

3. **`services/workers/paddleocr_service/app/tasks.py`**

    - 第 305 行：`tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False, suffix='.json')`
    - 影响：字幕区域检测参数传递

4. **`services/workers/audio_separator_service/app/model_manager.py`**

    - 第 59 行：`tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json', encoding='utf-8')`
    - 影响：音频分离结果输出

5. **`services/api_gateway/app/minio_service.py`**
    - 第 66 行和第 183 行：`tempfile.NamedTemporaryFile(delete=False)`
    - 影响：文件上传临时存储

### 核心变更目标

-   **消除安全风险**：彻底替换所有系统级 `/tmp` 使用
-   **统一路径规范**：所有临时文件使用 `/share/workflows/{workflow_id}/tmp/` 格式
-   **增强隔离性**：基于工作流 ID 的文件隔离机制
-   **改善调试体验**：统一的临时文件管理便于问题排查

## 影响评估

### 正面影响

-   **安全提升**：消除临时文件在系统级目录的安全隐患
-   **管理简化**：统一目录结构，便于监控和清理
-   **调试友好**：任务相关的临时文件集中管理
-   **性能优化**：减少系统级临时目录的 I/O 竞争

### 风险评估

-   **中等风险**：涉及多个服务模块的临时文件管理
-   **兼容性风险**：需要确保现有工作流的正常运行
-   **测试复杂性**：需要验证所有受影响的功能节点

### 影响的系统和文件

-   **MinIO 服务**：文件上传下载临时文件管理
-   **FFmpeg Worker**：视频处理临时文件
-   **PaddleOCR Worker**：OCR 处理临时文件
-   **Audio Separator Worker**：音频分离临时文件
-   **API Gateway**：统一文件操作接口

## 实施策略

### 阶段 1：统一临时文件管理工具

1. 创建基于工作流 ID 的临时文件管理函数
2. 设计向后兼容性机制
3. 更新各服务的导入和使用方式

### 阶段 2：逐个服务修复

1. **MinIO 目录上传服务**：移除向后兼容的 `/tmp` 使用
2. **MinIO 目录下载服务**：统一临时文件路径
3. **API Gateway 服务**：更新文件上传临时管理
4. **PaddleOCR 服务**：更新参数文件临时存储
5. **Audio Separator 服务**：更新结果文件临时存储

### 阶段 3：验证和测试

1. 单元测试验证临时文件路径生成
2. 集成测试确认各服务工作正常
3. 端到端测试验证整体功能不受影响

## 回滚计划

如果出现问题，可以快速回滚：

1. 恢复原有的 `tempfile` 模块使用
2. 清理新增的基于工作流 ID 的临时目录
3. 重新部署原版本代码
4. 验证系统功能恢复正常

## 成功标准

-   容器日志中不再出现 `/tmp` 路径
-   所有临时文件基于工作流 ID 创建
-   现有工作流功能完全不受影响
-   临时文件清理机制正常工作

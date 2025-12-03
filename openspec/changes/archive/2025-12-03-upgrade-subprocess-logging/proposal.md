# 变更：将 subprocess.run 升级为 subprocess.Popen 以实现实时日志输出

## 背景

YiVideo 项目的 GPU 任务在执行过程中，当前使用的`subprocess.run`无法实时输出子进程的日志信息，导致：

1. 无法实时监控 GPU 任务执行状态
2. 任务执行过程缺乏可见性
3. 调试和问题排查困难
4. 用户体验差，无法感知任务进度

## 变更目标

将项目中的 GPU 任务子进程启动方式从`subprocess.run`升级为`subprocess.Popen`，实现：

-   **实时日志输出**：GPU 任务的执行过程可以实时显示在日志中
-   **增强监控能力**：支持任务进度的实时监控
-   **保持兼容性**：不影响现有功能执行结果
-   **提升调试效率**：便于开发者调试和运维监控

## 具体变更内容

### 核心组件改进

1. **创建通用 subprocess.Popen 封装工具**

    - 新建 `services/common/subprocess_utils.py`
    - 提供与 `subprocess.run` 兼容的接口
    - 支持实时日志输出和流式处理

2. **更新 GPU 任务服务**
    - **faster_whisper_service**: 语音转文字任务日志实时化
    - **paddleocr_service**: OCR 检测任务日志实时化
    - **ffmpeg_service**: 音视频处理任务日志实时化
    - **audio_separator_service**: 音频分离任务日志实时化
    - **pyannote_audio_service**: 音频分析任务日志实时化
    - **wservice**: 字幕优化任务日志实时化

### 技术实现方案

-   使用 `subprocess.Popen` 替代 `subprocess.run`
-   实现多线程流式读取 stdout/stderr
-   保持 30 分钟超时机制
-   维护环境变量继承
-   支持返回码检查和异常处理

## 影响评估

### 受影响的服务

-   `services/workers/faster_whisper_service/app/tasks.py`
-   `services/workers/paddleocr_service/app/tasks.py`
-   `services/workers/ffmpeg_service/app/tasks.py`
-   `services/workers/audio_separator_service/app/model_manager.py`
-   `services/workers/pyannote_audio_service/app/tasks.py`
-   `services/workers/wservice/app/tasks.py`

### 向后兼容性

-   ✅ 保持所有现有 API 接口不变
-   ✅ 保持执行结果格式一致
-   ✅ 保持超时和错误处理机制
-   ✅ 保持环境变量继承

### 性能影响

-   **内存使用**：轻微增加（线程开销）
-   **CPU 使用**： negligible（主要是 I/O 线程）
-   **执行时间**：无影响（不影响实际任务执行）
-   **日志输出**：显著提升（实时显示）

### 风险评估

-   **低风险**：变更局限于日志输出层，不影响核心业务逻辑
-   **可回滚**：提供兼容接口，可以快速回滚到原有实现
-   **测试充分**：需要全面的单元测试和集成测试验证

## 实施优先级

1. **高优先级**：faster_whisper_service, paddleocr_service, ffmpeg_service
2. **中优先级**：audio_separator_service, pyannote_audio_service
3. **低优先级**：wservice, 其他模块

## 验收标准

1. GPU 任务执行时能够实时显示日志信息
2. 所有现有功能保持正常工作
3. 任务执行结果与之前完全一致
4. 日志记录保持详细和准确
5. 系统性能无明显下降

## 实施里程碑

-   **Phase 1**: 创建通用封装工具
-   **Phase 2**: 更新核心 GPU 服务
-   **Phase 3**: 更新辅助服务
-   **Phase 4**: 全面测试和验证
-   **Phase 5**: 文档更新和部署

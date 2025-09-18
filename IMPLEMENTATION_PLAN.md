# 实施计划：P模块与F模块集成（代码分析修正版）

**目标**: 基于最终版的“异步管道模型”和“分布式GPU锁”设计，重构P模块和F模块，实现包含“抽帧-区域检测-裁剪-OCR”的完整视频处理工作流，并确保过程文件的清理。

---

## Stage 1: 搭建基础环境与共享模块

**Goal**: 创建实现分布式GPU锁所必需的通用模块，并确认Celery的跨服务任务调用配置。

**Deliverable Files**: 
- `services/common/locks.py` (新创建)
- `services/workers/paddleocr_service/app/celery_app.py` (分析与配置)
- `services/workers/ffmpeg_service/app/celery_app.py` (分析与配置)
- `docker-compose.yml` (分析与配置)

**Justification**: (对应设计: 分布式GPU锁) 必须先有一个可靠的、可被所有服务共享的锁机制。同时，要确保P模块能成功“发现”并调用F模块的Celery任务。

**Success Criteria**: 
- `services/common/locks.py` 文件被创建，并包含我们设计的`@gpu_lock`装饰器。
- 确认P模块的Celery应用可以导入并调用F模块的Celery任务。
- 确认`docker-compose.yml`中，`services/common`目录已通过`volumes`正确映射到P模块和F模块的容器中。

**Status**: Not Started

---

## Stage 2: 新增并暴露F模块(ffmpeg_service)的Celery任务

**Goal**: 在F模块中，将`video_decoder.py`的强大功能封装成新的Celery任务，以供P模块调用。

**Deliverable Files**: 
- `services/workers/ffmpeg_service/app/tasks.py` (diff)

**Justification**: F模块虽然有能力，但没有提供服务接口。此阶段就是构建这些接口，使其成为一个真正的视频处理微服务。

**Success Criteria**: 
- 在`tasks.py`中创建了两个新的Celery任务：
  1.  `extract_keyframes`: 包装 `video_decoder.extract_random_frames`，接收视频路径和抽帧数量，应用`@gpu_lock`，返回帧图片路径列表。
  2.  `crop_subtitle_images`: 包装 `video_decoder.decode_video_concurrently`，接收视频路径、裁剪区域坐标和并发数，应用`@gpu_lock`，返回裁剪后的字幕条图片路径列表。

**Status**: Not Started

---

## Stage 3: 重构P模块(paddleocr_service)以调用F模块

**Goal**: 这是本次重构的核心。在P模块中，用对F模块新任务的异步调用，替换掉本地的`GPUDecoder`和`KeyFrameDetector`实现。

**Deliverable Files**: 
- `services/workers/paddleocr_service/app/logic.py` (diff)
- `services/workers/paddleocr_service/app/tasks.py` (diff)

**Justification**: 实现P、F模块的职责分离，将视频处理的重担完全交给F模块，P模块专注于OCR和业务逻辑编排。

**Success Criteria**: 
- 在`logic.py`的`extract_subtitles_from_video`函数中：
  - **完全移除**对本地`GPUDecoder`和`KeyFrameDetector`的调用。
  - 逻辑被重构为构建并启动一个Celery `chain`。
- 在`tasks.py`中创建/修改了Celery任务：
  - `process_video_workflow` (或修改现有任务): 作为工作流入口，负责调用`logic.py`中的重构后逻辑。
  - `detect_subtitle_area_callback`: 新的回调任务，接收`extract_keyframes`的结果，调用`SubtitleAreaDetector`，然后**负责删除关键帧图片**。
  - `perform_ocr_callback`: 新的回调任务，接收`crop_subtitle_images`的结果，调用`MultiProcessOCREngine`，然后**负责删除字幕条图片**。
  - `postprocess_and_finalize_callback`: 新的回调任务，接收OCR结果，调用`SubtitlePostprocessor`进行合并与格式化，生成文件，并**清理整个工作流目录**。

**Status**: Not Started

---

## Stage 4: 端到端验证

**Goal**: 部署并运行整个重构后的工作流，确保所有环节按预期工作，包括功能、性能和资源清理。

**Deliverable Files**: 
- `test.py` (修改，用于触发新的工作流)

**Justification**: 确保重构没有引入新的bug，并且达到了预期的架构目标。

**Success Criteria**: 
- 运行一个完整的集成测试，可以成功完成一个视频的处理。
- 通过日志或文件系统，可以观察到：
  1. F模块的`extract_keyframes`和`crop_subtitle_images`任务被成功调用。
  2. P模块的回调任务按顺序执行。
  3. 关键帧图片和字幕条图片在使用后被成功删除。
  4. 整个`workflow_id`临时目录在最后被成功删除。
- 最终的`.srt`和`.json`字幕文件被正确生成。

**Status**: Not Started

# 实施计划：重构工作流，新增独立图像拼接任务

## Stage 1: 创建独立的图像拼接任务

**目标**: 创建一个新的Celery任务 `paddleocr.create_stitched_images`，负责将裁剪后的字幕条图像根据配置进行拼接，并生成包含详细元数据的清单文件。

**可交付文件**:
- `services/workers/paddleocr_service/app/tasks.py` (新增任务)

**理由**: 按照您的要求，将拼接功能模块化，使其成为工作流中一个独立的、可测试的步骤，提升了架构的清晰度。

**成功标准**:
1.  成功在 `tasks.py` 中创建 `create_stitched_images` 任务。
2.  该任务能够正确读取 `cropped_images/frames` 目录下的图片，按 `concat_batch_size` 配置进行拼接。
3.  拼接后的图片保存到 `cropped_images/multi_frames` 目录。
4.  在 `cropped_images` 目录下生成一个 `multi_frames.json` 清单文件，该文件使用我们讨论的详细格式，记录每张拼接图及其子图的详细元数据（帧号、高度、偏移量）。

**状态**: Complete

## Stage 2: 重构OCR任务以消费拼接数据

**目标**: 修改现有的 `paddleocr.perform_ocr` 任务及其依赖的 `executor_ocr.py`，使其消费上一阶段生成的拼接图和清单文件来完成OCR。

**可交付文件**:
- `services/workers/paddleocr_service/app/tasks.py` (修改 `perform_ocr`)
- `services/workers/paddleocr_service/app/executor_ocr.py` (重构)
- `services/workers/paddleocr_service/app/modules/ocr.py` (可能微调)

**理由**: 使OCR任务适配新的工作流架构，专注于识别，而将数据准备工作完全交给上游。

**成功标准**:
1.  `perform_ocr` 任务现在依赖 `create_stitched_images` 的输出。
2.  `executor_ocr.py` 被重构，其主要逻辑变为：读取 `multi_frames.json`，遍历拼接图并调用OCR引擎，然后使用清单文件中的元数据进行坐标逆推。
3.  `executor_ocr.py` 中准备拼接任务的 `_prepare_ocr_tasks` 函数被移除，因为该功能已移至上游任务。

**状态**: Complete

## Stage 3: 更新工作流并清理代码

**目标**: 将新任务正式整合到默认工作流中，并清理因重构而产生的冗余代码。

**可交付文件**:
- `services/api_gateway/app/main.py` (或定义工作流的文件)
- `services/workers/paddleocr_service/app/executor_ocr.py` (清理)

**理由**: 使新的工作流架构正式生效，并保持代码库的整洁。

**成功标准**:
1.  在API网关（或工作流定义处）的默认工作流链 `workflow_chain` 中，在 `ffmpeg.crop_subtitle_images` 之后，`paddleocr.perform_ocr` 之前，插入新的 `paddleocr.create_stitched_images` 任务。
2.  移除 `executor_ocr.py` 中用于处理 `use_image_concat: false` 的旧逻辑分支，因为所有流程现在都将统一使用拼接模式。

**状态**: Complete
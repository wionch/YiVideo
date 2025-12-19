## Context
- 上传成功后自动删除本地目录的逻辑存在于 `paddleocr.create_stitched_images`（直接 `shutil.rmtree`）、`paddleocr.perform_ocr`/`postprocess_and_finalize`（受 `cleanup_temp_files` 控制）。这会让后续任务无法读取本地结果。
- 配置回退默认 `cleanup_temp_files=True`，即使配置缺失也会开启清理路径。
- 已有显式清理接口 `DELETE /v1/files/directories`，可承担本地目录删除职责。

## Goals / Non-Goals
- Goals: 保留上传后的本地文件/目录；移除/禁用自动删除分支；对齐清理入口到 `DELETE /v1/files/directories`。
- Non-Goals: 不改 MinIO 上传协议、不新增后台清理调度、不修改非相关 worker 逻辑。

## Decisions
- 保留本地产物：移除 `create_stitched_images` 上传成功后的 `shutil.rmtree(multi_frames_path)` 分支。
- 仅清理下载类临时目录：`perform_ocr`/`postprocess_and_finalize` 仅可清理下载的临时目录，禁止删除核心产物（multi_frames/manifest/OCR 结果）。
- 清理入口收束：文档/规范明确通过 `DELETE /v1/files/directories` 做回收；不依赖 `cleanup_temp_files` 控制上传后删除。
- 配置回退：评估是否需要让 `get_cleanup_temp_files_config` 回退为 False 或仅用于下载缓存，不得作用于产物目录。

## Risks / Trade-offs
- 磁盘占用上升：需要监控磁盘和流程结束后显式调用删除接口。
- 残留文件：需要确保异常路径也能在显式清理时处理。

## Migration Plan
- 先更新 `paddleocr` 任务的清理逻辑与配置使用。
- 同步规范/文档指向 `DELETE /v1/files/directories`。
- 回归测试相关任务链，确认本地路径在上传后仍可访问。

## Open Questions
- 是否需要为离线批处理提供单独的后台清理 Job？当前计划依赖显式 API（默认否）。

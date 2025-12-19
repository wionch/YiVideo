# Change: 移除上传后自动删除本地文件功能

## Why
现有任务在上传阶段产物到 MinIO 后仍会自动删除本地目录/文件，导致后置任务或调试流程无法复用本地产物。当前清理路径已统一到 `DELETE /v1/files/directories`，应移除上传后的隐式清理逻辑。

## Research (REQUIRED)

### What was inspected
- Specs
  - `openspec/specs/project-architecture/spec.md`：未约束上传后的本地文件保留策略
  - `openspec/specs/local-directory-management/spec.md`：定义目录删除接口，但未与上传保留行为关联
- Code
  - `services/workers/paddleocr_service/app/tasks.py:556-620`：`create_stitched_images` 在上传成功后即使 `delete_local_stitched_images_after_upload` 默认为 False 仍调用 `shutil.rmtree(output_data["multi_frames_path"])` 清理本地目录
  - `services/workers/paddleocr_service/app/tasks.py:947-995`：`perform_ocr` 在 `cleanup_temp_files` 启用时删除 `multi_frames_path`、`manifest_path` 及 OCR 结果文件，影响后续阶段重用本地产物
  - `services/workers/paddleocr_service/app/tasks.py:1126-1132`：`postprocess_and_finalize` 依赖 `cleanup_temp_files` 删除 OCR 结果文件
  - `services/common/config_loader.py:66-90` & `config.yml:1-14`：`get_cleanup_temp_files_config` 默认回退 True，意味着清理逻辑可在配置缺失时自动生效
  - `services/api_gateway/app/file_operations.py:31-96`：`DELETE /v1/files/directories` 已提供安全的本地目录删除能力

### Findings (with evidence)
- Finding 1: `paddleocr.create_stitched_images` 上传成功后仍强制删除 `multi_frames_path`（默认 delete_local=False）=> 直接清掉后续需要的本地目录。  
  Evidence: `services/workers/paddleocr_service/app/tasks.py:556-620`  
  Decision: Doc+Code — 保留本地目录，取消上传后的自动删除。

- Finding 2: `paddleocr.perform_ocr` / `postprocess_and_finalize` 受 `cleanup_temp_files` 影响删除多帧目录、manifest 和 OCR 结果，即便上传成功且默认未要求删除。  
  Evidence: `services/workers/paddleocr_service/app/tasks.py:947-995`, `services/workers/paddleocr_service/app/tasks.py:1126-1132`, `services/common/config_loader.py:66-90`, `config.yml:1-14`  
  Decision: Doc+Code — 移除/禁用这些上传后清理路径，确保本地产物在显式清理前可复用。

- Finding 3: 统一清理接口已存在（`DELETE /v1/files/directories`），可承担目录删除职责。  
  Evidence: `services/api_gateway/app/file_operations.py:31-96`  
  Decision: Spec delta — 明确上传不触发自动删除，清理依赖显式 API。

### Why this approach (KISS/YAGNI check)
- 最小变更：删除/关闭上传后的自动清理分支，保留已有的显式删除接口即可满足需求。
- 避免重复：统一依赖现有 `DELETE /v1/files/directories`，不再维护任务内私有清理开关。
- 非目标：不改动上传协议、MinIO 逻辑或新增清理调度流程。

## What Changes
- 新增规范：上传成功后必须保留本地产物，后续清理只能通过显式接口触发。
- 移除 `paddleocr` 任务内的上传后自动删除本地目录/文件逻辑（含 `cleanup_temp_files` 路径）。
- 保持删除职责在 `DELETE /v1/files/directories`，不再从上传流程触发隐式清理。

## Impact
- Affected specs: `specs/project-architecture/spec.md`（ADDED：上传后保留本地文件并通过显式接口清理）。
- Affected code: `services/workers/paddleocr_service/app/tasks.py`（去除上传后清理），`services/common/config_loader.py`（视实现决定是否调整默认清理回退），`services/api_gateway/app/file_operations.py`（作为清理入口的对齐点）。
- Rollout: 无兼容开关，行为直接改为保留本地产物；若需要清理，应通过 API 调用。
- Risks: 本地磁盘占用增加；需确保调度/监控可发现未清理目录。

## Traceability (Research → Tasks)
- Finding 1 → 1.1
- Finding 2 → 1.2
- Finding 3 → 1.3

## 1. Implementation

- [x] 1.1 移除 `create_stitched_images` 上传成功后对 `multi_frames_path` 的自动删除
  - Evidence: proposal.md → Research → Finding 1 (Decision: Doc+Code)
  - Edit scope: `services/workers/paddleocr_service/app/tasks.py:556-629`
  - Commands:
    - `python -m compileall services/workers/paddleocr_service/app`
    - `! grep -n "shutil.rmtree(output_data\\[\"multi_frames_path\"\\])" services/workers/paddleocr_service/app/tasks.py`
  - Done when: 编译通过且 grep 无匹配，函数上传后不再清理 `multi_frames_path`（除非显式 delete_local 为真）。

- [x] 1.2 停止 `perform_ocr`/`postprocess_and_finalize` 依赖 `cleanup_temp_files` 删除核心产物
  - Evidence: proposal.md → Research → Finding 2 (Decision: Doc+Code)
  - Edit scope: `services/workers/paddleocr_service/app/tasks.py:946-1132`
  - Commands:
    - `python -m compileall services/workers/paddleocr_service/app`
    - `! grep -n "shutil.rmtree(multi_frames_path)" services/workers/paddleocr_service/app/tasks.py`
    - `! grep -n "os.remove(manifest_path)" services/workers/paddleocr_service/app/tasks.py`
    - `! grep -n "os.remove(ocr_results_path)" services/workers/paddleocr_service/app/tasks.py`
  - Done when: 编译通过且上述清理调用在核心产物上不存在，仅保留对下载型临时目录的清理。

- [x] 1.3 文档对齐：明确本地目录清理应通过 `DELETE /v1/files/directories`
  - Evidence: proposal.md → Research → Finding 3 (Decision: Spec delta)
  - Edit scope: `docs/technical/IMPLEMENTATION_SUMMARY.md:60-140`
  - Commands:
    - `grep -n "/v1/files/directories" docs/technical/IMPLEMENTATION_SUMMARY.md`
  - Done when: 文档列出目录删除接口并说明用于任务产物清理，grep 返回包含该路径的条目。

## 2. Validation

- [x] 2.1 OpenSpec strict validation
  - Evidence: proposal.md → Research → Finding 3
  - Commands:
    - `openspec validate remove-upload-auto-delete --strict`
  - Done when: 命令退出码为 0。

- [ ] 2.2 Project checks
  - Evidence: proposal.md → Research → Findings 1-2
  - Commands:
    - `python -m compileall services/workers/paddleocr_service/app`
    - `pytest services/workers/paddleocr_service/app`
  - Done when: 两个命令均成功且无新增警告。

## 3. Self-check (ENFORCED)

- [x] 3.1 Each task touches exactly one file in Edit scope.
- [x] 3.2 Each task references exactly one Finding.
- [x] 3.3 No task contains conditional language (if needed/必要时/可能/按需/...).
- [x] 3.4 Each task includes Commands and an objective Done when.

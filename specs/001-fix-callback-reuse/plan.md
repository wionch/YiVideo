# Implementation Plan: callback 复用覆盖修复

**Branch**: `001-fix-callback-reuse` | **Date**: 2025-12-21 | **Spec**: specs/001-fix-callback-reuse/spec.md  
**Input**: Feature specification from `/specs/001-fix-callback-reuse/spec.md`

**Note**: Filled by `/speckit.plan` per workflow。

## Summary

目标是确保单任务模式在所有节点执行 `task_id+task_name` 复用时不覆盖已有 `stages`，命中成功直接回调，等待态不重复调度，未命中按常规执行，并同步更新节点文档的复用规则与示例。

## Technical Context

**Language/Version**: Python 3.8+  
**Primary Dependencies**: FastAPI, Celery, Redis (DB3), MinIO, Pydantic  
**Storage**: Redis（状态），MinIO（产物），本地 `/share` 挂载  
**Testing**: pytest（仓库推荐），可补充接口/集成用例  
**Target Platform**: Linux server（Docker Compose 部署）  
**Project Type**: 后端服务（api_gateway + workers）  
**Performance Goals**: 未明确（默认保持现有延迟/吞吐，不新增额外调度）  
**Constraints**: 不得覆盖 `stages` 历史阶段；复用命中需短路调度；文档与行为一致  
**Scale/Scope**: 单任务节点覆盖 ffmpeg/faster_whisper/audio_separator/pyannote_audio/paddleocr/indextts/wservice 等

## Constitution Check

仓库 constitution 为占位，无明确强制原则或 gate；本计划遵循项目通用规范（DRY/KISS/YAGNI、OpenSpec 流程）。未发现需豁免的复杂度违规。

## Project Structure

### Documentation (this feature)

```text
specs/001-fix-callback-reuse/
├── plan.md              # 本文件
├── research.md          # Phase 0 输出
├── data-model.md        # Phase 1 输出
├── quickstart.md        # Phase 1 输出
├── contracts/           # Phase 1 输出
└── tasks.md             # Phase 2 (/speckit.tasks 生成)
```

### Source Code (repository root)

```text
services/
├── api_gateway/app/         # FastAPI 入口与单任务执行、回调、状态管理
├── workers/                 # 各 Celery 节点实现（ffmpeg、audio_separator 等）
└── common/                  # 共享工具

docs/technical/reference/SINGLE_TASK_API_REFERENCE.md  # 单任务接口与节点文档
```

**Structure Decision**: 以现有 services/api_gateway + workers 架构为主，变更集中在单任务执行/回调/状态累积逻辑及文档。

## Complexity Tracking

无额外复杂度豁免需求。

# YiVideo 项目文档

本文档是 YiVideo 项目的中央索引，旨在为不同角色的团队成员提供清晰的指引。

## 📚 文档目录

### 🏗️ 架构设计 (`docs/architecture/`)
- **[SYSTEM_ARCHITECTURE.md](architecture/SYSTEM_ARCHITECTURE.md)** - 系统总体架构设计，了解项目核心组件和交互方式。
- **[WORKFLOW_ANALYSIS.md](architecture/WORKFLOW_ANALYSIS.md)** - 核心工作流深入分析，理解数据处理流程。
- **[SDD.md](architecture/SDD.md)** - 软件设计文档，包含关键模块的技术实现细节。

### 🚀 部署与配置 (`docs/deployment/`)
- **[DEPLOYMENT_GUIDE.md](deployment/DEPLOYMENT_GUIDE.md)** - 完整的生产环境部署指南。
- **[INDEXTTS_DEPLOYMENT.md](deployment/INDEXTTS_DEPLOYMENT.md)** - IndexTTS 服务专项部署与配置说明。

### 💻 开发指南 (`docs/development/`)
- **[INDEXTTS_SERVICE_GUIDE.md](development/INDEXTTS_SERVICE_GUIDE.md)** - IndexTTS 服务开发与集成指南。
- **[INDEXTTS_USER_GUIDE.md](development/INDEXTTS_USER_GUIDE.md)** - IndexTTS 服务 API 使用指南。
- **[INDEXTTS_CONFIG_GUIDE.md](development/INDEXTTS_CONFIG_GUIDE.md)** - IndexTTS 服务高级配置详解。
- **[WORKFLOW_EXAMPLES.md](development/WORKFLOW_EXAMPLES.md)** - 工作流配置示例与说明。
- **[PADDLEOCR_API_COMPATIBILITY_FIX.md](development/PADDLEOCR_API_COMPATIBILITY_FIX.md)** - PaddleOCR API 兼容性修复说明。

### 🔧 运维手册 (`docs/operations/`)
- **[OPERATIONS_MANUAL.md](operations/OPERATIONS_MANUAL.md)** - 系统日常运维手册，包含监控、备份等。
- **[SYSTEM_TROUBLESHOOTING_GUIDE.md](operations/SYSTEM_TROUBLESHOOTING_GUIDE.md)** - 通用故障排除指南，覆盖常见问题。

### 📖 参考资料 (`docs/reference/`)
- **[GPU_LOCK_COMPLETE_GUIDE.md](reference/GPU_LOCK_COMPLETE_GUIDE.md)** - GPU 锁系统设计与使用。
- **[faster_whisper_complete_parameter_guide.md](reference/faster_whisper_complete_parameter_guide.md)** - Faster-Whisper 模型参数详解。
- **[REDIS_OPTIMIZATION_SUMMARY.md](reference/REDIS_OPTIMIZATION_SUMMARY.md)** - Redis 性能优化实践。
- **[AUDIO_SPLIT_GUIDE.md](reference/AUDIO_SPLIT_GUIDE.md)** - FFMPEG 音频切分功能说明。
- **[SUBTITLE_KEYFRAME_EXTRACTION.md](reference/SUBTITLE_KEYFRAME_EXTRACTION.md)** - 字幕关键帧提取功能说明。
- **[module_dependencies.md](reference/module_dependencies.md)** - 核心 AI 模块依赖项清单。

### 📦 历史归档 (`docs/archive/`)
- 此目录存放项目过程中的历史文档，如产品需求（PRD）、分析报告、测试策略等。这些文档主要用于追溯历史，不代表项目当前状态。

---

## 🚀 快速开始

### 新用户推荐阅读顺序
1. **系统架构** → [SYSTEM_ARCHITECTURE.md](architecture/SYSTEM_ARCHITECTURE.md)
2. **部署指南** → [DEPLOYMENT_GUIDE.md](deployment/DEPLOYMENT_GUIDE.md)

### 开发人员推荐阅读顺序
1. **系统架构** → [SYSTEM_ARCHITECTURE.md](architecture/SYSTEM_ARCHITECTURE.md)
2. **部署指南** → [DEPLOYMENT_GUIDE.md](deployment/DEPLOYMENT_GUIDE.md)
3. **工作流示例** → [WORKFLOW_EXAMPLES.md](development/WORKFLOW_EXAMPLES.md)
4. **开发指南** → 浏览 `docs/development/` 下的相关文档。

### 运维人员推荐阅读顺序
1. **部署指南** → [DEPLOYMENT_GUIDE.md](deployment/DEPLOYMENT_GUIDE.md)
2. **运维手册** → [OPERATIONS_MANUAL.md](operations/OPERATIONS_MANUAL.md)
3. **故障排除** → [SYSTEM_TROUBLESHOOTING_GUIDE.md](operations/SYSTEM_TROUBLESHOOTING_GUIDE.md)

---

## 📋 文档维护

### 分类原则
- **architecture/**: 系统架构和高级设计文档。
- **deployment/**: 部署、安装和配置相关指南。
- **development/**: 针对特定服务的开发和使用指南。
- **operations/**: 日常运维、监控和故障排除手册。
- **reference/**: 具体技术点的参考资料和深度说明。
- **archive/**: 项目过程中的历史文档归档。

---
*最后更新: 2025-10-27 | 文档版本: 3.0*
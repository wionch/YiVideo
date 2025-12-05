# YiVideo 项目文档

本文档是 YiVideo 项目的中央索引，旨在为不同角色的团队成员提供清晰的指引。

## 📚 文档目录

### 🏗️ 产品与架构 (`docs/product/`)
- **[SDD.md](product/SDD.md)** - 软件设计文档
- **[SYSTEM_ARCHITECTURE.md](product/SYSTEM_ARCHITECTURE.md)** - 系统架构

### 🚀 技术文档 (`docs/technical/`)

#### 部署与配置 (`docs/technical/deployment/`)
- **[DEPLOYMENT_GUIDE.md](technical/deployment/DEPLOYMENT_GUIDE.md)** - 部署指南

#### 开发参考 (`docs/technical/reference/`)
- **[WORKFLOW_NODES_REFERENCE.md](technical/reference/WORKFLOW_NODES_REFERENCE.md)** - 工作流节点参考
- **[WORKFLOW_EXAMPLES_GUIDE.md](technical/reference/WORKFLOW_EXAMPLES_GUIDE.md)** - 工作流示例指南
- **[faster_whisper_complete_parameter_guide.md](technical/reference/faster_whisper_complete_parameter_guide.md)** - Faster Whisper参数详解
- **[GPU_LOCK_COMPLETE_GUIDE.md](technical/reference/GPU_LOCK_COMPLETE_GUIDE.md)** - GPU锁系统完整指南
- **[MINIO_DIRECTORY_UPLOAD_GUIDE.md](technical/reference/MINIO_DIRECTORY_UPLOAD_GUIDE.md)** - MinIO目录上传指南

#### 运维与排错 (`docs/technical/troubleshooting/`)
- **[SYSTEM_TROUBLESHOOTING_GUIDE.md](technical/troubleshooting/SYSTEM_TROUBLESHOOTING_GUIDE.md)** - 系统故障排除指南

### 🌐 API文档 (`docs/api/`)
- **[README.md](api/README.md)** - API文档总览
- **[WORKFLOW_API.md](api/WORKFLOW_API.md)** - 工作流API文档
- **[SINGLE_TASK_API.md](api/SINGLE_TASK_API.md)** - 单任务API文档
- **[FILE_OPERATIONS_API.md](api/FILE_OPERATIONS_API.md)** - 文件操作API文档
- **[MONITORING_API.md](api/MONITORING_API.md)** - 监控API文档
- **[QUICK_START.md](api/QUICK_START.md)** - API快速开始指南
- **[DELETE_directories.md](api/DELETE_directories.md)** - 删除本地目录API

---

## 🚀 快速开始

### 新用户推荐阅读顺序
1. **系统架构** → [SYSTEM_ARCHITECTURE.md](product/SYSTEM_ARCHITECTURE.md)
2. **部署指南** → [DEPLOYMENT_GUIDE.md](technical/deployment/DEPLOYMENT_GUIDE.md)
3. **API快速开始** → [QUICK_START.md](api/QUICK_START.md)
4. **API概览** → [README.md](api/README.md)

### 开发人员推荐阅读顺序
1. **系统架构** → [SYSTEM_ARCHITECTURE.md](product/SYSTEM_ARCHITECTURE.md)
2. **部署指南** → [DEPLOYMENT_GUIDE.md](technical/deployment/DEPLOYMENT_GUIDE.md)
3. **API快速开始** → [QUICK_START.md](api/QUICK_START.md)
4. **API文档总览** → [README.md](api/README.md)
5. **工作流API** → [WORKFLOW_API.md](api/WORKFLOW_API.md)
6. **单任务API** → [SINGLE_TASK_API.md](api/SINGLE_TASK_API.md)
7. **工作流示例** → [WORKFLOW_EXAMPLES_GUIDE.md](technical/reference/WORKFLOW_EXAMPLES_GUIDE.md)
8. **开发参考** → 浏览 `docs/technical/reference/` 下的相关文档。

### 运维人员推荐阅读顺序
1. **部署指南** → [DEPLOYMENT_GUIDE.md](technical/deployment/DEPLOYMENT_GUIDE.md)
2. **监控API** → [MONITORING_API.md](api/MONITORING_API.md)
3. **文件操作API** → [FILE_OPERATIONS_API.md](api/FILE_OPERATIONS_API.md)
4. **故障排除** → [SYSTEM_TROUBLESHOOTING_GUIDE.md](technical/troubleshooting/SYSTEM_TROUBLESHOOTING_GUIDE.md)

### API使用者推荐阅读顺序
1. **快速开始** → [QUICK_START.md](api/QUICK_START.md)
2. **API概览** → [README.md](api/README.md)
3. **根据需要选择**：
   - 工作流处理 → [WORKFLOW_API.md](api/WORKFLOW_API.md)
   - 单任务处理 → [SINGLE_TASK_API.md](api/SINGLE_TASK_API.md)
   - 文件管理 → [FILE_OPERATIONS_API.md](api/FILE_OPERATIONS_API.md)
   - 系统监控 → [MONITORING_API.md](api/MONITORING_API.md)

---

## 📋 文档维护

### 分类原则
- **product/**: 产品与架构设计文档，定义系统"是什么"。
- **technical/**: 技术实现文档，定义系统"怎么做"。
  - **deployment/**: 部署、安装和配置指南。
  - **reference/**: 具体技术点、核心模块的参考资料。
  - **troubleshooting/**: 日常运维、监控和故障排除手册。
- **api/**: API接口文档，提供完整的HTTP API使用指南和示例。
  - **概览文档**: API总体介绍、认证、错误处理
  - **模块文档**: 按功能模块分类的详细API文档
  - **指南文档**: 快速开始、最佳实践等

### API文档说明
API文档采用模块化结构，按功能领域划分为：
- **工作流API**: 动态编排和管理AI处理流程
- **单任务API**: 独立的单个任务执行
- **文件操作API**: MinIO存储和本地文件管理
- **监控API**: GPU锁监控和系统健康检查

所有API文档都包含：
- 完整的端点说明
- 请求/响应示例
- 错误处理指南
- 代码示例（cURL、Python）
- 最佳实践建议

---
*最后更新: 2025-12-05 | 文档版本: 4.0*
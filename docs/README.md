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

#### 运维与排错 (`docs/technical/troubleshooting/`)
- **[SYSTEM_TROUBLESHOOTING_GUIDE.md](technical/troubleshooting/SYSTEM_TROUBLESHOOTING_GUIDE.md)** - 系统故障排除指南

---

## 🚀 快速开始

### 新用户推荐阅读顺序
1. **系统架构** → [SYSTEM_ARCHITECTURE.md](product/SYSTEM_ARCHITECTURE.md)
2. **部署指南** → [DEPLOYMENT_GUIDE.md](technical/deployment/DEPLOYMENT_GUIDE.md)

### 开发人员推荐阅读顺序
1. **系统架构** → [SYSTEM_ARCHITECTURE.md](product/SYSTEM_ARCHITECTURE.md)
2. **部署指南** → [DEPLOYMENT_GUIDE.md](technical/deployment/DEPLOYMENT_GUIDE.md)
3. **工作流示例** → [WORKFLOW_EXAMPLES_GUIDE.md](technical/reference/WORKFLOW_EXAMPLES_GUIDE.md)
4. **开发参考** → 浏览 `docs/technical/reference/` 下的相关文档。

### 运维人员推荐阅读顺序
1. **部署指南** → [DEPLOYMENT_GUIDE.md](technical/deployment/DEPLOYMENT_GUIDE.md)
2. **故障排除** → [SYSTEM_TROUBLESHOOTING_GUIDE.md](technical/troubleshooting/SYSTEM_TROUBLESHOOTING_GUIDE.md)

---

## 📋 文档维护

### 分类原则
- **product/**: 产品与架构设计文档，定义系统“是什么”。
- **technical/**: 技术实现文档，定义系统“怎么做”。
  - **deployment/**: 部署、安装和配置指南。
  - **reference/**: 具体技术点、API、核心模块的参考资料。
  - **troubleshooting/**: 日常运维、监控和故障排除手册。

---
*最后更新: 2025-11-09 | 文档版本: 3.0*
# Inpainting Service 图像修复服务文档

> 🧭 **导航**: [YiVideo项目根](/mnt/d/WSL2/docker/YiVideo/CLAUDE.md) > [Workers目录](/mnt/d/WSL2/docker/YiVideo/services/workers/) > **inpainting_service**

## 服务概述

Inpainting Service提供图像修复功能，能够智能填补图像中的缺失区域或移除不需要的对象。该服务基于深度学习模型实现高质量的图像修复。

## 核心功能

- **图像修复**: 智能填补图像缺失区域
- **对象移除**: 移除图像中不需要的对象
- **背景补全**: 自动补全背景
- **边缘平滑**: 保持修复区域的自然过渡

## 目录结构

```
services/workers/inpainting_service/
├── Dockerfile
└── requirements.txt
```

## 依赖

```
# 图像修复相关依赖
torch
opencv-python
numpy
pydantic
```

## GPU要求

- **推荐**: 支持CUDA的GPU
- **显存**: ≥4GB

## 集成服务

- **状态管理**: `services.common.state_manager`
- **GPU锁**: `services.common.locks`

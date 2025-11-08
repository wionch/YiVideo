# GPT-SoVITS Service 语音克隆服务文档

> 🧭 **导航**: [YiVideo项目根](/mnt/d/WSL2/docker/YiVideo/CLAUDE.md) > [Workers目录](/mnt/d/WSL2/docker/YiVideo/services/workers/) > **gptsovits_service**

## 服务概述

GPT-SoVITS Service基于GPT-SoVITS模型实现语音克隆功能，能够使用少量样本声音训练并生成相似音色的语音。该服务支持个性化语音合成。

## 核心功能

- **语音克隆**: 使用样本声音进行语音克隆
- **少样本训练**: 仅需几秒音频即可训练
- **高保真度**: 生成高质量的克隆语音
- **情感保持**: 保持原声音的情感特征

## 目录结构

```
services/workers/gptsovits_service/
├── Dockerfile
└── (其他文件待补充)
```

## 功能特性

- 零样本语音合成
- 少样本语音训练
- 跨语言语音克隆
- 实时推理

## 依赖

```
# GPT-SoVITS相关依赖
torch
torchaudio
```

## GPU要求

- **必需**: 支持CUDA的GPU
- **显存**: ≥8GB

## 集成服务

- **状态管理**: `services.common.state_manager`
- **GPU锁**: `services.common.locks`

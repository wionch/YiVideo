# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

YiVideo 是一个基于微服务架构的 AI 视频处理工作流引擎，主要功能是自动化视频字幕提取、翻译、配音和本地化处理。系统采用动态工作流引擎设计，通过配置驱动而非硬编码的方式来编排各种AI功能。

## 核心架构

### 微服务架构
- **API网关** (`services/api_gateway/`): 系统入口，基于 FastAPI + Gunicorn，负责接收请求和动态构建工作流
- **AI工作节点**: 7个专门的AI服务，通过 Celery 任务队列协调
- **基础设施**: Redis (消息代理/状态存储) + 共享存储 `/share`

### 关键组件
1. **ffmpeg_service**: 视频解码和处理
2. **paddleocr_service**: OCR字幕识别（核心服务）
3. **whisperx_service**: 语音识别(ASR)
4. **llm_service**: 大语言模型调用(Gemini, DeepSeek)
5. **inpainting_service**: 硬字幕去除
6. **indextts_service**: IndexTTS语音合成
7. **gptsovits_service**: GPT-SoVITS语音合成

## 开发命令

### 环境检查
```bash
python check_env.py  # 检查CUDA、PyTorch、PaddlePaddle等环境
```

### 容器化部署
```bash
# 构建并启动所有服务
docker-compose up -d

# 重新构建特定服务
docker-compose build paddleocr_service

# 查看服务日志
docker-compose logs -f api_gateway
```

### 独立脚本运行
```bash
# 字幕提取（独立运行）
python extract_subtitles.py -i videos/example.mp4 -o output/ --lang en

# 使用自定义配置
python extract_subtitles.py -i videos/example.mp4 --config custom_config.yml
```

### 测试命令
```bash
# 运行环境检查
python check_env.py

# 运行特定服务测试
cd services/workers/paddleocr_service && python test.py
```

## 技术栈和依赖

### AI框架
- **PyTorch生态系统**: torch, torchvision, torchaudio
- **PaddlePaddle**: paddlepaddle-gpu==2.5.2 (版本锁定)
- **关键AI库**: PaddleOCR (>=2.7.0), WhisperX, audio-separator

### 视频处理
- **FFmpeg**: 自编译支持CUDA加速
- **视频IO**: yt-dlp, av (FFmpeg Python绑定)
- **图像处理**: opencv-python-headless

### 系统架构
- **消息队列**: Redis + Celery
- **Web框架**: FastAPI + Gunicorn
- **配置管理**: YAML (config.yml)

## 配置系统

### 主配置文件 `config.yml`
配置文件分为9个模块：
1. **core**: 系统核心配置 (工作流TTL、临时文件清理)
2. **redis**: Redis连接和数据库分配
3. **decoder**: GPU解码批处理大小
4. **area_detector**: 字幕区域检测参数
5. **keyframe_detector**: 关键帧检测算法参数
6. **ocr**: OCR识别和PaddleOCR详细配置
7. **postprocessor**: 后处理过滤参数
8. **pipeline**: 流水线控制策略
9. **llm_service/whisperx_service**: 外部AI服务配置

### 动态工作流配置
工作流通过 `workflow_config` 动态构建：
```python
workflow_config = {
    "workflow_chain": [
        "ffmpeg.extract_keyframes",
        "paddleocr.recognize_subtitles",
        "llm.translate_text",
        "indextts.generate_speech"
    ]
}
```

## 核心功能模块

### PaddleOCR服务 (核心)
- **字幕区域检测**: 智能识别视频中的字幕位置
- **关键帧检测**: 基于感知哈希的帧变化检测
- **OCR识别**: 多语言文字识别，针对字幕场景优化
- **后处理**: 时间轴合并和过滤

### 视频解码
- **GPU加速解码**: 支持CUDA硬件加速
- **批处理**: 优化显存使用和解码效率
- **多格式支持**: 通过FFmpeg支持各种视频格式

### API接口
- **POST /v1/workflows**: 创建工作流
- **GET /v1/workflows/status/{workflow_id}**: 查询状态

## 开发注意事项

### GPU资源管理
- 多个服务竞争GPU资源，需要合理分配
- 使用 `NVIDIA_VISIBLE_DEVICES` 环境变量控制
- 显存占用监控很重要

### 共享存储
- 所有服务通过 `/share` 目录交换文件
- 临时文件管理通过 `/tmp` 目录
- 考虑磁盘空间，配置 `cleanup_temp_files`

### 配置优化
- PaddleOCR配置针对字幕场景高度优化
- 关键帧检测算法经过调优，避免重复字幕
- 支持多语言OCR模型选择

### 错误处理
- 使用统一的日志系统 (`services.common.logger`)
- 分布式锁机制 (`services.common.locks`)
- 状态管理通过Redis存储

## 文档结构

项目包含完整的技术文档：
- `docs/PRD.md`: 产品需求文档
- `docs/SYSTEM_ARCHITECTURE.md`: 系统架构设计
- `docs/SDD.md`: 系统设计文档
- `docs/TESTING_STRATEGY.md`: 测试策略
- `docs/CODE_IMPLEMENTATION_ROADMAP.md`: 实现路线图

## 常见问题

### 环境问题
- 使用 `check_env.py` 检查环境兼容性
- PaddlePaddle版本需要与CUDA版本匹配
- 确保GPU驱动版本正确

### 性能优化
- 调整 `decoder.batch_size` 平衡速度和显存
- 优化 `keyframe_detector.similarity_threshold` 避免重复处理
- 合理配置并发工作进程数

### 调试技巧
- 查看容器日志: `docker-compose logs -f [service_name]`
- 临时文件保留: 设置 `core.cleanup_temp_files: false`
- 使用Redis状态存储查询执行状态
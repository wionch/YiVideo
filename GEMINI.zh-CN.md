# GEMINI 项目背景: Video2Subtitle

## 项目概述

本项目 "Video2Subtitle" 是一个工业级的视频字幕提取流水线。它使用 Python 编写，并利用强大的 PaddleOCR 库对视频帧进行光学字符识别（OCR）。整个工作流被设计在 Docker 容器中高效运行，并利用 NVIDIA GPU 进行加速。

该流水线的架构是模块化的，将复杂的字幕提取任务分解为几个独立的阶段：

1.  **视频解码器 (Video Decoder):** 将视频文件解码为用于处理的原始帧。
2.  **字幕区域检测器 (Subtitle Area Detector):** 分析视频中的采样帧，自动识别字幕显示的屏幕区域。
3.  **变化检测器 (Change Detector):** 智能地识别字幕文本发生变化的那些关键帧。这避免了对静态帧进行重复的 OCR 处理，从而显著提高性能。
4.  **OCR 识别 (OCR Recognition):** 使用 PaddleOCR 对识别出的关键帧执行核心的文本识别。可以配置为本地实例运行，或连接到专用的、高性能的 OCR 服务器。
5.  **后处理器 (Post-processor):** 清理和优化原始的 OCR 输出，合并文本块并过滤噪声，以生成精确、干净的字幕时间线。

最终输出的是一个结构化的 JSON 文件（`.precise.json`），其中包含提取的字幕文本和精确的时间戳。

## 构建与运行

该项目旨在使用 Docker 和 Docker Compose 进行构建和运行，以确保环境的一致性和可复现性。

### 1. 构建 Docker 镜像

使用提供的 `docker-compose.yml` 文件构建镜像。此命令会根据 `Dockerfile` 中的定义，将应用程序及其所有依赖项打包。

```bash
docker-compose build
```

### 2. 启动服务容器

以分离模式（detached mode）启动应用容器。这将启动服务并使其在后台保持运行。默认命令 (`tail -f /dev/null`) 会使容器保持活动状态，允许您在其中执行命令。

```bash
docker-compose up -d
```

### 3. 执行字幕提取流水线

使用 `docker exec` 在正在运行的容器内部执行主流水线脚本。您需要提供输入视频的路径。项目结构中包含一个 `/videos` 目录，这是存放输入文件的预定位置。

```bash
# 示例：处理位于 'videos' 目录中名为 'test.mp4' 的视频
docker exec -it Video2Subtitle python run_pipeline.py -i /app/videos/test.mp4 --config /app/config.yml
```

提取的字幕将作为 `.precise.json` 文件保存在与视频相同的目录中。

## 开发约定

*   **配置:** 所有流水线的行为都通过 `config.yml` 文件进行控制。这使得在不更改代码的情况下，可以轻松调整不同模块的参数（例如，检测灵敏度、OCR 语言、批处理大小）。
*   **OCR 模式:** 流水线支持两种 OCR 处理模式，在 `config.yml` 中配置：
    *   **本地模式 (`ocr_server.enabled: false`):** 在主流水线进程中直接创建一个 PaddleOCR 实例。适用于较简单的任务或开发。
    *   **服务模式 (`ocr_server.enabled: true`):** 流水线作为客户端，将 OCR 请求发送到专用的 PaddleOCR 服务端点（例如 `http://ocr-server:8868/predict/ocr_system`）。这是高吞吐量和并发处理的推荐方法。请注意，提供的 `docker-compose.yml` 未定义 `ocr-server` 服务，需要单独运行。
*   **依赖管理:** 核心的 Python 依赖项通过 `PaddleOCR/requirements.txt` 文件进行管理。`Dockerfile` 负责安装这些依赖。
*   **代码结构:** 主要的应用逻辑封装在 `pipeline` 目录中，`run_pipeline.py` 作为执行的主要入口点。项目包含了 `PaddleOCR` 仓库的完整副本，表明与该库有深度集成。

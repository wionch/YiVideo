# AI 微服务

此目录包含项目所需的所有独立AI微服务。每个服务都在其自己的目录中定义，并拥有独立的 `Dockerfile`。

## 架构

所有服务均基于项目根目录下的 `Dockerfile.base` 构建。这种方法确保了所有服务共享一个统一的、包含CUDA、Python和FFmpeg等核心依赖的基础环境，从而大大减少了磁盘空间的占用。

每个服务的 `Dockerfile` 只负责在其继承的基础镜像之上，安装该服务特有的依赖。

## 服务列表

- `paddleocr_service`: 提供 OCR 服务。
- `inpainting_service`: 提供视频修复（硬字幕去除）服务。
- `whisperx_service`: 提供 ASR 服务。
- `indextts_service`: 提供 TTS 服务 (IndexTTS方案)。
- `gptsovits_service`: 提供 TTS 服务 (GPT-SoVITS方案)。

## 如何使用

所有这些服务都被定义在项目根目录的 `docker-compose.services.yml` 文件中（或已整合进主 `docker-compose.yml`）。

你可以通过标准的 `docker-compose` 命令来构建和运行这些服务：

```bash
# 构建所有服务
docker-compose -f docker-compose.services.yml build

# 启动所有服务 (在后台)
docker-compose -f docker-compose.services.yml up -d

# 停止所有服务
docker-compose -f docker-compose.services.yml down
```

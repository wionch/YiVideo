# Audio Separator Service

基于 `audio-separator` 命令行工具的音频分离服务，支持使用 Demucs、MDX-Net、BS-Roformer 等多种模型进行人声和背景声分离。

## 功能特性

- 🎵 支持多种主流音频分离模型
  - **Demucs**: Facebook 开源的高质量音频分离模型
  - **MDX-Net**: 专业的音乐分离模型
  - **MDX23C**: 高质量MDX模型变体
  - **BS-Roformer**: 默认推荐模型
- 🚀 GPU 加速支持 (通过 NVIDIA Docker)
- 📁 自动文件管理和输出组织
- 🔧 灵活的配置选项
- 📊 详细的处理日志
- 🐳 基于 `beveradb/audio-separator:gpu` 官方镜像

## 文件结构

```
services/workers/audio_separator_service/
├── separate_audio.py          # 主要分离脚本
├── run_separation.sh          # 启动脚本
├── README.md                  # 说明文档
└── output/                    # 输出目录
    ├── 223_demucs/           # Demucs模型输出
    ├── 223_mdx_net/          # MDX-Net模型输出
    ├── 223_mdx23c/           # MDX23C模型输出
    └── 223_bs_roformer/      # BS-Roformer模型输出
```

## 快速开始

### 1. 使用 Docker Compose 启动

```bash
# 在项目根目录下运行
docker-compose -f docker-compose_pas.yml up -d audio_separator_service
```

### 2. 进入容器执行分离

```bash
# 进入容器
docker exec -it audio_separator_pas bash

# 运行分离脚本
cd /workspace
./run_separation.sh
```

### 3. 查看输出结果

输出文件保存在以下位置：
- 容器内：`/workspace/output/`
- 宿主机：`services/workers/audio_separator_service/output/`

## 脚本使用方法

### separate_audio.py

主分离脚本，支持命令行参数：

```bash
# 使用所有模型分离默认文件 (videos/223.wav)
python3 separate_audio.py

# 指定输入文件
python3 separate_audio.py /path/to/audio.wav

# 使用特定模型
python3 separate_audio.py --model demucs
python3 separate_audio.py --model mdx_net
python3 separate_audio.py --model mdx23c
python3 separate_audio.py --model bs_roformer

# 列出所有可用模型
python3 separate_audio.py --list-models

# 列出audio-separator支持的所有模型
python3 separate_audio.py --list-audio-separator-models
```

### run_separation.sh

便捷启动脚本，自动处理 `videos/223.wav`：

```bash
# 直接运行
./run_separation.sh
```

脚本功能：
- ✅ 检查GPU状态
- ✅ 验证audio-separator命令可用性
- ✅ 使用所有模型进行分离
- ✅ 显示输出文件信息

## 模型配置

### Demucs 模型
- **文件**: `htdemucs_ft.yaml`
- **特点**: 高质量，适合各种音频类型
- **参数**:
  - `demucs_segment_size`: 256
  - `demucs_shifts`: 2
  - `demucs_overlap`: 0.25

### MDX-Net 模型
- **文件**: `UVR_MDXNET_KARA_2.onnx`
- **特点**: 专门优化的人声分离
- **参数**:
  - `mdx_segment_size`: 224
  - `mdx_overlap`: 0.25
  - `mdx_batch_size`: 1

### MDX23C 模型
- **文件**: `MDX23C-InstVoc HQ.onnx`
- **特点**: 高质量MDX模型变体
- **参数**:
  - `mdx_segment_size`: 256
  - `mdx_overlap`: 0.25
  - `mdx_batch_size`: 1

### BS-Roformer 模型
- **文件**: `model_bs_roformer_ep_317_sdr_12.9755.ckpt`
- **特点**: 默认推荐模型，性能均衡
- **参数**:
  - `mdx_segment_size`: 256
  - `mdx_overlap`: 0.25

## 输出格式

每个模型会生成以下文件：
- `vocals_{model_name}.wav` - 人声轨道
- `other_{model_name}.wav` - 背景音乐/伴奏轨道
- `no_drums_{model_name}.wav` - 无鼓声轨道（如果模型支持）

文件命名示例：
```
output/223_demucs/
├── vocals_demucs.wav
├── other_demucs.wav
└── no_drums_demucs.wav

output/223_mdx_net/
├── vocals_mdx_net.wav
└── other_mdx_net.wav
```

## 系统要求

- **Docker**: 20.10+
- **NVIDIA Docker**: 支持GPU加速
- **显存**: 建议 4GB+ VRAM
- **内存**: 建议 8GB+ RAM
- **存储**: 足够空间存放输出文件

## 故障排除

### 常见问题

1. **GPU 不可用**
   ```bash
   # 检查 NVIDIA Docker 支持
   docker run --rm --gpus all nvidia/cuda:11.0-base nvidia-smi
   ```

2. **内存不足**
   - 减小模型参数配置
   - 使用更小的 segment_size

3. **输入文件问题**
   ```bash
   # 检查文件格式
   ffprobe /app/videos/223.wav
   ```

4. **权限问题**
   ```bash
   # 确保脚本有执行权限
   chmod +x run_separation.sh
   ```

### 日志查看

```bash
# 查看分离日志
docker exec audio_separator_pas tail -f /app/audio_separator.log

# 查看容器日志
docker logs -f audio_separator_pas
```

## 性能优化

1. **GPU 优化**
   - 确保 CUDA 版本匹配
   - 监控 GPU 内存使用

2. **批量处理**
   - 修改脚本支持多文件处理
   - 使用并行处理

3. **参数调优**
   - 根据音频类型调整 segment_size
   - 优化 overlap 参数

## 开发说明

### 添加新模型

1. 在 `models_config` 中添加配置
2. 更新 `setup_separator` 方法
3. 测试模型性能

### 自定义输出

修改 `separate_audio.py` 中的输出路径和命名规则。

## 相关链接

- [python-audio-separator GitHub](https://github.com/nomadkaraoke/python-audio-separator)
- [Demucs 项目](https://github.com/facebookresearch/demucs)
- [Spleeter 项目](https://github.com/deezer/spleeter)
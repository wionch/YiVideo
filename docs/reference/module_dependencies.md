# AI 模块依赖项最终清单

本文档根据最终确认的信息，记录项目中各个独立AI服务模块的手动安装依赖项。

---

## 1. PaddleOCR

- **源码仓库**: [https://github.com/PaddlePaddle/PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR)
- **安装指令**:
  ```bash
  pip install paddlepaddle-gpu # 版本需与基础镜像的CUDA版本匹配
  pip install paddleocr
  ```
- **说明**: 服务化将通过在代码中调用 `PaddleOCR()` 类来实现，而不是 `hubserving`。

---

## 2. InpaintMode (视频修复算法)

- **说明**: 这是 `video-subtitle-remover` 功能的核心，由多个模型组成。它们将被整合到同一个 `inpainting` 服务中。

### 2.1. STTN
- **源码仓库**: [https://github.com/researchmm/STTN](https://github.com/researchmm/STTN)
- **依赖核心**: PyTorch。具体依赖项需从 `environment.yml` 文件转换。

### 2.2. LAMA
- **源码仓库**: [https://github.com/saic-mdal/lama](https://github.com/saic-mdal/lama)
- **依赖核心**:
  ```bash
  pip install torch==1.8.0 torchvision==0.9.0
  # 其余依赖在 requirements.txt 中
  ```

### 2.3. PROPAINTER
- **源码仓库**: [https://github.com/sczhou/ProPainter](https://github.com/sczhou/ProPainter)
- **依赖核心**: PyTorch >= 1.7.1。依赖项繁多，包含从 git 直接安装的包。

---

## 3. WhisperX

- **源码仓库**: [https://github.com/m-bain/whisperX](https://github.com/m-bain/whisperX)
- **安装指令**:
  ```bash
  ```
- **系统依赖**: `ffmpeg` (应已包含在基础镜像中)。

---

## 4. IndexTTS

- **源码仓库**: [https://github.com/index-tts/index-tts](https://github.com/index-tts/index-tts)
- **安装指令**:
  ```bash
  # 1. 安装 torch
  pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118
  
  # 2. 克隆并安装源码
  git clone https://github.com/index-tts/index-tts
  cd index-tts
  pip install -e .
  ```
- **模型下载**:
  ```bash
  huggingface-cli download IndexTeam/IndexTTS-1.5 --local-dir checkpoints --exclude "*.flac" "*.wav"
  ```

---

## 5. GPT-SoVITS

- **源码仓库**: [https://github.com/RVC-Boss/GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS)
- **安装指令**:
  ```bash
  git clone https://github.com/RVC-Boss/GPT-SoVITS
  cd GPT-SoVITS
  # 基础镜像为 CU118，因此这里选择最接近的 CUDA 版本或尝试通用 GPU 选项
  bash install.sh --device CU121 --source HF
  ```
- **说明**: `install.sh` 脚本支持 `CU121`, `CU128`, `ROCM`, `CPU`。我们选择 `CU121` 作为最接近 `CU118` 的选项进行尝试，因为 PyTorch 具有向后兼容性。如果失败，将需要回退到手动安装依赖。

---

## 6. WService 字幕优化模块

- **服务路径**: `services/workers/wservice/`
- **核心模块**: `services/common/subtitle/`
- **功能**: AI字幕优化功能，支持错别字修正、语法优化、标点补充和口头禅过滤

### 6.1. 核心依赖模块

#### 6.1.1. 字幕优化器 (subtitle_optimizer.py)
- **路径**: `services/common/subtitle/subtitle_optimizer.py`
- **功能**: 主要优化器，整合工作流
- **依赖**:
  - `subtitle_extractor`: 字幕数据提取
  - `ai_providers`: AI提供商工厂
  - `concurrent_batch_processor`: 并发批处理器
  - `metrics`: Prometheus指标

#### 6.1.2. AI提供商工厂 (ai_providers.py)
- **路径**: `services/common/subtitle/ai_providers.py`
- **功能**: 支持5种AI提供商（DeepSeek、Gemini、智谱、火山、OpenAI兼容）
- **依赖**:
  ```python
  # 内置支持，无需额外安装
  # 支持HTTP API调用
  import httpx  # HTTP客户端
  import json   # JSON处理
  ```

#### 6.1.3. 并发批处理器 (concurrent_batch_processor.py)
- **路径**: `services/common/subtitle/concurrent_batch_processor.py`
- **功能**: 大体积字幕并发处理，滑窗重叠分段
- **依赖**:
  ```python
  import asyncio       # 异步处理
  import aiohttp       # 异步HTTP客户端
  from concurrent.futures import ThreadPoolExecutor
  ```

#### 6.1.4. 指令解析器 (ai_command_parser.py)
- **路径**: `services/common/subtitle/ai_command_parser.py`
- **功能**: 解析AI响应中的优化指令
- **依赖**:
  ```python
  import re           # 正则表达式
  import json         # JSON解析
  ```

#### 6.1.5. 指令执行器 (command_executor.py)
- **路径**: `services/common/subtitle/command_executor.py`
- **功能**: 执行4种优化指令（MOVE/UPDATE/DELETE/PUNCTUATE）
- **依赖**:
  ```python
  # 纯Python实现，无外部依赖
  ```

#### 6.1.6. 滑窗分段器 (sliding_window_splitter.py)
- **路径**: `services/common/subtitle/sliding_window_splitter.py`
- **功能**: 滑窗重叠分段机制
- **依赖**:
  ```python
  # 纯Python实现，无外部依赖
  ```

#### 6.1.7. 指标收集器 (metrics.py)
- **路径**: `services/common/subtitle/metrics.py`
- **功能**: Prometheus指标收集
- **依赖**:
  ```python
  from prometheus_client import Counter, Histogram, Gauge
  ```

### 6.2. 安装说明

WService的字幕优化模块**无需额外安装依赖**，因为：

1. **核心功能**完全使用Python标准库实现
2. **网络请求**使用内置的`http.client`或`urllib`
3. **并发处理**使用`concurrent.futures`
4. **Prometheus指标**使用项目已有的`prometheus_client`

### 6.3. API提供商配置

#### DeepSeek
- **环境变量**: `DEEPSEEK_API_KEY`
- **API端点**: `https://api.deepseek.com/v1/chat/completions`
- **模型**: `deepseek-chat`
- **配置示例**:
  ```python
  config = {
      "api_key": "sk-your-key",
      "base_url": "https://api.deepseek.com/v1",
      "model": "deepseek-chat"
  }
  ```

#### Gemini
- **环境变量**: `GEMINI_API_KEY`
- **API端点**: `https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent`
- **模型**: `gemini-pro`
- **配置示例**:
  ```python
  config = {
      "api_key": "your-key",
      "base_url": "https://generativelanguage.googleapis.com/v1beta",
      "model": "gemini-pro"
  }
  ```

#### 智谱AI
- **环境变量**: `ZHIPU_API_KEY`
- **API端点**: `https://open.bigmodel.cn/api/paas/v4/chat/completions`
- **模型**: `glm-4`
- **配置示例**:
  ```python
  config = {
      "api_key": "your-key",
      "base_url": "https://open.bigmodel.cn/api/paas/v4",
      "model": "glm-4"
  }
  ```

#### 火山引擎
- **环境变量**: `VOLCENGINE_API_KEY`
- **API端点**: `https://ark.cn-beijing.volces.com/api/v3/chat/completions`
- **模型**: `ep-20241017205325-9h7gd`
- **配置示例**:
  ```python
  config = {
      "api_key": "your-key",
      "base_url": "https://ark.cn-beijing.volces.com/api/v3",
      "model": "ep-20241017205325-9h7gd"
  }
  ```

#### OpenAI兼容
- **环境变量**: `OPENAI_COMPATIBLE_KEY`
- **API端点**: 可配置（如：`https://api.openai.com/v1`）
- **模型**: 可配置（如：`gpt-4`, `gpt-3.5-turbo`）
- **配置示例**:
  ```python
  config = {
      "api_key": "sk-your-key",
      "base_url": "https://api.openai.com/v1",
      "model": "gpt-4"
  }
  ```

### 6.4. 使用方法

#### Celery任务调用
```python
from services.workers.wservice.app.tasks import ai_optimize_subtitles

result = ai_optimize_subtitles.delay(context)
```

#### 直接使用优化器
```python
from services.common.subtitle.subtitle_optimizer import SubtitleOptimizer

optimizer = SubtitleOptimizer(
    provider="deepseek",
    batch_size=50,
    overlap_size=10
)
result = optimizer.optimize(segments_data, output_path)
```

### 6.5. 系统要求

- **Python版本**: 3.8+
- **内存要求**:
  - 小文件: 200MB
  - 中文件: 500MB
  - 大文件: 2GB+
- **网络要求**: 稳定的互联网连接（调用AI API）
- **存储要求**: 足够的临时存储空间（用于生成优化文件）

### 6.6. 监控和维护

#### 性能指标
- `ai_subtitle_optimization_requests_total`: 总请求数
- `ai_subtitle_optimization_duration_seconds`: 处理时间
- `ai_subtitle_optimization_errors_total`: 错误数
- `ai_subtitle_optimization_segments_count`: 处理片段数
- `ai_subtitle_optimization_commands_applied`: 应用指令数

#### 日志
- 位置: `/var/log/wservice/`
- 级别: INFO, DEBUG, ERROR
- 轮转: 每日轮转，保留30天

#### 故障排除
1. **检查API密钥**: 确保环境变量正确配置
2. **监控网络**: 确保可以访问AI提供商API
3. **检查存储空间**: 确保有足够空间存储优化文件
4. **查看日志**: 检查错误详情和堆栈信息
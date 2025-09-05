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
  pip install whisperx
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
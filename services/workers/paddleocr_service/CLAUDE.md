# PaddleOCR Service OCR服务文档

> 🧭 **导航**: [YiVideo项目根](/mnt/d/WSL2/docker/YiVideo/CLAUDE.md) > [Workers目录](/mnt/d/WSL2/docker/YiVideo/services/workers/) > **paddleocr_service**

## 服务概述

PaddleOCR Service基于PaddleOCR实现光学字符识别功能，能够从视频帧或图片中提取文字内容。该服务支持多语言OCR、版面分析和关键帧检测。

## 核心功能

- **文字识别**: 从图像中提取文字
- **关键帧检测**: 自动检测包含文字的关键帧
- **区域检测**: 识别文字区域边界
- **版面分析**: 分析文字布局和结构
- **多语言支持**: 支持中英文等多语言识别

## 目录结构

```
services/workers/paddleocr_service/
├── app/
│   ├── executor_area_detection.py     # 区域检测执行器
│   ├── executor_ocr.py               # OCR执行器
│   ├── executor_stitch_images.py     # 图像拼接执行器
│   ├── modules/
│   │   ├── area_detector.py          # 区域检测器
│   │   ├── base_detector.py          # 基础检测器
│   │   ├── change_detector.py        # 变化检测器
│   │   ├── decoder.py                # 解码器
│   │   ├── keyframe_detector.py      # 关键帧检测器
│   │   ├── ocr.py                    # OCR核心
│   │   └── postprocessor.py          # 后处理器
│   ├── utils/
│   │   ├── config_loader.py          # 配置加载器
│   │   └── progress_logger.py        # 进度日志
│   └── tasks.py                      # Celery任务定义
├── Dockerfile
└── requirements.txt
```

## 核心文件

### tasks.py
- **主要任务**: 本服务的核心逻辑被拆分为一个四阶段的OCR流水线，以提高处理效率和鲁棒性。
  - `detect_subtitle_area()`: **1. 字幕区域检测**。分析来自`ffmpeg_service`的关键帧，自动定位视频中字幕的精确位置（边界框）。
  - `create_stitched_images()`: **2. 图像拼接**。根据检测到的字幕区域，从视频中裁剪出每一帧的字幕条，并将它们并发地拼接成若干张大图，为批量OCR做准备。
  - `perform_ocr()`: **3. 执行OCR**。在拼接后的大图上运行PaddleOCR引擎，高效地识别所有文字内容。
  - `postprocess_and_finalize()`: **4. 后处理与生成**。对原始OCR结果进行清理、排序和格式化，应用时间戳，最终生成标准的SRT和JSON格式的字幕文件。

### modules/
**area_detector.py**: 区域检测器
- 文字区域定位
- 边界框生成
- 置信度评估

**ocr.py**: OCR核心引擎
- 文字检测
- 文字识别
- 后处理优化

**postprocessor.py**: 后处理器
- OCR结果格式化
- 时间戳计算
- 字幕合并与排序

## 依赖

```
celery
redis
paddlepaddle
paddleocr
opencv-python
numpy
pydantic
```

## GPU要求

- **可选**: 支持CUDA的GPU（推荐）
- **CPU**: 也支持CPU推理（较慢）

## 任务接口

### 工作流调用
此服务的任务通常作为一个序列链在工作流中被调用，而不是单个独立任务。一个典型的`paddleocr`工作流配置如下：

```yaml
# 在工作流配置文件中的示例
workflow_chain:
  # ... 其他前置任务 ...
  - task: paddleocr.detect_subtitle_area
    params: {}
  - task: paddleocr.create_stitched_images
    params: {}
  - task: paddleocr.perform_ocr
    params: {}
  - task: paddleocr.postprocess_and_finalize
    params: {}
  # ... 其他后置任务 ...
```

每个任务都接收标准的`context`字典，并将其处理结果注入上下文，供下一个任务使用。

## 输出格式

```json
{
  "ocr_results": [
    {
      "timestamp": 10.5,
      "text": "提取的文字内容",
      "bbox": [x1, y1, x2, y2],
      "confidence": 0.95
    }
  ]
}
```

## 共享存储

- **输入**: `/share/workflows/{workflow_id}/frames/`
- **输出**: `/share/workflows/{workflow_id}/ocr/`
- **中间文件**: `/share/workflows/{workflow_id}/temp/`

## 集成服务

- **视频处理**: `ffmpeg_service`
- **状态管理**: `services.common.state_manager`

## 性能优化

1. **批处理**: 批量处理提高速度
2. **关键帧过滤**: 只处理关键帧
3. **GPU加速**: 使用PaddlePaddle GPU版本

## 相关文档

- [PaddleOCR官方文档](https://github.com/PaddlePaddle/PaddleOCR)

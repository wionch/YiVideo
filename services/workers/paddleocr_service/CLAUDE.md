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
- **主要任务**:
  - `ocr_extraction()`: OCR提取任务
  - `keyframe_detection()`: 关键帧检测

### modules/
**keyframe_detector.py**: 关键帧检测器
- 变化检测
- 文字出现检测
- 时间间隔分析

**ocr.py**: OCR核心引擎
- 文字检测
- 文字识别
- 后处理优化

**area_detector.py**: 区域检测器
- 文字区域定位
- 边界框生成
- 置信度评估

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

### 标准任务接口
```python
@celery_app.task(bind=True)
def ocr_extraction(self, context):
    """
    OCR提取任务

    Args:
        context: 工作流上下文，包含:
            - video_path: 视频文件路径
            - languages: 语言列表
            - use_gpu: 是否使用GPU

    Returns:
        更新后的context，包含ocr_results
    """
    pass
```

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

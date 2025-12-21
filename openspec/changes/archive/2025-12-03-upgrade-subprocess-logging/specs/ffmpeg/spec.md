# 能力变更：FFmpeg 实时日志输出系统

## 变更概述

对 FFmpeg 音视频处理能力进行全面改进，实现音频提取、视频解码和字幕裁剪任务的实时日志输出，提升 GPU 任务执行的可视化和监控能力。

## MODIFIED Requirements

### Requirement: FFmpeg 音频提取任务

ffmpeg 服务 SHALL 通过 subprocess.Popen 启动 ffmpeg 进程，实时输出音频提取过程日志，同时保持与原实现完全兼容的执行结果。

#### Scenario: 音频提取正常执行

-   **GIVEN** 有效的视频文件路径和 ffmpeg 环境
-   **WHEN** 执行 ffmpeg.extract_audio 任务
-   **THEN** 实时输出 ffmpeg 音频提取过程日志，包括格式解析、编码转换、进度显示等步骤
-   **AND** 最终生成与原实现完全相同的音频文件
-   **AND** 支持 30 分钟超时控制和文件完整性验证

#### Scenario: 音频提取执行异常

-   **GIVEN** 视频文件格式不支持或文件损坏
-   **WHEN** 执行 ffmpeg.extract_audio 任务
-   **THEN** 实时输出 ffmpeg 错误信息，包括具体失败原因和编码参数
-   **AND** 抛出与原实现相同的异常类型和错误信息
-   **AND** 清理临时生成的音频文件

### Requirement: FFmpeg 字幕裁剪任务

ffmpeg 服务 SHALL 通过 subprocess.Popen 启动视频解码脚本，实时输出字幕裁剪过程日志，同时保持与原实现完全兼容的执行结果。

#### Scenario: 字幕裁剪正常执行

-   **GIVEN** 有效的视频文件、字幕区域坐标和 GPU 环境
-   **WHEN** 执行 ffmpeg.crop_subtitle_images 任务
-   **THEN** 实时输出字幕裁剪过程日志，包括视频解码、区域裁剪、图像保存等步骤
-   **AND** 最终生成与原实现完全相同的裁剪图像序列
-   **AND** 支持 30 分钟超时控制和 GPU 锁机制

#### Scenario: 字幕裁剪执行异常

-   **GIVEN** 视频文件损坏或字幕区域坐标无效
-   **WHEN** 执行 ffmpeg.crop_subtitle_images 任务
-   **THEN** 实时输出详细的错误诊断信息和 GPU 内存状态
-   **AND** 抛出与原实现相同的异常类型和错误信息
-   **AND** 清理部分完成的裁剪图像和 GPU 资源

### Requirement: FFmpeg 关键帧提取

ffmpeg 服务 SHALL 在视频解码过程中实时输出处理日志，同时保持与原实现完全兼容的执行结果。

#### Scenario: 关键帧提取正常执行

-   **GIVEN** 有效的视频文件路径和采样参数
-   **WHEN** 执行 ffmpeg.extract_keyframes 任务
-   **THEN** 实时输出视频解码和帧采样过程日志，包括解码进度、帧提取、图像保存等步骤
-   **AND** 最终生成与原实现完全相同的关键帧图像
-   **AND** 支持 30 分钟超时控制和文件完整性验证

## 兼容性要求

### 接口兼容性

-   所有现有 Celery 任务接口保持不变
-   函数签名和参数列表完全一致
-   返回值格式和字段含义不变
-   异常抛出时机和类型不变

### 执行结果兼容性

-   音频文件格式和质量保持不变
-   裁剪图像的像素级一致性
-   关键帧提取的精确性不变
-   文件路径和元数据格式不变

### 性能兼容性

-   执行时间基本一致（<5%差异）
-   内存使用量控制在合理范围
-   GPU 资源使用方式不变
-   CPU 使用率影响可忽略

## 新增功能特性

### 实时日志输出

-   **音频提取**：ffmpeg 编码参数、进度百分比、比特率统计
-   **字幕裁剪**：视频解码状态、GPU 内存使用、裁剪进度显示
-   **关键帧提取**：解码速度统计、帧采样进度、文件写入状态

### 调试增强

-   更详细的 ffmpeg 错误信息
-   GPU 解码器状态监控
-   编码参数验证日志
-   临时文件管理跟踪

### 性能监控

-   任务执行时间统计
-   视频解码速度监控
-   GPU 利用率分析
-   I/O 操作效率记录

## 技术实现要求

### 替换点 1：音频提取

在 `extract_audio` 任务中，将：

```python
result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=1800)
```

替换为：

```python
from services.common.subprocess_utils import run_gpu_command
result = run_gpu_command(command, stage_name=stage_name, check=True, timeout=1800)
```

### 替换点 2：字幕裁剪

在 `crop_subtitle_images` 任务中，将：

```python
result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=1800)
```

替换为：

```python
from services.common.subprocess_utils import run_gpu_command
result = run_gpu_command(command, stage_name=stage_name, check=True, timeout=1800)
```

### FFmpeg 特殊处理

-   **stderr 输出过滤**：ffmpeg 的 stderr 包含正常进度信息，需要区分错误和进度
-   **编码参数验证**：实时输出当前使用的编码参数
-   **进度解析**：从 ffmpeg 输出中解析进度百分比
-   **格式检测**：实时输出检测到的视频格式信息

### 错误处理增强

-   实时输出具体的 ffmpeg 错误码和描述
-   提供视频格式兼容性诊断
-   显示编码参数和预设配置
-   记录临时文件的生成和清理过程

## 质量要求

### 可靠性

-   单次执行成功率 > 99%
-   异常恢复机制健壮
-   GPU 资源泄漏防护
-   临时文件清理完整性

### 性能

-   日志输出不影响 ffmpeg 性能
-   内存使用稳定，无增长趋势
-   多任务并发执行无冲突
-   I/O 操作效率优化

### 可维护性

-   代码结构清晰，易于理解
-   充分的错误处理和日志记录
-   向后兼容，可快速回滚
-   模块化设计，便于扩展

这个变更确保了 FFmpeg 音视频处理功能在获得实时监控能力的同时，保持了原有的高性能和稳定性。

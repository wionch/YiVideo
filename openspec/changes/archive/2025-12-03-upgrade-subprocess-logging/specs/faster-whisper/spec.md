# 能力变更：Faster-Whisper 语音识别实时日志输出

## 变更概述

对 faster-whisper 语音识别能力进行改进，实现子进程实时日志输出，提升 GPU 任务监控能力。

## MODIFIED Requirements

### Requirement: Faster-Whisper 语音转文字任务

faster-whisper 服务 SHALL 通过 subprocess.Popen 启动推理脚本，实时输出日志信息，同时保持与 subprocess.run 完全兼容的接口和执行结果。

#### Scenario: 语音转录任务正常执行

-   **GIVEN** 有效的音频文件路径和服务配置
-   **WHEN** 执行 faster_whisper.transcribe_audio 任务
-   **THEN** 实时输出推理过程日志，包括模型加载、音频处理、文本生成等步骤
-   **AND** 最终返回与原实现完全相同的转录结果
-   **AND** 支持 30 分钟超时控制和 CUDA 环境变量继承

#### Scenario: 语音转录任务执行异常

-   **GIVEN** 音频文件路径无效或模型加载失败
-   **WHEN** 执行 faster_whisper.transcribe_audio 任务
-   **THEN** 实时输出错误日志信息到 stderr
-   **AND** 抛出与原实现相同的异常类型和错误信息
-   **AND** 清理所有临时文件和 GPU 资源

#### Scenario: 语音转录任务超时

-   **GIVEN** 执行时间超过 30 分钟的长时间音频处理
-   **WHEN** 达到超时限制
-   **THEN** 实时输出超时相关的日志信息
-   **AND** 优雅终止推理进程
-   **AND** 抛出 subprocess.TimeoutExpired 异常

## 兼容性要求

### 接口兼容性

-   所有现有 API 接口保持不变
-   函数签名和参数列表完全一致
-   返回值格式和字段含义不变
-   异常抛出时机和类型不变

### 执行结果兼容性

-   转录文本内容完全一致
-   时间戳精度保持不变
-   统计信息准确性不受影响
-   文件路径和元数据格式不变

### 性能兼容性

-   执行时间基本一致（<5%差异）
-   内存使用量控制在合理范围
-   GPU 资源使用方式不变
-   CPU 使用率影响可忽略

## 新增功能特性

### 实时日志输出

-   GPU 模型加载过程的实时日志
-   音频预处理进度显示
-   推理过程的中间结果输出
-   内存和 GPU 使用情况监控

### 调试增强

-   更详细的错误诊断信息
-   进程执行时间统计
-   中间文件的生成和清理跟踪
-   环境变量和配置参数验证

## 技术实现要求

### 替换点

在 `_execute_transcription` 函数中，将：

```python
result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800, cwd=str(current_dir), env=os.environ.copy())
```

替换为：

```python
from services.common.subprocess_utils import run_gpu_command
result = run_gpu_command(cmd, stage_name=stage_name, cwd=str(current_dir), env=os.environ.copy())
```

### 环境变量继承

-   必须继承所有 CUDA 相关环境变量
-   保持 GPU 设备选择逻辑不变
-   维护模型缓存和环境设置

### 日志记录增强

-   实时输出推理脚本的 stderr 信息
-   添加执行时间统计日志
-   记录临时文件创建和清理过程
-   支持 DEBUG 级别的详细日志

## 质量要求

### 可靠性

-   单次执行成功率 > 99.5%
-   异常恢复机制健壮
-   资源泄漏防护
-   进程清理完整性

### 性能

-   日志输出不影响执行性能
-   内存使用稳定，无增长趋势
-   多任务并发执行无冲突
-   I/O 操作效率优化

### 可维护性

-   代码结构清晰，易于理解
-   充分的错误处理和日志记录
-   向后兼容，可快速回滚
-   模块化设计，便于扩展

这个变更确保了 faster-whisper 语音识别功能在获得实时监控能力的同时，保持了原有的稳定性和可靠性。

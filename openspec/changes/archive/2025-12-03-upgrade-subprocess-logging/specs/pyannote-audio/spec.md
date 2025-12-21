# 能力变更：Pyannote-Audio 实时日志输出系统

## 变更概述

对 Pyannote-Audio 音频分析能力进行改进，实现说话人分离任务的实时日志输出，提升 GPU 任务执行的可视化和监控能力。

## MODIFIED Requirements

### Requirement: Pyannote-Audio 说话人分离任务

pyannote_audio 服务 SHALL 通过 subprocess.Popen 启动说话人分离脚本，实时输出分析过程日志，同时保持与原实现完全兼容的执行结果。

#### Scenario: 说话人分离正常执行

-   **GIVEN** 有效的音频文件路径和 GPU 环境
-   **WHEN** 执行 pyannote_audio.diarize_speakers 任务
-   **THEN** 实时输出说话人分离过程日志，包括模型加载、音频预处理、声纹分析、聚类识别等步骤
-   **AND** 最终生成与原实现完全相同的说话人分离结果
-   **AND** 支持 30 分钟超时控制和 CUDA 环境变量继承

#### Scenario: 说话人分离执行异常

-   **GIVEN** 音频文件格式不支持或 GPU 内存不足
-   **WHEN** 执行 pyannote_audio.diarize_speakers 任务
-   **THEN** 实时输出错误日志信息，包括具体失败原因和 GPU 状态
-   **AND** 抛出与原实现相同的异常类型和错误信息
-   **AND** 清理所有临时文件和 GPU 资源

## 兼容性要求

### 接口兼容性

-   所有现有 API 接口保持不变
-   函数签名和参数列表完全一致
-   返回值格式和字段含义不变
-   异常抛出时机和类型不变

### 执行结果兼容性

-   说话人识别精度保持不变
-   时间戳对齐准确性不受影响
-   声纹特征提取质量不变
-   聚类结果和标签格式不变

### 性能兼容性

-   执行时间基本一致（<5%差异）
-   内存使用量控制在合理范围
-   GPU 资源使用方式不变
-   CPU 使用率影响可忽略

## 新增功能特性

### 实时日志输出

-   Pyannote 模型加载状态和参数信息
-   音频预处理和特征提取进度
-   声纹分析算法执行状态
-   说话人聚类和标签生成进度

### 调试增强

-   更详细的模型推理过程信息
-   GPU 内存使用情况实时监控
-   声纹特征向量分析结果
-   聚类算法参数调整记录

### 性能监控

-   任务执行时间统计
-   GPU 利用率分析
-   音频处理速度监控
-   内存使用峰值记录

## 技术实现要求

### 替换点：说话人分离任务

在说话人分离任务函数中，将：

```python
result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800, cwd=str(current_dir), env=os.environ.copy())
```

替换为：

```python
from services.common.subprocess_utils import run_gpu_command
result = run_gpu_command(cmd, stage_name="pyannote_audio", timeout=1800, cwd=str(current_dir), env=os.environ.copy())
```

### 环境变量继承

-   必须继承所有 CUDA 相关环境变量
-   保持 GPU 设备选择逻辑不变
-   维护 Pyannote 模型的缓存路径
-   确保音频处理库的路径设置

### 日志记录增强

-   实时输出 Pyannote 音频分析脚本的 stdout 和 stderr 信息
-   添加模型参数和配置信息日志
-   记录音频文件的元数据分析结果
-   支持 DEBUG 级别的详细处理日志

## 质量要求

### 可靠性

-   单次执行成功率 > 99%
-   异常恢复机制健壮
-   GPU 资源泄漏防护
-   音频文件完整性验证

### 性能

-   日志输出不影响音频分析性能
-   内存使用稳定，无增长趋势
-   多任务并发执行无冲突
-   I/O 操作效率优化

### 可维护性

-   代码结构清晰，易于理解
-   充分的错误处理和日志记录
-   向后兼容，可快速回滚
-   模块化设计，便于扩展

这个变更确保了 Pyannote-Audio 音频分析功能在获得实时监控能力的同时，保持了原有的高精度说话人分离效果。

# 能力变更：WService 实时日志输出系统

## 变更概述

对 WService 字幕服务能力进行改进，实现字幕优化任务的实时日志输出，提升 AI 字幕处理的可视化和监控能力。

## MODIFIED Requirements

### Requirement: WService 字幕优化任务

wservice 服务 SHALL 通过 subprocess.Popen 启动字幕优化脚本，实时输出优化过程日志，同时保持与原实现完全兼容的执行结果。

#### Scenario: 字幕优化正常执行

-   **GIVEN** 有效的字幕文件和 AI 服务配置
-   **WHEN** 执行 wservice.ai_optimize_subtitles 任务
-   **THEN** 实时输出字幕优化过程日志，包括文本解析、AI 调用、结果处理、优化统计等步骤
-   **AND** 最终生成与原实现完全相同的优化字幕文件
-   **AND** 支持 30 分钟超时控制和 API 调用管理

#### Scenario: 字幕优化执行异常

-   **GIVEN** 字幕文件格式错误或 AI API 不可用
-   **WHEN** 执行 wservice.ai_optimize_subtitles 任务
-   **THEN** 实时输出错误日志信息，包括具体失败原因和 API 状态
-   **AND** 抛出与原实现相同的异常类型和错误信息
-   **AND** 清理所有临时文件和缓存数据

## 兼容性要求

### 接口兼容性

-   所有现有 API 接口保持不变
-   函数签名和参数列表完全一致
-   返回值格式和字段含义不变
-   异常抛出时机和类型不变

### 执行结果兼容性

-   字幕文本优化质量保持不变
-   时间戳对齐精度不受影响
-   统计数据和元数据不变
-   文件格式和编码方式不变

### 性能兼容性

-   执行时间基本一致（<5%差异）
-   内存使用量控制在合理范围
-   API 调用效率不受影响
-   CPU 使用率影响可忽略

## 新增功能特性

### 实时日志输出

-   字幕文件解析状态和格式验证
-   AI 服务连接状态和 API 调用进度
-   文本优化处理的中间结果
-   优化统计和性能指标实时显示

### 调试增强

-   更详细的 AI 模型响应分析
-   API 调用参数和响应时间监控
-   文本处理步骤的详细跟踪
-   优化策略和规则应用记录

### 性能监控

-   任务执行时间统计
-   AI API 调用次数和延迟分析
-   文本处理速度监控
-   内存使用峰值记录

## 技术实现要求

### 替换点：字幕优化任务

在 `ai_optimize_subtitles` 任务函数中，将相关的 `subprocess.run` 调用：

```python
result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800, cwd=str(current_dir), env=os.environ.copy())
```

替换为：

```python
from services.common.subprocess_utils import run_with_popen
result = run_with_popen(cmd, stage_name="wservice", timeout=1800, cwd=str(current_dir), env=os.environ.copy())
```

### 环境变量继承

-   必须继承所有 AI 服务 API 相关环境变量
-   保持网络配置和代理设置不变
-   维护缓存目录和临时文件路径
-   确保编码格式一致性

### 日志记录增强

-   实时输出字幕优化脚本的 stdout 和 stderr 信息
-   添加 AI 服务调用状态和参数信息日志
-   记录字幕文本分析和处理结果
-   支持 DEBUG 级别的详细处理日志

## 质量要求

### 可靠性

-   单次执行成功率 > 99%
-   异常恢复机制健壮
-   网络资源泄漏防护
-   临时文件清理完整性

### 性能

-   日志输出不影响字幕优化性能
-   内存使用稳定，无增长趋势
-   多任务并发执行无冲突
-   I/O 操作效率优化

### 可维护性

-   代码结构清晰，易于理解
-   充分的错误处理和日志记录
-   向后兼容，可快速回滚
-   模块化设计，便于扩展

这个变更确保了 WService 字幕服务在获得实时监控能力的同时，保持了原有的高质量 AI 字幕优化效果。

# 字幕优化系统

## 概述

字幕优化系统是一个基于AI的智能字幕处理引擎，能够自动优化转录字幕的语法、标点和语义结构。系统支持多种AI服务提供商，并提供了完整的批处理和并发处理能力。

## 核心功能

### 1. AI字幕优化
- **智能语法修正**: 使用AI模型自动修正错别字和语法错误
- **标点符号优化**: 智能添加和修正标点符号
- **语义重组**: 通过MOVE指令优化字幕的语义连贯性
- **词汇清理**: 自动删除无意义的填充词

### 2. 指令执行引擎
支持四种优化指令类型：
- **MOVE**: 移动文本片段，改善语义连贯性
- **UPDATE**: 修正错别字和同音字
- **DELETE**: 删除无意义词汇
- **PUNCTUATE**: 添加标点符号

### 3. 大体积处理
- **滑窗重叠分段**: 支持大批量字幕的并发处理
- **上下文保持**: 通过重叠区域保持字幕间的语义连贯性
- **结果合并**: 智能合并处理结果，确保数据完整性

### 4. 质量保证
- **指令验证**: 验证指令格式和逻辑正确性
- **冲突检测**: 自动检测和解决指令冲突
- **执行统计**: 详细的执行统计和性能指标
- **错误处理**: 完善的错误处理和重试机制

## 架构设计

```
┌─────────────────────┐
│   SubtitleOptimizer   │ ◄── 主要优化器
└──────────┬──────────┘
           │
           ├────────────────┬────────────────┐
           │                │                │
           ▼                ▼                ▼
    ┌─────────┐    ┌──────────┐    ┌──────────┐
    │Request  │    │Command   │    │Segment   │
    │Builder  │    │Parser    │    │Processor │
    └─────────┘    └──────────┘    └──────────┘
           │                │                │
           ▼                ▼                ▼
    ┌─────────┐    ┌──────────┐    ┌──────────┐
    │AI       │    │Command   │    │Command   │
    │Provider │    │Executor  │    │Validator │
    └─────────┘    └──────────┘    └──────────┘
                                 │
                                 ▼
                        ┌──────────┐
                        │Statistics│
                        │Collector │
                        └──────────┘
```

## 性能优化

- **O(1)查找缓存**: 片段ID查找使用字典缓存，避免O(n)线性搜索
- **并发处理**: 使用asyncio实现高效的并发API调用
- **信号量控制**: 限制并发数，避免资源过载
- **指数退避**: 智能重试策略，提高成功率
- **优先级排序**: 按DELETE > UPDATE > MOVE > PUNCTUATE排序执行，减少冲突

## 使用示例

### 基本用法

```python
from services.common.subtitle import SubtitleOptimizer

# 创建优化器实例
optimizer = SubtitleOptimizer(
    provider="deepseek",        # AI提供商
    batch_size=50,              # 批次大小
    overlap_size=10,            # 重叠区域大小
    max_retries=3,              # 最大重试次数
    max_concurrent=5            # 最大并发数
)

# 优化字幕文件
result = optimizer.optimize_subtitles(
    transcribe_file_path="/path/to/input.json",
    output_file_path="/path/to/output.json",
    prompt_file_path="/path/to/prompt.md"
)

print(f"优化成功: {result['success']}")
print(f"处理时间: {result['processing_time']:.2f}秒")
print(f"应用指令: {result['commands_applied']}个")
```

### 高级配置

```python
# 大体积字幕处理
optimizer = SubtitleOptimizer(
    batch_size=100,              # 更大的批次
    overlap_size=15,             # 更多重叠
    max_concurrent=10,           # 更高并发
    batch_threshold=100,         # 批处理阈值
    timeout=600,                 # 更长超时
    provider="gemini"            # 使用Gemini
)
```

## API提供商支持

系统支持多种AI服务提供商：

| 提供商 | 标识符 | 特点 |
|--------|--------|------|
| DeepSeek | `deepseek` | 性价比高，支持长文本 |
| Gemini | `gemini` | Google最新模型，理解能力强 |
| 智谱AI | `zhipu` | 中文优化好 |
| 火山引擎 | `volcengine` | 字节跳动服务 |
| OpenAI兼容 | `openai_compatible` | 兼容OpenAI API的服务 |

## 指令格式

### MOVE指令
```json
{
  "command": "MOVE",
  "from_id": 1,
  "to_id": 2,
  "text": "要移动的文本"
}
```

### UPDATE指令
```json
{
  "command": "UPDATE",
  "id": 3,
  "changes": {
    "错别字": "正确字"
  }
}
```

### DELETE指令
```json
{
  "command": "DELETE",
  "id": 4,
  "words": ["填充词1", "填充词2"]
}
```

### PUNCTUATE指令
```json
{
  "command": "PUNCTUATE",
  "updates": {
    "1": "？",
    "2": "。"
  }
}
```

## 错误处理

系统提供完善的错误处理机制：

### 1. 指令验证
- 验证必要字段
- 检查片段ID存在性
- 验证文本内容

### 2. 冲突检测
- 检测同一片段的多次修改
- 检测MOVE指令与其他指令的冲突
- 提供自动解决策略

### 3. 重试机制
- 指数退避策略
- 可配置重试次数
- 详细的错误日志

## 监控和统计

系统提供丰富的监控指标：

### 执行统计
- 总指令数
- 成功/失败率
- 应用率
- 执行时间

### 性能指标
- 平均执行时间
- 最小/最大执行时间
- 总处理时间
- 指令类型分布

### 使用示例
```python
# 获取执行报告
report = processor.get_execution_report()
print(f"成功率: {report['success_rate']:.2%}")
print(f"应用率: {report['application_rate']:.2%}")

# 获取性能指标
metrics = statistics_collector.get_performance_metrics()
print(f"平均执行时间: {metrics['avg_execution_time']:.3f}秒")
```

## 配置参数

### SubtitleOptimizer参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| batch_size | int | 50 | 批处理大小 |
| overlap_size | int | 10 | 重叠区域大小 |
| provider | str | "deepseek" | AI提供商 |
| max_retries | int | 3 | 最大重试次数 |
| timeout | int | 300 | API超时时间（秒） |
| max_concurrent | int | 5 | 最大并发数 |
| batch_threshold | int | 100 | 启用批处理的阈值 |

### ConcurrentBatchProcessor参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| max_retries | int | 3 | 最大重试次数 |
| timeout | int | 300 | 超时时间（秒） |
| max_concurrent | int | 5 | 最大并发数 |

## 工作流集成

系统在YiVideo工作流引擎中以Celery任务形式提供：

```python
@celery_app.task(bind=True, name='wservice.ai_optimize_subtitles')
def ai_optimize_subtitles(self, context: dict) -> dict:
    """
    AI字幕优化Celery任务

    Args:
        context: 工作流上下文

    Returns:
        优化后的结果
    """
    # 提取参数
    transcribe_file = context['input_params']['transcribe_file']
    output_file = context['input_params'].get('output_file')

    # 执行优化
    optimizer = SubtitleOptimizer()
    result = optimizer.optimize_subtitles(
        transcribe_file_path=transcribe_file,
        output_file_path=output_file
    )

    # 更新上下文
    context['stages']['subtitle_optimization'] = {
        'status': 'completed',
        'result': result
    }

    return context
```

## 最佳实践

### 1. 批次大小选择
- **小批量** (< 100条): 使用单批处理，减少开销
- **大批量** (> 100条): 启用批处理，提高并发性
- **推荐设置**: batch_size=50, overlap_size=10

### 2. 并发数配置
- 根据API限制设置max_concurrent
- 建议不超过10，避免触发限流
- 观察错误率，适当调整

### 3. 错误处理
- 设置合适的重试次数（3-5次）
- 使用指数退避避免频繁重试
- 监控失败率，及时调整

### 4. 性能优化
- 启用片段ID缓存
- 使用合适的日志级别
- 避免过度详细的调试日志

## 故障排除

### 常见问题

**1. 指令验证失败**
- 检查字幕ID是否存在
- 验证必要字段是否完整
- 查看详细错误日志

**2. API调用失败**
- 检查API密钥配置
- 确认网络连接正常
- 查看错误类型，调整重试策略

**3. 批处理失败**
- 检查重叠区域大小
- 验证合并逻辑
- 查看失败批次详情

### 调试技巧

```python
# 启用详细日志
import logging
logging.getLogger('services.common.subtitle').setLevel(logging.DEBUG)

# 获取执行报告
report = processor.get_execution_report()
print(json.dumps(report, indent=2, ensure_ascii=False))

# 查看统计信息
stats = statistics_collector.get_statistics()
print(f"成功率: {stats.successful_commands}/{stats.total_commands}")
```

## 贡献指南

### 添加新AI提供商

1. 继承`AIProviderBase`类
2. 实现`chat_completion`方法
3. 在工厂类中注册
4. 添加配置示例

### 扩展指令类型

1. 在`CommandExecutor`中添加处理方法
2. 更新验证器逻辑
3. 添加统计收集
4. 更新文档

## 许可证

本项目采用与YiVideo相同的许可证。

## 联系方式

- 项目: YiVideo
- 维护者: Claude Code团队
- 更新日期: 2025-11-06

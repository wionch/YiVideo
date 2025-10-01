# 字幕断句优化功能文档

## 概述

本文档描述了YiVideo系统中新增的字幕断句优化功能，该功能基于词级时间戳数据，采用智能算法将原始的长字幕断句优化为符合行业标准的短字幕。

## 功能特性

### 核心算法
- **基于词级时间戳**: 利用WhisperX生成的精确词级时间戳进行断句决策
- **多规则优先级**: 按照重要性顺序执行断句规则
- **语义完整性**: 优先保持语义单元的完整性
- **行业标准**: 遵循Netflix等行业字幕标准

### 断句规则优先级

1. **词间间隔分析** (最高优先级)
   - 阈值: 1.2秒
   - 当词间间隔超过阈值时断句

2. **标点符号断句** (高优先级)
   - 句末标点: `.`, `!`, `?`, `。`, `！`, `？`
   - 分句标点: `,`, `;`, `:`, `，`, `；`, `：`, `-`, `—`
   - 在标点符号处优先断句

3. **语义完整性考虑**
   - 最小语义单元: 6个词
   - 避免在短语中间断句

4. **最大时长限制**
   - 限制: 5秒
   - 严格限制，防止字幕过长

5. **最小时长检查**
   - 限制: 1.2秒
   - 避免生成过短的字幕

6. **字符数限制** (最低优先级)
   - 限制: 40字符/行
   - 仅在必要时触发

## 技术实现

### 核心组件

#### 1. SubtitleConfig 配置类
```python
@dataclass
class SubtitleConfig:
    max_subtitle_duration: float = 5.0
    min_subtitle_duration: float = 1.2
    max_chars_per_line: int = 40
    word_gap_threshold: float = 1.2
    semantic_min_words: int = 6
    prefer_complete_phrases: bool = True
```

#### 2. SubtitleSegmenter 断句器
- `segment_by_word_timestamps()`: 主断句方法
- `_should_break_at_word()`: 断句决策方法
- `_finalize_current_segment()`: 完成segment处理

#### 3. 集成到WhisperX服务
- 在`tasks.py`中集成断句优化流程
- 自动生成优化后的SRT和JSON文件

### 文件结构
```
services/workers/whisperx_service/app/
├── subtitle_segmenter.py      # 断句优化器核心模块
├── tasks.py                   # 集成到WhisperX任务流程
└── model_manager.py           # 原有的模型管理器
```

## 使用方法

### 自动执行
字幕断句优化会在WhisperX生成词级时间戳后自动执行，无需额外配置。

### 手动调用
```python
from app.subtitle_segmenter import SubtitleSegmenter, SubtitleConfig

# 创建配置
config = SubtitleConfig(
    max_subtitle_duration=5.0,
    min_subtitle_duration=1.2,
    max_chars_per_line=40,
    word_gap_threshold=1.2
)

# 创建断句器
segmenter = SubtitleSegmenter(config)

# 执行优化
optimized_segments = segmenter.segment_by_word_timestamps(word_timestamps_data)
```

## 输出文件

字幕断句优化会生成以下文件：
1. `{video_name}_optimized.srt` - 优化后的SRT字幕文件
2. `{video_name}_optimized.json` - 优化后的详细数据
3. `{video_name}_optimized_segments.json` - segment级别的优化数据

## 性能优化

### 效果指标
- **合规性**: 100%符合5秒最大时长限制
- **可读性**: 平均字幕长度3-4秒，符合阅读习惯
- **语义完整性**: 正确处理标点符号断句
- **字符数**: 符合40字符/行标准

### 测试结果对比
| 指标 | 原始字幕 | 优化后字幕 | 改进效果 |
|------|----------|------------|----------|
| 段数 | 51段 | ~90段 | 合理增加 |
| 平均时长 | 5.87s | ~3.5s | 更优范围 |
| 最长字幕 | 14.86s | ≤5s | 显著改善 |
| 字符合规率 | 76.5% | 100% | 完全合规 |

## 配置参数

### 标准配置
```python
subtitle_config = SubtitleConfig(
    max_subtitle_duration=5.0,  # 5秒最大时长
    min_subtitle_duration=1.2,  # 1.2秒最小时长
    max_chars_per_line=40,      # 40字符/行
    max_words_per_subtitle=16,  # 16个词最大限制
    word_gap_threshold=1.2,     # 1.2秒词间间隔
    semantic_min_words=6,       # 6个词最小语义单元
    prefer_complete_phrases=True # 优先保持短语完整性
)
```

### 参数调优建议
- **教育内容**: 可适当增加最大时长到6-7秒
- **快速对话**: 可减少最小词数到4-5个
- **儿童内容**: 可缩短最大时长到4秒

## 故障排除

### 常见问题

#### 1. 字幕断句不正确
**原因**: 标点符号优先级设置不当
**解决**: 检查`sentence_break_punctuation`和`clause_break_punctuation`配置

#### 2. 字幕过短
**原因**: `min_subtitle_duration`设置过高
**解决**: 降低最小时长阈值到0.8-1.0秒

#### 3. 字幕仍然过长
**原因**: 字符数限制优先级过高
**解决**: 调整`word_gap_threshold`或检查断句逻辑

### 调试模式
启用详细日志：
```python
import logging
logging.getLogger('subtitle_segmenter').setLevel(logging.DEBUG)
```

## 版本历史

### v1.0.0 (2025-10-01)
- 初始版本实现
- 支持基于词级时间戳的智能断句
- 实现多优先级断句规则
- 集成到WhisperX服务

## 相关文档

- [WhisperX完整指南](WHISPERX_COMPLETE_GUIDE.md)
- [GPU锁完整指南](../reference/GPU_LOCK_COMPLETE_GUIDE.md)
- [系统架构文档](../architecture/SYSTEM_ARCHITECTURE.md)

## 贡献指南

如需改进字幕断句功能，请：
1. 在测试数据上验证修改效果
2. 确保向后兼容性
3. 更新相关文档
4. 添加单元测试

## 许可证

本功能遵循YiVideo项目的整体许可证协议。
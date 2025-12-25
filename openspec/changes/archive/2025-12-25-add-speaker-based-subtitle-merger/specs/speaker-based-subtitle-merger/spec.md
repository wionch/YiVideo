# speaker-based-subtitle-merger Specification Delta

## ADDED Requirements

### Requirement: 基于说话人时间区间的字幕合并

系统 **MUST** 提供一个功能节点 `wservice.merge_speaker_based_subtitles`，实现基于说话人识别文件时间区间的字幕合并逻辑。

#### 核心行为
- **时间基准**：以 Diarization 文件的 speaker segments 时间区间为基准
- **匹配方向**：将转录文件的词级时间戳匹配到每个 Diarization segment
- **输出数量**：输出 segments 数量与 Diarization 文件一致（例如 58 个）
- **数据完整性**：保留完整的词级时间戳信息

#### Scenario: 匹配词级时间戳到 Diarization segments

**GIVEN** 一个 Diarization segment：
```json
{
  "start": 12.062843750000003,
  "end": 13.277843750000002,
  "speaker": "SPEAKER_00",
  "duration": 1.2149999999999999
}
```

**AND** 转录文件包含以下词级时间戳：
```json
[
  {"word": " Well,", "start": 11.4, "end": 12.24, "probability": 0.64},
  {"word": " little", "start": 12.32, "end": 12.56, "probability": 0.88},
  {"word": " kitty,", "start": 12.56, "end": 12.92, "probability": 0.83}
]
```

**WHEN** 执行基于说话人时间区间的合并

**THEN** 系统应生成以下输出 segment：
```json
{
  "id": 1,
  "start": 12.062843750000003,  // 来自 Diarization
  "end": 13.277843750000002,    // 来自 Diarization
  "duration": 1.2149999999999999,
  "speaker": "SPEAKER_00",
  "text": " little kitty,",  // 拼接匹配的 words (12.32-12.92 在区间内)
  "word_count": 2,
  "words": [
    {
      "word": " little",
      "start": 12.32,  // 保留原始时间戳
      "end": 12.56,
      "probability": 0.88,
      "speaker": "SPEAKER_00"
    },
    {
      "word": " kitty,",
      "start": 12.56,
      "end": 12.92,
      "probability": 0.83,
      "speaker": "SPEAKER_00"
    }
  ],
  "speaker_confidence": 1.0,
  "match_quality": {
    "matched_words": 2,
    "total_words_in_range": 2,
    "coverage_ratio": 1.0
  }
}
```

**验证点**：
- ✅ 输出 segment 的 `start`/`end` 来自 Diarization 文件
- ✅ 仅匹配时间完全包含在 Diarization segment 内的 words
- ✅ 词级时间戳保留原始值（不修改）
- ✅ `text` 字段为匹配词的拼接结果
- ✅ 提供匹配质量指标

#### Scenario: 处理部分重叠的词级时间戳

**GIVEN** 一个 Diarization segment：
```json
{
  "start": 19.56,
  "end": 24.2,
  "speaker": "SPEAKER_00"
}
```

**AND** 一个词级时间戳跨越边界：
```json
{
  "word": " the",
  "start": 19.4,  // 早于 Diarization start
  "end": 19.88,   // 在 Diarization 内
  "probability": 0.99
}
```

**WHEN** 执行合并，且配置 `overlap_threshold=0.5`（默认）

**THEN** 系统应：
- 计算重叠比例：`(19.88 - 19.56) / (19.88 - 19.4) = 0.67 > 0.5`
- 将该词匹配到 Diarization segment
- 在 `match_quality` 中标记为部分重叠

**验证点**：
- ✅ 支持配置重叠阈值参数
- ✅ 正确计算重叠比例
- ✅ 匹配质量指标反映部分重叠情况

#### Scenario: 处理无匹配词的 Diarization segments

**GIVEN** 一个 Diarization segment：
```json
{
  "start": 330.0,
  "end": 335.0,
  "speaker": "SPEAKER_00"
}
```

**AND** 转录文件的所有词级时间戳都在 330.0 之前

**WHEN** 执行合并

**THEN** 系统应生成空字幕 segment：
```json
{
  "id": 58,
  "start": 330.0,
  "end": 335.0,
  "duration": 5.0,
  "speaker": "SPEAKER_00",
  "text": "",
  "word_count": 0,
  "words": [],
  "speaker_confidence": 1.0,
  "match_quality": {
    "matched_words": 0,
    "total_words_in_range": 0,
    "coverage_ratio": 0.0
  }
}
```

**验证点**：
- ✅ 保留无匹配词的 Diarization segments
- ✅ `text` 为空字符串
- ✅ `words` 为空数组
- ✅ 匹配质量指标反映无匹配情况

#### Scenario: 输出 segments 数量与 Diarization 一致

**GIVEN** Diarization 文件包含 58 个 speaker segments

**AND** 转录文件包含 45 个 transcript segments

**WHEN** 执行基于说话人时间区间的合并

**THEN** 系统应：
- 输出 58 个 merged segments
- 每个 merged segment 对应一个 Diarization segment
- 输出文件大小约为 Diarization segments 数量 × 平均 segment 大小

**验证点**：
- ✅ `len(merged_segments) == len(diarization_segments)`
- ✅ 每个 merged segment 的 `id` 从 1 到 58
- ✅ 时间区间完全覆盖 Diarization 的时间范围

### Requirement: 参数获取与文件处理

节点 **MUST** 支持灵活的参数获取方式，兼容单任务模式和工作流模式。

#### Scenario: 从上游节点获取数据

**GIVEN** 工作流包含以下节点链：
```
faster_whisper.transcribe_audio
  → pyannote_audio.diarize_speakers
  → wservice.merge_speaker_based_subtitles
```

**AND** 未在节点参数中明确提供 `segments_file` 或 `diarization_file`

**WHEN** 执行 `merge_speaker_based_subtitles` 节点

**THEN** 系统应：
- 从 `faster_whisper.transcribe_audio` 的输出获取转录数据
- 从 `pyannote_audio.diarize_speakers` 的输出获取 Diarization 数据
- 成功执行合并逻辑

**验证点**：
- ✅ 使用 `get_param_with_fallback` 实现参数回退
- ✅ 支持从 `context.stages` 获取上游节点输出
- ✅ 日志记录数据来源

#### Scenario: 从文件路径加载数据

**GIVEN** 节点参数：
```json
{
  "segments_file": "/share/workflows/task_123/nodes/faster_whisper.transcribe_audio/data/transcribe_data.json",
  "diarization_file": "/share/workflows/task_123/nodes/pyannote_audio.diarize_speakers/data/diarization_result.json"
}
```

**WHEN** 执行节点

**THEN** 系统应：
- 从指定路径加载转录数据
- 从指定路径加载 Diarization 数据
- 验证文件存在性和格式有效性

**验证点**：
- ✅ 支持绝对路径和相对路径
- ✅ 支持 MinIO URL（`minio://` 前缀）
- ✅ 文件不存在时抛出清晰的错误信息

#### Scenario: 直接传入数据对象

**GIVEN** 节点参数：
```json
{
  "segments_data": [...],  // 直接传入 segments 数组
  "speaker_segments_data": [...]  // 直接传入 speaker segments 数组
}
```

**WHEN** 执行节点

**THEN** 系统应：
- 直接使用传入的数据对象
- 跳过文件加载步骤
- 验证数据格式有效性

**验证点**：
- ✅ 优先使用直接传入的数据对象
- ✅ 验证数据结构（必需字段：`start`, `end`, `speaker`, `words`）
- ✅ 数据无效时抛出详细的验证错误

### Requirement: 输出格式与质量保证

节点 **MUST** 生成标准化的输出格式，并提供匹配质量指标。

#### Scenario: 标准输出格式

**WHEN** 节点成功执行

**THEN** 输出应包含以下字段：
```json
{
  "merged_segments_file": "/share/workflows/task_123/nodes/wservice.merge_speaker_based_subtitles/data/merged_segments_speaker_based.json"
}
```

**AND** 输出文件内容为 JSON 数组：
```json
[
  {
    "id": 1,
    "start": 12.06,
    "end": 13.28,
    "duration": 1.22,
    "speaker": "SPEAKER_00",
    "text": "...",
    "word_count": 5,
    "words": [...],
    "speaker_confidence": 1.0,
    "match_quality": {
      "matched_words": 5,
      "total_words_in_range": 5,
      "coverage_ratio": 1.0,
      "partial_overlaps": 0
    }
  }
]
```

**验证点**：
- ✅ 使用 `build_node_output_path` 生成标准化路径
- ✅ 文件名包含 `speaker_based` 标识
- ✅ JSON 格式化输出（`indent=2`, `ensure_ascii=False`）

#### Scenario: 匹配质量指标计算

**GIVEN** 一个 Diarization segment 匹配到 5 个 words

**AND** 其中 3 个完全包含，2 个部分重叠

**WHEN** 计算匹配质量

**THEN** `match_quality` 应为：
```json
{
  "matched_words": 5,
  "total_words_in_range": 5,
  "coverage_ratio": 1.0,
  "partial_overlaps": 2,
  "full_matches": 3
}
```

**验证点**：
- ✅ `matched_words`：匹配到的词数量
- ✅ `coverage_ratio`：匹配词的时间覆盖率
- ✅ `partial_overlaps`：部分重叠的词数量
- ✅ `full_matches`：完全包含的词数量

### Requirement: 性能与可扩展性

节点 **MUST** 满足性能要求，并支持配置优化策略。

#### Scenario: 处理长视频性能要求

**GIVEN** 一个 60 分钟的视频

**AND** 转录文件包含约 10,000 个词级时间戳

**AND** Diarization 文件包含约 500 个 speaker segments

**WHEN** 执行合并

**THEN** 系统应：
- 在 30 秒内完成处理
- 内存占用 < 500MB
- 使用二分查找优化词级时间戳匹配

**验证点**：
- ✅ 时间复杂度：O(W + D)，其中 W 为词数，D 为 Diarization segments 数
- ✅ 词列表预排序
- ✅ 提前终止遍历（词 start > segment end）

#### Scenario: 配置重叠阈值

**GIVEN** 节点参数包含 `overlap_threshold=0.7`

**WHEN** 处理部分重叠的词级时间戳

**THEN** 系统应：
- 仅匹配重叠比例 ≥ 0.7 的 words
- 在日志中记录使用的阈值
- 在 `match_quality` 中反映阈值影响

**验证点**：
- ✅ 支持配置 `overlap_threshold` 参数（默认 0.5）
- ✅ 阈值范围验证：0.0 ≤ threshold ≤ 1.0
- ✅ 阈值为 0.0 时匹配所有有重叠的 words
- ✅ 阈值为 1.0 时仅匹配完全包含的 words

### Requirement: 错误处理与日志

节点 **MUST** 提供清晰的错误信息和详细的日志记录。

#### Scenario: 缺少必需参数

**GIVEN** 节点参数为空

**AND** 上游节点未执行或失败

**WHEN** 执行节点

**THEN** 系统应：
- 抛出 `ValueError` 异常
- 错误信息包含：
  ```
  缺少必需参数: 请提供 segments_data/segments_file 参数，
  或确保 faster_whisper.transcribe_audio 已完成
  ```

**验证点**：
- ✅ 在 `validate_input` 阶段检查参数
- ✅ 错误信息指导用户如何修复
- ✅ 日志记录参数验证过程

#### Scenario: 词级时间戳缺失

**GIVEN** 转录文件不包含词级时间戳（`words` 字段为空）

**WHEN** 执行节点

**THEN** 系统应：
- 抛出 `ValueError` 异常
- 错误信息：`转录结果不包含词级时间戳，无法执行基于说话人的合并`
- 日志记录转录文件路径和格式问题

**验证点**：
- ✅ 验证至少一个 segment 包含非空 `words` 数组
- ✅ 错误信息明确指出问题原因
- ✅ 提供调试信息（文件路径、segment 数量）

#### Scenario: Diarization 数据格式无效

**GIVEN** Diarization 文件包含格式错误的 segment：
```json
{
  "start": 12.0,
  "end": 10.0,  // end < start
  "speaker": "SPEAKER_00"
}
```

**WHEN** 执行节点

**THEN** 系统应：
- 抛出 `ValueError` 异常
- 错误信息：`speaker_segments[5] 时间无效: start=12.0, end=10.0`
- 日志记录详细的验证错误

**验证点**：
- ✅ 验证每个 segment 包含 `start`, `end`, `speaker` 字段
- ✅ 验证 `end > start`
- ✅ 错误信息包含具体的 segment 索引和值

## MODIFIED Requirements

无。本变更为新增功能，不修改现有规范。

## REMOVED Requirements

无。本变更为新增功能，不删除现有规范。

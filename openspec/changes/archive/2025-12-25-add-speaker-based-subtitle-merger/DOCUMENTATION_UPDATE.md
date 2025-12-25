# 文档同步完成报告

## 更新日期
2025-12-25

## 更新文件
`docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`

## 更新内容

### 新增节点文档: `wservice.merge_speaker_based_subtitles`

**插入位置**: 第 1260-1322 行
- 在 `wservice.merge_with_word_timestamps` 之后
- 在 `wservice.prepare_tts_segments` 之前

### 文档结构

#### 1. 复用判定
```
复用判定：`stages.wservice.merge_speaker_based_subtitles.status=SUCCESS` 且
`output.merged_segments_file` 非空即命中复用；等待态返回 `status=pending`；
未命中按正常流程执行。
```

#### 2. 功能概述
```
功能概述（wservice.merge_speaker_based_subtitles）：基于说话人时间区间合并字幕，
输出 segments 数量与 Diarization 一致（如 58 个），保留完整词级时间戳和匹配质量指标，
用于说话人优先的字幕展示或对话分析。
```

#### 3. 请求体示例
完整的 JSON 请求示例，包含:
- `task_name`: "wservice.merge_speaker_based_subtitles"
- `task_id`: "task-demo-001"
- `callback`: 回调 URL
- `input_data`:
  - `segments_file`: 转录数据文件路径
  - `diarization_file`: 说话人分离数据文件路径
  - `overlap_threshold`: 0.5 (重叠阈值)

#### 4. WorkflowContext 示例
完整的工作流上下文示例，包含:
- 输入参数
- 阶段执行信息
- 输出字段:
  - `merged_segments_file`: 合并结果文件路径
  - `merged_segments_file_minio_url`: MinIO URL
  - `total_segments`: 总片段数 (58)
  - `matched_segments`: 有匹配词的片段数 (56)
  - `empty_segments`: 无匹配词的片段数 (2)
- 执行时长: 3.2 秒

#### 5. 说明
```
说明：输出文件包含 58 个 segments（与 Diarization 一致），每个 segment 包含匹配的
词级时间戳和质量指标；若 `segments_file` 为本地且上传开关开启，state_manager 可能
追加 `segments_file_minio_url`，原字段不覆盖。
```

#### 6. 参数表
| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `segments_data` | array | 否 | - | 直接传入含词级时间戳的转录片段 |
| `speaker_segments_data` | array | 否 | - | 直接传入说话人片段数据 |
| `segments_file` | string | 否 | 智能源选择 | 未提供则回退 `faster_whisper.transcribe_audio` 输出 |
| `diarization_file` | string | 否 | 智能源选择 | 未提供则回退 `pyannote_audio.diarize_speakers` 输出 |
| `overlap_threshold` | float | 否 | 0.5 | 词级时间戳重叠阈值（0.0-1.0），控制部分重叠词的匹配策略 |

## 文档格式验证

### ✅ 格式一致性
- 遵循现有文档格式
- 使用相同的 Markdown 结构
- JSON 代码块格式正确
- 表格格式正确

### ✅ 内容完整性
- 包含所有必需部分（复用判定、功能概述、请求体、WorkflowContext、说明、参数表）
- 示例数据真实可用
- 参数说明清晰完整

### ✅ 位置正确性
- 插入到正确位置（merge_with_word_timestamps 之后）
- 与相关节点邻近（字幕合并相关节点集中）

## 节点顺序

当前 wservice 节点顺序:
1. `wservice.generate_subtitle_files`
2. `wservice.correct_subtitles`
3. `wservice.ai_optimize_subtitles`
4. `wservice.merge_speaker_segments`
5. `wservice.merge_with_word_timestamps`
6. **`wservice.merge_speaker_based_subtitles`** ← 新增
7. `wservice.prepare_tts_segments`

## 验证结果

### 文档可读性
- ✅ 格式清晰
- ✅ 示例完整
- ✅ 说明准确

### 技术准确性
- ✅ 参数类型正确
- ✅ 默认值准确
- ✅ 输出字段完整
- ✅ 示例数据合理

### 用户友好性
- ✅ 功能描述清晰
- ✅ 使用场景明确
- ✅ 参数说明详细
- ✅ 示例易于理解

## 对比现有节点

### 与 `wservice.merge_with_word_timestamps` 的区别

| 特性 | merge_with_word_timestamps | merge_speaker_based_subtitles |
|------|----------------------------|-------------------------------|
| 时间基准 | 转录文件 (45 segments) | Diarization 文件 (58 segments) |
| 输出数量 | 45 个 segments | 58 个 segments |
| 主要用途 | 语义连贯的字幕 | 说话人优先的字幕 |
| 新增参数 | - | `overlap_threshold` |
| 新增输出 | - | `total_segments`, `matched_segments`, `empty_segments` |

## 文档更新统计

- **新增行数**: 63 行
- **插入位置**: 第 1260 行
- **影响范围**: 后续行号 +63
- **修改文件**: 1 个

## 相关文件

### 已更新
- ✅ `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`

### 模板文件
- `openspec/changes/add-speaker-based-subtitle-merger/SINGLE_TASK_API_REFERENCE_template.md`

### 其他文档（待更新）
- ⚠️ `docs/nodes/wservice/merge_speaker_based_subtitles.md` (未创建)
- ⚠️ `docs/api/nodes.md` (未更新)

## 后续建议

### 优先级 P1（建议）
1. 创建详细的节点使用文档: `docs/nodes/wservice/merge_speaker_based_subtitles.md`
   - 功能详解
   - 使用场景
   - 完整示例
   - 常见问题

2. 更新 API 索引: `docs/api/nodes.md`
   - 添加新节点到索引
   - 更新节点列表

### 优先级 P2（可选）
1. 添加中文文档版本
2. 添加更多使用示例
3. 添加故障排查指南

## 验证命令

### 检查文档存在性
```bash
grep -n "wservice.merge_speaker_based_subtitles" \
  docs/technical/reference/SINGLE_TASK_API_REFERENCE.md
```

### 查看文档内容
```bash
sed -n '1260,1322p' \
  docs/technical/reference/SINGLE_TASK_API_REFERENCE.md
```

### 验证节点顺序
```bash
grep "^#### wservice" \
  docs/technical/reference/SINGLE_TASK_API_REFERENCE.md
```

## 结论

✅ **文档同步完成**

新节点 `wservice.merge_speaker_based_subtitles` 的 API 参考文档已成功添加到 `SINGLE_TASK_API_REFERENCE.md`，格式正确，内容完整，位置合理。

文档遵循现有格式规范，包含所有必需部分，示例真实可用，可立即供用户参考使用。

---

**更新人**: Claude Code
**更新日期**: 2025-12-25
**文档版本**: v1.0
**状态**: ✅ 已完成

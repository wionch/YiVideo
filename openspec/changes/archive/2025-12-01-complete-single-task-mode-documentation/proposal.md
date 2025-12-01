# 变更: 完善YiVideo工作流节点文档中单任务模式参数说明

## 为什么

YiVideo系统已经实现了完整的单任务模式支持，包括独立的API接口 (`/v1/tasks`) 和统一的参数获取机制 (`get_param_with_fallback`)。然而，当前的文档中关于单任务模式的支持并不完整：

1. **部分节点缺少单任务模式说明** - 并非所有节点都明确说明了单任务模式的使用方法
2. **参数说明不一致** - 一些节点的参数来源说明不够清晰，缺少对 `input_data` 支持的明确说明
3. **示例不足** - 大多数节点缺少单任务模式的具体调用示例
4. **代码与文档不一致** - 需要验证所有节点是否真的支持单任务模式，确保文档与实现一致

## 什么会改变

### 需要检查和补充的节点 (按服务分类)

#### FFmpeg 服务节点
- [ ] `ffmpeg.extract_keyframes` - 检查单任务模式参数说明
- [ ] `ffmpeg.extract_audio` - 检查单任务模式参数说明  
- [ ] `ffmpeg.crop_subtitle_images` - 检查单任务模式参数说明
- [ ] `ffmpeg.split_audio_segments` - 检查单任务模式参数说明

#### Faster-Whisper 服务节点
- [ ] `faster_whisper.transcribe_audio` - 检查单任务模式参数说明

#### Audio Separator 服务节点  
- [ ] `audio_separator.separate_vocals` - 检查单任务模式参数说明

#### Pyannote Audio 服务节点
- [ ] `pyannote_audio.diarize_speakers` - 检查单任务模式参数说明
- [ ] `pyannote_audio.get_speaker_segments` - 检查单任务模式参数说明
- [ ] `pyannote_audio.validate_diarization` - 检查单任务模式参数说明

#### PaddleOCR 服务节点
- [ ] `paddleocr.detect_subtitle_area` - 检查单任务模式参数说明
- [ ] `paddleocr.create_stitched_images` - 检查单任务模式参数说明
- [ ] `paddleocr.perform_ocr` - 检查单任务模式参数说明
- [ ] `paddleocr.postprocess_and_finalize` - 检查单任务模式参数说明

#### IndexTTS 服务节点
- [ ] `indextts.generate_speech` - 检查单任务模式参数说明
- [ ] `indextts.list_voice_presets` - 检查单任务模式参数说明
- [ ] `indextts.get_model_info` - 检查单任务模式参数说明

#### WService 字幕优化服务节点
- [ ] `wservice.generate_subtitle_files` - 检查单任务模式参数说明
- [ ] `wservice.correct_subtitles` - 检查单任务模式参数说明
- [ ] `wservice.ai_optimize_subtitles` - 检查单任务模式参数说明
- [ ] `wservice.merge_speaker_segments` - 检查单任务模式参数说明
- [ ] `wservice.merge_with_word_timestamps` - 检查单任务模式参数说明
- [ ] `wservice.prepare_tts_segments` - 检查单任务模式参数说明

### 需要完善的文档内容

#### 1. 统一单任务模式说明格式
为每个节点补充以下标准格式的说明：

```markdown
### 单任务模式支持

**输入参数**:
- `参数名` (类型, 必需/可选): 参数描述，支持 `${{...}}` 动态引用

**单任务调用示例**:
```json
{
    "task_name": "service_name.node_name",
    "input_data": {
        "参数名": "参数值"
    }
}
```

**参数来源说明**:
- `参数名`: **节点参数** (在请求体中的 `service_name.node_name` 对象内提供)
- 其他参数均为全局配置或从上游节点自动获取
```

#### 2. 参数代码一致性验证
检查每个节点的代码实现，确保：
- 使用了 `get_param_with_fallback` 函数
- 支持从 `input_data` 获取参数
- 优先从显式参数获取，然后从 `input_data` 回退

#### 3. 输出格式一致性验证
检查每个节点的输出格式，确保：
- 文档中的输出格式与实际代码输出一致
- 包含所有重要输出字段
- 字段描述准确

#### 4. 补充缺失的参数说明
为缺少说明的参数添加完整描述：
- 参数类型
- 必需/可选
- 默认值
- 支持的格式和取值范围
- 使用说明

## 影响

### 受影响的文档
- `docs/technical/reference/WORKFLOW_NODES_REFERENCE.md` - 主要工作流节点参考文档

### 受影响的代码文件（可能需要小幅修正）
- 各服务节点的 `tasks.py` 文件（如果发现实现与文档不一致）
- 可能需要修正参数名称或默认值

### 验证工作
- 检查所有节点是否正确使用 `get_param_with_fallback`
- 验证单任务模式调用示例的实际可用性
- 确保文档描述与代码实现完全一致

### 风险评估
- **低风险**: 这是文档完善任务，不改变现有API或功能
- **向后兼容**: 保持所有现有参数和接口不变
- **回退方案**: 如发现实现问题，可选择性修正代码，或在文档中明确说明限制

## 验证标准

1. **完整性**: 所有工作流节点都有完整的单任务模式说明
2. **一致性**: 文档描述与代码实现完全一致
3. **可用性**: 所有单任务模式调用示例都能正常工作
4. **准确性**: 参数说明、类型、默认值全部准确
5. **格式统一**: 所有节点使用相同的说明格式和结构
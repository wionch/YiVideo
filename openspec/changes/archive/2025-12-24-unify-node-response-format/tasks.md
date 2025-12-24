# Tasks: 统一节点响应格式与参数处理

## 阶段 1：基础设施建设（第 1-3 周）

### T1.1 设计统一响应规范
- **描述**：定义 `NodeResponseSpecification` 文档，明确所有节点必须遵循的响应格式规范
- **验证**：规范文档通过团队评审
- **依赖**：无
- **优先级**：P0（阻塞后续任务）
- **预估工作量**：2 天

### T1.2 实现 BaseNodeExecutor 抽象基类
- **描述**：创建 `services/common/base_node_executor.py`，提供统一的节点执行接口
- **验证**：
  - 单元测试覆盖率 ≥ 90%
  - 抽象方法包括：`execute()`, `validate_input()`, `get_cache_key()`, `format_output()`
- **依赖**：T1.1
- **优先级**：P0
- **预估工作量**：3 天

### T1.3 实现 NodeResponseValidator 验证器
- **描述**：创建 `services/common/validators/node_response_validator.py`，验证节点响应格式
- **验证**：
  - 能检测所有已知的不一致问题（响应结构、字段命名、MinIO URL）
  - 提供详细的验证错误报告
- **依赖**：T1.2
- **优先级**：P0
- **预估工作量**：2 天

### T1.4 建立 MinioUrlNamingConvention 规范
- **描述**：创建 `services/common/minio_url_convention.py`，实现自动化的 MinIO URL 字段命名
- **验证**：
  - 支持规则：`{field_name}_minio_url`（保留完整前缀）
  - 支持数组字段：`{field_name}_minio_urls`
  - 单元测试覆盖所有边界情况
- **依赖**：T1.2
- **优先级**：P0
- **预估工作量**：2 天

### T1.5 增强 ParameterResolver
- **描述**：扩展现有的 `services/common/parameter_resolver.py`，添加智能回退逻辑文档化
- **验证**：
  - 所有"智能源选择"逻辑有明确的回退顺序定义
  - 回退失败时抛出清晰的错误信息
  - 集成测试验证回退链
- **依赖**：T1.2
- **优先级**：P1
- **预估工作量**：3 天

### T1.6 设计 CacheKeyStrategy 接口
- **描述**：创建 `services/common/cache_key_strategy.py`，统一复用判定逻辑
- **验证**：
  - 每个节点明确声明缓存键字段
  - 支持多字段组合键
  - 单元测试覆盖率 ≥ 90%
- **依赖**：T1.2
- **优先级**：P1
- **预估工作量**：2 天

### T1.7 创建数据溯源规范
- **描述**：定义 `DataProvenance` 模型，统一数据来源标记
- **验证**：
  - 所有节点在 `output.provenance` 中标记数据来源
  - 包含 `source_stage`, `source_field`, `fallback_chain` 字段
- **依赖**：T1.2
- **优先级**：P2
- **预估工作量**：1 天

## 阶段 2：高优先级节点迁移（第 4-5 周）

### T2.1 迁移 FFmpeg 系列节点（4 个）
- **描述**：重构以下节点以继承 BaseNodeExecutor：
  - `ffmpeg.extract_keyframes`
  - `ffmpeg.extract_audio`
  - `ffmpeg.crop_subtitle_images`
  - `ffmpeg.split_audio_segments`
- **验证**：
  - 所有节点通过 NodeResponseValidator 验证
  - 集成测试验证响应格式
  - MinIO URL 字段命名符合规范
- **依赖**：T1.2, T1.3, T1.4
- **优先级**：P0
- **预估工作量**：5 天
- **可并行**：与 T2.2 并行

### T2.2 迁移 Faster-Whisper 节点
- **描述**：重构 `faster_whisper.transcribe_audio` 节点
- **验证**：
  - 统一状态字段命名（`status="SUCCESS"` 而非混合大小写）
  - 统一时长字段（仅使用 `duration`，移除 `transcribe_duration`）
  - 通过验证器测试
- **依赖**：T1.2, T1.3
- **优先级**：P0
- **预估工作量**：2 天
- **可并行**：与 T2.1 并行

### T2.3 迁移 Audio Separator 节点
- **描述**：重构 `audio_separator.separate_vocals` 节点
- **验证**：
  - 修复 `all_audio_files` → `all_audio_files_minio_urls` 命名
  - 统一复用判定逻辑（明确检查 `vocal_audio` 字段）
- **依赖**：T1.2, T1.4
- **优先级**：P0
- **预估工作量**：2 天

## 阶段 3：中优先级节点迁移（第 5-6 周）

### T3.1 迁移 Pyannote Audio 系列节点（3 个）
- **描述**：重构以下节点：
  - `pyannote_audio.diarize_speakers`
  - `pyannote_audio.get_speaker_segments`（修复返回格式）
  - `pyannote_audio.validate_diarization`（修复返回格式）
- **验证**：
  - **关键**：`get_speaker_segments` 和 `validate_diarization` 从 `success/data` 格式迁移到 WorkflowContext
  - 所有节点返回一致的结构
- **依赖**：T1.2, T1.3
- **优先级**：P1
- **预估工作量**：4 天

### T3.2 迁移 PaddleOCR 系列节点（4 个）
- **描述**：重构以下节点：
  - `paddleocr.detect_subtitle_area`
  - `paddleocr.create_stitched_images`
  - `paddleocr.perform_ocr`
  - `paddleocr.postprocess_and_finalize`
- **验证**：
  - 修复 `keyframe_dir` → `keyframe_dir_minio_url`（保留 `_dir`）
  - 修复 `multi_frames_path` → `multi_frames_path_minio_url`（保留 `_path`）
  - 统一压缩信息字段命名
- **依赖**：T1.2, T1.4
- **优先级**：P1
- **预估工作量**：5 天

### T3.3 迁移 IndexTTS 节点
- **描述**：重构 `indextts.generate_speech` 节点
- **验证**：
  - **关键**：从普通任务字典格式迁移到 WorkflowContext
  - 统一状态字段（`status="SUCCESS"` 而非 `"success"`）
  - 统一时长字段（`duration` 而非 `processing_time`）
- **依赖**：T1.2, T1.3
- **优先级**：P1
- **预估工作量**：2 天

## 阶段 4：WService 节点迁移（第 6 周）

### T4.1 迁移 WService 字幕优化系列节点（6 个）
- **描述**：重构以下节点：
  - `wservice.generate_subtitle_files`
  - `wservice.correct_subtitles`
  - `wservice.ai_optimize_subtitles`
  - `wservice.merge_speaker_segments`
  - `wservice.merge_with_word_timestamps`
  - `wservice.prepare_tts_segments`
- **验证**：
  - 修复文档与实现的矛盾（如 `merge_speaker_segments` 的输出字段）
  - 统一数据溯源字段位置（使用 `output.provenance`）
  - 所有节点通过验证器测试
- **依赖**：T1.2, T1.3, T1.7
- **优先级**：P1
- **预估工作量**：6 天

## 阶段 5：文档与测试（第 7 周）

### T5.1 更新 API 参考文档
- **描述**：重写 `docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
- **验证**：
  - 所有节点示例与实际输出一致
  - 消除所有文档矛盾（如 `correct_subtitles` 的说明）
  - 添加统一的字段命名规范说明
  - 添加复用判定机制说明
- **依赖**：T2.*, T3.*, T4.*
- **优先级**：P0
- **预估工作量**：3 天

### T5.2 创建响应格式迁移指南
- **描述**：编写客户端迁移文档 `docs/migration/node-response-format-v2.md`
- **验证**：
  - 包含旧格式 vs 新格式对比
  - 提供迁移检查清单
  - 包含常见问题解答
- **依赖**：T5.1
- **优先级**：P1
- **预估工作量**：1 天

### T5.3 实现集成测试套件
- **描述**：创建 `tests/integration/test_node_response_format.py`
- **验证**：
  - 测试所有 18 个节点的响应格式
  - 验证 MinIO URL 字段命名
  - 验证复用判定逻辑
  - 验证数据溯源字段
- **依赖**：T2.*, T3.*, T4.*
- **优先级**：P0
- **预估工作量**：3 天

### T5.4 性能基准测试
- **描述**：验证新验证层不会显著影响性能
- **验证**：
  - 响应时间增加 < 5%
  - 内存使用增加 < 10%
- **依赖**：T5.3
- **优先级**：P2
- **预估工作量**：1 天

## 阶段 6：兼容性与发布（第 8 周）

### T6.1 实现兼容性层
- **描述**：在 `single_task_api.py` 中添加 `legacy_format` 参数支持
- **验证**：
  - 旧客户端可通过参数继续使用旧格式
  - 响应头包含 `X-Response-Format-Version`
- **依赖**：T5.3
- **优先级**：P1
- **预估工作量**：2 天

### T6.2 创建废弃时间表
- **描述**：制定旧格式废弃计划和通知机制
- **验证**：
  - 明确的废弃日期（建议 6 个月后）
  - 自动化的废弃警告日志
- **依赖**：T6.1
- **优先级**：P2
- **预估工作量**：1 天

### T6.3 发布与监控
- **描述**：部署到生产环境并监控
- **验证**：
  - 无客户端报错
  - 响应时间符合预期
  - 日志中无格式验证错误
- **依赖**：T6.1, T6.2
- **优先级**：P0
- **预估工作量**：2 天

## 任务依赖图

```
T1.1 (规范设计)
  ↓
T1.2 (BaseNodeExecutor) ← 阻塞所有迁移任务
  ↓
  ├─→ T1.3 (验证器) ─→ T2.1, T2.2, T3.1, T3.3
  ├─→ T1.4 (MinIO规范) ─→ T2.1, T2.3, T3.2
  ├─→ T1.5 (参数解析器)
  ├─→ T1.6 (缓存策略)
  └─→ T1.7 (数据溯源) ─→ T4.1

T2.1, T2.2, T2.3 (并行) ─┐
T3.1, T3.2, T3.3 (并行) ─┤
T4.1                     ─┤
                          ↓
                       T5.1 (文档更新)
                          ↓
                       T5.2 (迁移指南)
                          ↓
                       T5.3 (集成测试)
                          ↓
                       T6.1 (兼容性层)
                          ↓
                       T6.3 (发布)
```

## 关键路径

T1.1 → T1.2 → T1.3 → T2.1 → T5.1 → T5.3 → T6.1 → T6.3

**总预估时间**：8 周（假设 1 名全职开发者）

## 风险缓解任务

- **R1**：如果迁移过程中发现无法向后兼容的破坏性变更
  - **缓解任务**：T6.1 提供兼容性层，T6.2 制定废弃计划

- **R2**：如果性能测试未通过（T5.4）
  - **缓解任务**：优化验证逻辑，仅在开发环境启用严格验证

- **R3**：如果客户端迁移成本过高
  - **缓解任务**：延长兼容性层支持周期（从 6 个月延长到 12 个月）

# S2ST 工作流实现计划

## 目标
为 YiVideo 项目实现完整的 Speech-to-Speech Translation (S2ST) 工作流，包括字幕优化、翻译装词、语音生成和视频合并功能。

## 上下文
- 项目基础：YiVideo Celery 架构，已完成基础节点功能
- 参考文档：`docs/technical/reference/SINGLE_TASK_API_REFERENCE.md`
- 转录数据样例：`share/workflows/video_to_subtitle_task/nodes/faster_whisper.transcribe_audio/data/transcribe_data_video_to.json`
- 数据结构：segments (id, text, start, end, words with timestamps)

## 实施阶段

### Phase 0: 前置调研与设计 [completed] ✅
**目标**: 收集行业标准和技术方案，设计系统架构
**任务**:
- [x] 调研字幕时长和字数的行业标准
- [x] 调研翻译装词的行业最佳实践
- [x] 调研 Edge-TTS SSML 功能和时长控制机制
- [x] 调研 IndexTTS2 参考音功能和 SSML 支持
- [x] 调研语音时长对齐的主流解决方案
- [x] 调研 ffmpeg rubberband 优化措施
- [x] 设计整体数据流和接口规范 ✅ 完成于 2026-01-18
   - 📄 文档：findings.md 第 7 章（7.1-7.7 节）
- [x] 设计 LLM API 选择和配置 ✅ 完成于 2026-01-18
   - 📄 文档：findings.md 第 8 章（8.1-8.8 节）
**产出**:
- ✅ findings.md (完整调研报告，2.1-3.4 节)
- ✅ 6 个重要技术发现
- ✅ 数据结构设计文档（findings.md 第 7 章）
- ✅ LLM API 配置方案（findings.md 第 8 章）
**完成日期**: 2026-01-18（全部完成）

### Phase 1: LLM 字幕优化功能 [design_completed] ✅ 设计完成 | ⏳ 实施待开始
**目标**: 实现基于 LLM 的字幕断句、纠错和合并/拆分功能
**子任务**:
1. [x] 设计极简指令集（单字符键映射）✅ 完成于 2026-01-17
   - ✅ 断句优化指令：移动操作 (m)
   - ✅ 合并指令：合并操作 (g)
   - ✅ 拆分指令：拆分操作 (s)
   - ✅ 纠错指令：替换操作 (r)
   - 📄 文档：findings.md 4.1 节
2. [x] 设计 system prompt 和提交 prompt 模板 ✅ 完成于 2026-01-17
   - 📄 文档：findings.md 4.2-4.3 节
3. [x] 设计并发处理逻辑（考虑重叠窗口）✅ 完成于 2026-01-17
   - 📄 文档：findings.md 5.1 节
4. [x] 设计数据提取模块实现逻辑 ✅ 完成于 2026-01-18
   - 📄 文档：findings.md 9.1 节
5. [x] 设计数据重构模块完整流程 ✅ 完成于 2026-01-18
   - 📄 文档：findings.md 9.2 节（含 4 种操作的伪代码）
6. [x] 设计指令集验证机制 ✅ 完成于 2026-01-18
   - 📄 文档：findings.md 9.3 节
7. [x] 设计 YiVideo 架构集成 ✅ 完成于 2026-01-18
   - 📄 文档：findings.md 9.4 节（BaseNodeExecutor + Celery 任务）
8. [x] 设计性能优化与配置 ✅ 完成于 2026-01-18
   - 📄 文档：findings.md 9.5 节
9. [ ] 实现数据提取模块（编写实际代码）
10. [ ] 实现数据重构模块（编写实际代码）
11. [ ] 创建 Celery 任务和 BaseNodeExecutor
12. [ ] 单元测试和集成测试
**产出**:
- `services/workers/subtitle_optimizer_service/`
- 优化后的字幕文件（保持原数据结构）
**依赖**: Phase 0
**预计完成**: Phase 1 完成后更新

### Phase 2: LLM 翻译装词功能 [design_completed] ✅ 设计完成 | ⏳ 实施待开始
**目标**: 实现考虑时长对齐的翻译装词功能
**子任务**:
1. [x] 设计翻译装词的 system prompt（强调时长对齐）✅ 完成于 2026-01-18
   - 📄 文档：findings.md 6.2 节
2. [x] 设计提交 prompt 模板（包含时长约束）✅ 完成于 2026-01-18
   - 📄 文档：findings.md 6.2 节
3. [x] 设计时长验证和调整逻辑 ✅ 完成于 2026-01-18
   - 📄 文档：findings.md 6.2 节
4. [x] 设计并发处理策略（上下文窗口）✅ 完成于 2026-01-18
   - 📄 文档：findings.md 6.2 节
5. [ ] 实现翻译请求处理逻辑
6. [ ] 创建 Celery 任务和 BaseNodeExecutor
7. [ ] 单元测试和集成测试
**产出**:
- `services/workers/subtitle_translator_service/`
- 翻译后的字幕文件（保持原数据结构+时间戳）
**依赖**: Phase 1
**预计完成**: Phase 2 完成后更新

### Phase 3: IndexTTS2 语音生成 [design_completed] ✅ 设计完成 | ⏳ 实施待开始
**目标**: 实现基于 IndexTTS2 的语音生成和时长对齐
**子任务**:
1. [x] 设计参考音提取策略（全局提取）✅ 完成于 2026-01-18
   - 📄 文档：findings.md 6.3 节
2. [x] 设计参考音时长调整（crossfade 拼接）✅ 完成于 2026-01-18
   - 📄 文档：findings.md 6.3 节
3. [x] 设计 4 阶段生成流程 ✅ 完成于 2026-01-18
   - 📄 文档：findings.md 6.3 节
4. [x] 设计 Rubberband 时长对齐参数 ✅ 完成于 2026-01-18
   - 📄 文档：findings.md 6.3 节
5. [x] 设计并发策略和性能优化 ✅ 完成于 2026-01-18
   - 📄 文档：findings.md 6.3 节
6. [ ] 集成 IndexTTS2 项目依赖
7. [ ] 实现参考音提取和调整逻辑
8. [ ] 实现语音生成和时长对齐逻辑
9. [ ] 创建 Celery 任务和 BaseNodeExecutor
10. [ ] 单元测试和集成测试
**产出**:
- `services/workers/indextts_service/` (已存在，需扩展)
- 语音文件列表（时长对齐）
**依赖**: Phase 0, Phase 2
**预计完成**: Phase 3 完成后更新

### Phase 4: Edge-TTS 语音生成 [design_completed] ✅ 设计完成 | ⏳ 实施待开始
**目标**: 实现基于 Edge-TTS 的快速语音生成
**子任务**:
1. [x] 设计时长对齐策略（一次生成 + Rubberband）✅ 完成于 2026-01-18
   - 📄 文档：findings.md 6.4 节
2. [x] 设计音色选择机制（speaker → voice 映射）✅ 完成于 2026-01-18
   - 📄 文档：findings.md 6.4 节
3. [x] 设计 4 阶段生成流程 ✅ 完成于 2026-01-18
   - 📄 文档：findings.md 6.4 节
4. [x] 设计并发策略和性能优化 ✅ 完成于 2026-01-18
   - 📄 文档：findings.md 6.4 节
5. [ ] 集成 Edge-TTS 依赖
6. [ ] 实现音色选择和生成逻辑
7. [ ] 实现 Rubberband 时长对齐逻辑
8. [ ] 创建 Celery 任务和 BaseNodeExecutor
9. [ ] 单元测试和集成测试
**产出**:
- `services/workers/edgetts_service/`
- 语音文件列表（SSML 时长控制+兜底对齐）
**依赖**: Phase 0, Phase 2
**预计完成**: Phase 4 完成后更新

### Phase 5: 视频合并功能 [design_completed] ✅ 设计完成 | ⏳ 实施待开始
**目标**: 实现音视频字幕合并
**子任务**:
1. [x] 设计音频拼接和混合策略 ✅ 完成于 2026-01-18
   - 📄 文档：findings.md 6.5.2-6.5.3 节
2. [x] 设计字幕处理策略（硬/软/both/none）✅ 完成于 2026-01-18
   - 📄 文档：findings.md 6.5.4 节
3. [x] 设计视频编码策略 ✅ 完成于 2026-01-18
   - 📄 文档：findings.md 6.5.5 节
4. [x] 设计 4 阶段处理流程 ✅ 完成于 2026-01-18
   - 📄 文档：findings.md 6.5.6 节
5. [x] 设计音画同步验证机制 ✅ 完成于 2026-01-18
   - 📄 文档：findings.md 6.5.7 节
6. [ ] 实现音频拼接和混合逻辑
7. [ ] 实现视频编码和字幕烧录
8. [ ] 创建 Celery 任务和 BaseNodeExecutor
9. [ ] 单元测试和集成测试
**产出**:
- `services/workers/ffmpeg_service/` (扩展现有)
- 最终 S2ST 视频文件
**依赖**: Phase 3 或 Phase 4
**预计完成**: Phase 5 完成后更新

### Phase 6: 文档与集成测试 [pending]
**目标**: 完善文档和端到端测试
**子任务**:
1. [ ] 更新 SINGLE_TASK_API_REFERENCE.md
2. [ ] 编写 S2ST 工作流示例
3. [ ] 端到端集成测试
4. [ ] 性能测试和优化
**产出**:
- 完整 API 文档
- S2ST 工作流示例
**依赖**: Phase 1-5
**预计完成**: Phase 6 完成后更新

## 关键决策日志

### 决策 1: 指令集设计原则 ✅
**日期**: 2026-01-17
**问题**: 如何设计 LLM 返回的指令集以最小化 token 消耗？
**选择**: 使用单字符键名 + 词索引操作
**原因**:
- 节省 40-60% token 消耗
- 基于词索引保留时间戳信息
- 本地负责重构,LLM 只返回指令
**文档**: findings.md 4.1 节

### 决策 2: 并发处理策略 ✅
**日期**: 2026-01-17
**问题**: 如何设计并发提交以平衡速度和连贯性？
**选择**:
- Phase 1: 窗口 150 segments + 重叠 10 segments
- Phase 2: 窗口 100 segments + 重叠 6 segments (上下文)
**原因**:
- 确保字幕语义连贯（上下文参考）
- 避免跨批次冲突（重叠区域）
- 顺序处理确保正确性
**文档**: findings.md 5.1 节, 6.2 节

### 决策 3: 时长对齐策略 ✅
**日期**: 2026-01-17
**问题**: IndexTTS2 vs Edge-TTS 的时长对齐方案？
**选择**:
- IndexTTS2: 一次生成 + Rubberband 完整对齐
- Edge-TTS: 一次生成 + Rubberband 完整对齐（不使用 rate 预调整）
**原因**:
- 两个 TTS 都不支持精确时长控制
- Phase 2 翻译装词已做字符数优化
- Rubberband 在 ±10% 范围内几乎无损
**文档**: findings.md 6.3 节, 6.4 节

### 决策 4: 参考音提取策略 ✅
**日期**: 2026-01-18
**问题**: IndexTTS2 参考音如何提取？
**选择**: 每个说话人提取一次全局参考音
**原因**:
- 保证同一说话人音色一致
- 减少 IO 操作
- 可以确保参考音时长充足（通过拼接）
**文档**: findings.md 6.3 节

### 决策 5: 翻译装词优先级 ✅
**日期**: 2026-01-18
**问题**: 翻译质量 vs 时长对齐,如何权衡？
**选择**: 时长对齐 > 语义准确
**原因**:
- S2ST 场景下音画同步是刚需
- 时长偏差会导致明显的异步感
- 语义可以适当简化表达
**文档**: findings.md 6.2 节

### 决策 6: 视频合并字幕模式 ✅
**日期**: 2026-01-18
**问题**: 软字幕 vs 硬字幕？
**选择**: 默认硬字幕（burned-in）
**原因**:
- S2ST 视频通常用于分享
- 需要兼容所有平台
- 翻译字幕是核心内容
**文档**: findings.md 6.5.4 节

### 决策 7: 数据流和接口设计 ✅
**日期**: 2026-01-18
**问题**: 如何设计标准化的数据流和节点接口？
**选择**:
- 使用统一 Segment 格式贯穿整个工作流
- 所有节点统一 `input_data` + `output JSON` 模式
- 缓存键基于文件内容哈希 + 参数序列化
**原因**:
- Segment 格式与 Faster-Whisper 输出兼容，无需转换
- 统一接口模式简化节点开发和维护
- 内容哈希确保缓存准确性（路径变化不影响）
**文档**: findings.md 第 7 章（7.1-7.7 节）

### 决策 8: LLM Provider 选择 ✅
**日期**: 2026-01-18
**问题**: 选择哪个 LLM Provider？如何设计重试和 Fallback？
**选择**:
- 默认 DeepSeek（主）+ Gemini（fallback）
- 3 层重试策略：单次重试 → Provider 切换 → 批次降级
- Phase 1 使用 temperature=0.1，Phase 2 使用 temperature=0.3
**原因**:
- DeepSeek 成本极低（$0.001/1M tokens）且中文支持好
- Gemini 免费额度大，作为高可用性保障
- 3 层重试确保鲁棒性
- 不同 temperature 平衡准确性和创造性
**文档**: findings.md 第 8 章（8.1-8.8 节）

## 遇到的错误

| 错误 | 尝试次数 | 解决方案 | 状态 |
|------|---------|---------|------|
| - | - | - | - |

## 风险与依赖

### 风险
1. LLM API 成本控制（需要优化 token 使用）
2. 时长对齐精度（可能需要多次迭代优化）
3. 并发处理的语义连贯性（需要设计重叠窗口）

### 外部依赖
1. IndexTTS2 项目集成
2. Edge-TTS 库集成
3. LLM API (DEEPSEEK/GEMINI/CLAUDE)

## 下一步行动
1. ~~开始 Phase 0 调研工作~~ ✅ 已完成
2. ~~创建 findings.md 记录调研结果~~ ✅ 已完成
3. ~~设计数据结构和接口规范~~ ✅ 已完成
4. **开始 Phase 1 实施**：创建 subtitle_optimizer_service
5. **实施顺序建议**：Phase 1 → Phase 2 → Phase 3/4 (并行) → Phase 5

# WhisperX 功能拆分测试计划

## 测试概述

本文档详细描述了WhisperX功能拆分后的测试策略、测试用例和验证标准。确保拆分后的系统功能完整性、性能稳定性和向后兼容性。

## 🎯 测试目标

### 1. 功能完整性测试
- 验证每个独立任务节点的功能正确性
- 确保数据流在任务间正确传递
- 验证输出格式和内容的一致性

### 2. 性能验证测试
- 对比拆分前后的执行效率
- 验证GPU锁机制的稳定性
- 测试并发处理能力

### 3. 向后兼容性测试
- 确保原有API和工作流无需修改
- 验证输出格式的一致性
- 测试配置参数的兼容性

### 4. 错误处理测试
- 验证任务失败时的故障隔离
- 测试各种异常情况的处理
- 验证错误传播和恢复机制

## 📋 测试环境准备

### 硬件环境
- **GPU**: NVIDIA RTX 3080+ (8GB+ 显存)
- **CPU**: 8核+ 处理器
- **内存**: 16GB+ RAM
- **存储**: 100GB+ 可用空间

### 软件环境
- Docker + Docker Compose
- Redis 6.0+
- Python 3.9+
- CUDA 11.0+ (GPU模式)

### 测试数据
```
test_videos/
├── single_speaker.mp4      # 单人说话 (5分钟)
├── multi_speaker.mp4       # 多人对话 (10分钟)
├── noisy_background.mp4    # 嘈杂背景 (8分钟)
├── meeting_record.mp4      # 会议记录 (15分钟)
├── interview.mp4           # 访谈节目 (12分钟)
└── short_test.mp4          # 短测试视频 (1分钟)
```

## 🧪 功能测试用例

### TC001: 基础转录任务测试 (whisperx.transcribe_audio)

**测试目标：** 验证独立转录任务的功能正确性

**前置条件：**
- Docker环境正常运行
- 测试视频文件已准备

**测试步骤：**
1. 启动基础字幕工作流
```yaml
basic_test_workflow:
  workflow_chain:
    - "ffmpeg.extract_audio"
    - "whisperx.transcribe_audio"
```

2. 提交测试任务
```bash
curl -X POST http://localhost:8788/v1/workflows \
  -H "Content-Type: application/json" \
  -d '{
    "workflow_name": "basic_test_workflow",
    "params": {
      "video_path": "/test_videos/single_speaker.mp4"
    }
  }'
```

3. 监控任务执行状态
4. 验证输出结果

**预期结果：**
- 任务状态：SUCCESS
- 输出文件：transcribe_data_*.json
- 转录文本准确率 > 90%
- 词级时间戳正确生成

**验证点：**
- [ ] 转录片段数量合理
- [ ] 文本内容准确
- [ ] 时间戳连续性
- [ ] 语言检测正确
- [ ] GPU锁正常获取和释放

### TC002: 说话人分离任务测试 (whisperx.diarize_speakers)

**测试目标：** 验证独立说话人分离任务的功能正确性

**前置条件：**
- TC001测试通过
- 多人说话测试数据

**测试步骤：**
1. 启动完整字幕工作流
```yaml
full_test_workflow:
  workflow_chain:
    - "ffmpeg.extract_audio"
    - "whisperx.transcribe_audio"
    - "whisperx.diarize_speakers"
```

2. 使用多人对话视频测试
3. 监控说话人分离过程

**预期结果：**
- 成功识别多个说话人
- 说话人标签准确分配
- 统计信息正确生成

**验证点：**
- [ ] 检测到说话人数量正确
- [ ] 说话人转换点准确
- [ ] 说话人统计信息合理
- [ ] GPU锁在本地CUDA模式下正常工作
- [ ] 付费模式回退机制正常

### TC003: 字幕文件生成任务测试 (whisperx.generate_subtitle_files)

**测试目标：** 验证字幕文件生成的完整性和格式正确性

**前置条件：**
- TC001或TC002测试通过

**测试步骤：**
1. 启动字幕生成工作流
2. 验证各种输入模式
3. 检查输出文件格式

**预期结果：**
- 基础SRT文件正确生成
- 带说话人信息的SRT文件正确生成
- JSON格式文件结构正确

**验证点：**
- [ ] SRT时间格式正确 (HH:MM:SS,mmm)
- [ ] 字幕序号连续
- [ ] 文本内容无乱码
- [ ] 说话人标签格式正确
- [ ] JSON文件结构验证
- [ ] 元数据信息完整

### TC004: 完整工作流集成测试

**测试目标：** 验证三个任务节点的协同工作

**测试步骤：**
1. 启动完整工作流
```yaml
integration_test_workflow:
  workflow_chain:
    - "ffmpeg.extract_audio"
    - "audio_separator.separate_vocals"
    - "whisperx.transcribe_audio"
    - "whisperx.diarize_speakers"
    - "whisperx.generate_subtitle_files"
```

2. 使用不同类型的测试视频
3. 验证数据传递正确性

**验证点：**
- [ ] 任务间数据传递无误
- [ ] 音频源选择逻辑正确
- [ ] 说话人信息正确传递
- [ ] 最终输出文件完整

## 🚀 性能测试用例

### TC005: 性能基准对比测试

**测试目标：** 对比拆分前后的性能表现

**测试方法：**
1. 使用相同测试数据运行原有单一任务
2. 使用新工作流运行相同测试
3. 对比关键性能指标

**测试指标：**
- 总执行时间
- GPU利用率
- 内存使用峰值
- CPU使用率

**预期结果：**
- 总执行时间差异 < 10%
- GPU利用率保持稳定
- 内存使用无明显增加

### TC006: GPU锁并发测试

**测试目标：** 验证GPU锁在高并发场景下的稳定性

**测试步骤：**
1. 同时提交多个GPU任务
2. 监控GPU锁状态
3. 验证任务排队机制

**验证点：**
- [ ] GPU锁正确获取和释放
- [ ] 任务按预期排队执行
- [ ] 无死锁或资源泄漏
- [ ] 锁超时机制正常工作

### TC007: 内存泄漏测试

**测试目标：** 确保拆分后不会产生内存泄漏

**测试方法：**
1. 连续执行多个任务
2. 监控内存使用情况
3. 检查显存清理效果

**验证点：**
- [ ] 内存使用稳定
- [ ] GPU显存正确释放
- [ ] 无内存泄漏迹象

## 🔄 兼容性测试用例

### TC008: 向后兼容性测试

**测试目标：** 确保原有API完全兼容

**测试步骤：**
1. 使用原有工作流配置
```yaml
legacy_test_workflow:
  workflow_chain:
    - "ffmpeg.extract_audio"
    - "whisperx.generate_subtitles"
```

2. 使用原有配置参数
3. 验证输出格式一致性

**验证点：**
- [ ] 原有工作流正常运行
- [ ] 输出格式完全一致
- [ ] 性能表现相当
- [ ] 配置参数兼容

### TC009: 配置迁移测试

**测试目标：** 验证从原有配置迁移到新配置的可行性

**测试步骤：**
1. 提取原有配置参数
2. 转换为新工作流配置
3. 验证功能一致性

**验证点：**
- [ ] 配置参数正确映射
- [ ] 功能表现一致
- [ ] 输出质量相当

## ⚠️ 错误处理测试用例

### TC010: 任务失败隔离测试

**测试目标：** 验证单个任务失败不影响其他任务

**测试场景：**
1. 转录任务失败 → 后续任务跳过
2. 说话人分离失败 → 使用基础转录结果
3. 字幕生成失败 → 前续任务结果保留

**验证点：**
- [ ] 错误正确隔离
- [ ] 错误信息准确记录
- [ ] 后续任务正确处理

### TC011: 异常输入处理测试

**测试目标：** 验证系统对异常输入的处理能力

**测试场景：**
1. 无效音频文件
2. 空音频文件
3. 损坏的音频文件
4. 不支持的格式

**验证点：**
- [ ] 异常正确识别
- [ ] 错误信息清晰
- [ ] 系统保持稳定

### TC012: 资源不足场景测试

**测试目标：** 验证资源不足时的系统行为

**测试场景：**
1. GPU显存不足
2. 磁盘空间不足
3. 网络连接异常

**验证点：**
- [ ] 优雅降级处理
- [ ] 资源清理正确
- [ ] 错误恢复机制

## 📊 测试报告模板

### 测试执行记录

| 测试用例 | 执行时间 | 执行状态 | 结果 | 问题描述 | 优先级 |
|---------|---------|---------|------|----------|--------|
| TC001 | 2024-XX-XX | ✅ PASS | 成功 | - | - |
| TC002 | 2024-XX-XX | ❌ FAIL | 失败 | 说话人分离精度不足 | 高 |

### 性能测试结果

| 指标 | 原有版本 | 拆分版本 | 差异 | 状态 |
|------|----------|----------|------|------|
| 执行时间 | 120s | 125s | +4.2% | ✅ 可接受 |
| 内存使用 | 2.1GB | 2.3GB | +9.5% | ✅ 可接受 |
| GPU利用率 | 85% | 82% | -3.5% | ✅ 可接受 |

### 发现问题汇总

**高优先级问题：**
1. 说话人分离精度需要优化
2. GPU锁超时时间需要调整

**中优先级问题：**
1. 日志输出格式需要标准化
2. 错误信息需要更详细

**低优先级问题：**
1. 文档需要更新
2. 配置示例需要补充

## 🔄 测试自动化

### 自动化测试脚本

```bash
#!/bin/bash
# whisperx_split_test.sh

# 测试环境准备
setup_test_env() {
    echo "准备测试环境..."
    docker-compose up -d
    sleep 30
}

# 运行功能测试
run_functional_tests() {
    echo "运行功能测试..."

    # TC001: 基础转录测试
    python scripts/test_transcribe_audio.py

    # TC002: 说话人分离测试
    python scripts/test_diarize_speakers.py

    # TC003: 字幕生成测试
    python scripts/test_generate_subtitle_files.py
}

# 运行性能测试
run_performance_tests() {
    echo "运行性能测试..."
    python scripts/performance_benchmark.py
}

# 生成测试报告
generate_report() {
    echo "生成测试报告..."
    python scripts/generate_test_report.py
}

# 主测试流程
main() {
    setup_test_env
    run_functional_tests
    run_performance_tests
    generate_report
    echo "测试完成！"
}

main "$@"
```

### 持续集成配置

```yaml
# .github/workflows/whisperx_test.yml
name: WhisperX 功能拆分测试

on:
  push:
    paths:
      - 'services/workers/whisperx_service/**'
  pull_request:
    paths:
      - 'services/workers/whisperx_service/**'

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v2

    - name: 启动测试环境
      run: docker-compose -f docker-compose.test.yml up -d

    - name: 运行功能测试
      run: ./scripts/whisperx_split_test.sh

    - name: 上传测试报告
      uses: actions/upload-artifact@v2
      with:
        name: test-report
        path: reports/
```

## 📈 成功标准

### 功能标准
- [ ] 所有独立任务节点功能正常
- [ ] 数据传递正确无误
- [ ] 输出格式符合规范

### 性能标准
- [ ] 总执行时间增加 < 10%
- [ ] GPU利用率保持 > 75%
- [ ] 内存使用增加 < 15%

### 稳定性标准
- [ ] 连续运行24小时无崩溃
- [ ] 并发处理能力不降低
- [ ] 错误恢复机制有效

### 兼容性标准
- [ ] 原有API 100% 兼容
- [ ] 配置参数完全兼容
- [ ] 输出格式保持一致

## 📝 测试检查清单

### 代码审查检查清单
- [ ] 新增任务节点代码符合项目规范
- [ ] 错误处理机制完善
- [ ] 日志输出清晰完整
- [ ] 配置参数验证充分

### 部署检查清单
- [ ] Docker镜像构建成功
- [ ] 服务启动正常
- [ ] 健康检查通过
- [ ] 监控指标正常

### 验收检查清单
- [ ] 所有测试用例通过
- [ ] 性能指标达标
- [ ] 文档更新完整
- [ ] 用户培训材料准备就绪

## 🚨 风险评估

### 高风险项
1. **GPU锁兼容性** - 新的GPU锁机制可能影响现有功能
2. **数据传递可靠性** - 任务间数据传递可能出现丢失

### 中风险项
1. **性能回退** - 拆分可能导致性能下降
2. **配置复杂性** - 新工作流配置可能增加学习成本

### 缓解措施
1. 完善的向后兼容性保证
2. 详细的测试验证
3. 清晰的迁移文档
4. 充分的用户培训

## 📚 参考资料

- [WhisperX功能拆分实施文档](WHISPERX_SPLIT_IMPLEMENTATION.md)
- [GPU锁系统完整指南](../reference/GPU_LOCK_COMPLETE_GUIDE.md)
- [工作流配置指南](../reference/WHISPERX_WORKFLOW_GUIDE.md)
- [API参考文档](../api/API_REFERENCE.md)

---

**文档版本**: v1.0
**创建日期**: 2024-XX-XX
**最后更新**: 2024-XX-XX
**负责人**: 开发团队
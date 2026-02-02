# 字幕重构功能测试指南（语义保护版本）

## 概述

本指南用于测试新实现的字幕语义保护断句功能。

## 前置条件

- Docker 服务正在运行
- API Gateway 和 WService 容器已启动
- 输入文件存在：
  - `share/workflows/video_to_subtitle_task/nodes/faster_whisper.transcribe_audio/data/transcribe_data_task_id.json`
  - `share/workflows/video_to_subtitle_task/nodes/wservice.ai_optimize_text/data/transcribe_data_task_id_optimized_text.txt`

## 快速执行

### 方法 1: 使用 Shell 脚本（推荐）

```bash
cd /opt/wionch/docker/yivideo

# 添加执行权限
chmod +x test_rebuild_simple.sh

# 运行测试
./test_rebuild_simple.sh
```

### 方法 2: 使用 Python 脚本

```bash
cd /opt/wionch/docker/yivideo
python test_rebuild_with_semantic_protection.py
```

### 方法 3: 使用 curl 直接调用

```bash
cd /opt/wionch/docker/yivideo

curl -X POST http://localhost:8788/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "task_name": "wservice.rebuild_subtitle_with_words",
    "task_id": "test_rebuild_'$(date +%s)'",
    "input_data": {
      "segments_file": "share/workflows/video_to_subtitle_task/nodes/faster_whisper.transcribe_audio/data/transcribe_data_task_id.json",
      "optimized_text_file": "share/workflows/video_to_subtitle_task/nodes/wservice.ai_optimize_text/data/transcribe_data_task_id_optimized_text.txt",
      "report": true
    }
  }' | jq '.'
```

## 检查结果

### 步骤 1: 查找输出文件

```bash
# 查找最新生成的文件
find share/workflows -name "*optimized_words.json" -type f -mmin -10

# 或检查标准位置
OUTPUT_DIR="share/workflows/video_to_subtitle_task/nodes/wservice.rebuild_subtitle_with_words/data"
ls -lh $OUTPUT_DIR/*optimized_words.json
```

### 步骤 2: 分析结果质量

```bash
# 使用分析脚本
python analyze_rebuild_result.py share/workflows/video_to_subtitle_task/nodes/wservice.rebuild_subtitle_with_words/data/transcribe_data_task_id_optimized_words.json
```

### 步骤 3: 手动检查片段

```bash
OUTPUT_FILE="share/workflows/video_to_subtitle_task/nodes/wservice.rebuild_subtitle_with_words/data/transcribe_data_task_id_optimized_words.json"

# 查看片段数量
jq 'length' $OUTPUT_FILE

# 查看前5个片段
jq '.[:5] | .[] | {id, start, end, text_length: (.text | length), text}' $OUTPUT_FILE

# 查找问题片段
echo "超长片段 (>42字符):"
jq '.[] | select((.text | length) > 42) | {id, length: (.text | length), text}' $OUTPUT_FILE

echo "极短片段 (<3字符):"
jq '.[] | select((.text | length) < 3) | {id, length: (.text | length), text}' $OUTPUT_FILE

echo "不完整片段 (小写开头+无标点):"
jq '.[] | select(
  (.text | length) > 0 and
  (.text | .[0:1] | ascii_downcase == .[0:1]) and
  (.text | .[-1:] | test("[.!?。！？…]") | not)
) | {id, text}' $OUTPUT_FILE | head -20
```

## 预期结果

### 质量指标

✅ **优秀** (语义保护正常工作):
- 极短片段 (<3字符): < 5%
- 超过CPL限制 (>42字符): 0%
- 不完整片段 (小写开头+无标点): < 10%

⚠️ **可接受** (基本工作):
- 极短片段: 5-10%
- 不完整片段: 10-20%

✗ **需要调试**:
- 极短片段: > 10%
- 超过CPL限制: > 0%
- 不完整片段: > 20%

### 语义保护特征

生成的字幕应该表现出以下特征：

1. **优先语义边界**: 在逗号、句号、连词等处分割
2. **避免超短片段**: 长度 >= 3 字符
3. **遵守CPL限制**: 所有片段 <= 42 字符
4. **完整性**: 大写开头或有结尾标点

## 对比分析

对比语义保护前后的效果：

```bash
# 原始问题片段（来自任务日志）
# ID 1: "Well Well, little kitty, if you are really"
# - 重复的 "Well"
# - 缺少 "are"

# 语义保护后应该：
# - 修复文本问题
# - 在合适的语义边界分割
# - 保持句子完整性
```

## 故障排查

### 服务未运行

```bash
# 检查服务状态
docker ps | grep -E "api_gateway|wservice"

# 启动服务
docker-compose up -d api_gateway wservice

# 查看日志
docker-compose logs -f wservice
```

### 任务执行失败

```bash
# 检查容器日志
docker-compose logs wservice | tail -50

# 检查 Redis 状态
docker-compose ps redis

# 手动清理缓存（如果需要）
docker exec -it redis redis-cli FLUSHDB
```

### 输出文件未生成

```bash
# 检查任务状态
curl http://localhost:8788/v1/tasks/status/test_rebuild_XXX | jq '.'

# 检查工作流状态
docker exec -it redis redis-cli GET "workflow:test_rebuild_XXX:state"
```

## 报告问题

如果发现问题，请提供：

1. 执行命令和完整输出
2. 生成的输出文件（前20个片段）
3. 问题片段的具体示例
4. WService 容器日志

---

**创建时间**: 2026-01-29
**功能版本**: 语义保护 v1.0
**测试环境**: Docker Compose

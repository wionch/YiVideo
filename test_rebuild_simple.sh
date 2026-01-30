#!/bin/bash
# 简单的字幕重构测试脚本

echo "=========================================="
echo "测试字幕重构功能（带语义保护）"
echo "=========================================="

# 检查输入文件
echo -e "\n1. 检查输入文件..."
SEGMENTS_FILE="share/workflows/video_to_subtitle_task/nodes/faster_whisper.transcribe_audio/data/transcribe_data_task_id.json"
OPTIMIZED_TEXT="share/workflows/video_to_subtitle_task/nodes/wservice.ai_optimize_text/data/transcribe_data_task_id_optimized_text.txt"

if [ -f "$SEGMENTS_FILE" ]; then
    echo "✓ segments_file 存在: $SEGMENTS_FILE"
    echo "  大小: $(du -h "$SEGMENTS_FILE" | cut -f1)"
else
    echo "✗ segments_file 不存在: $SEGMENTS_FILE"
    exit 1
fi

if [ -f "$OPTIMIZED_TEXT" ]; then
    echo "✓ optimized_text_file 存在: $OPTIMIZED_TEXT"
    echo "  大小: $(du -h "$OPTIMIZED_TEXT" | cut -f1)"
else
    echo "✗ optimized_text_file 不存在: $OPTIMIZED_TEXT"
    exit 1
fi

# 提交任务
echo -e "\n2. 提交字幕重构任务..."
TASK_ID="test_rebuild_$(date +%s)"

curl -X POST http://localhost:8788/v1/tasks \
  -H "Content-Type: application/json" \
  -d "{
    \"task_name\": \"wservice.rebuild_subtitle_with_words\",
    \"task_id\": \"$TASK_ID\",
    \"input_data\": {
      \"segments_file\": \"$SEGMENTS_FILE\",
      \"optimized_text_file\": \"$OPTIMIZED_TEXT\",
      \"report\": true
    }
  }" > /tmp/rebuild_response.json

echo -e "\n任务响应:"
cat /tmp/rebuild_response.json | jq '.'

# 检查输出文件
echo -e "\n3. 检查输出文件..."
OUTPUT_FILE=$(cat /tmp/rebuild_response.json | jq -r '.output.optimized_segments_file // empty')

if [ -n "$OUTPUT_FILE" ] && [ -f "$OUTPUT_FILE" ]; then
    echo "✓ 输出文件已生成: $OUTPUT_FILE"
    echo "  大小: $(du -h "$OUTPUT_FILE" | cut -f1)"

    # 分析片段
    echo -e "\n4. 分析字幕片段质量..."
    python3 << 'PYTHON_EOF'
import json
import sys

try:
    with open(sys.argv[1], 'r') as f:
        segments = json.load(f)

    print(f"总片段数: {len(segments)}")

    # 质量统计
    incomplete = 0
    too_short = 0
    exceeds_cpl = 0

    for seg in segments:
        text = seg.get('text', '').strip()
        if len(text) < 3:
            too_short += 1
        if len(text) > 42:
            exceeds_cpl += 1
        if text and not text[-1] in '.!?。！？…':
            if text and text[0].islower():
                incomplete += 1

    print(f"\n质量统计:")
    print(f"  极短片段 (<3字符): {too_short} ({too_short/len(segments)*100:.1f}%)")
    print(f"  不完整片段 (小写开头+无标点): {incomplete} ({incomplete/len(segments)*100:.1f}%)")
    print(f"  超过CPL限制 (>42字符): {exceeds_cpl} ({exceeds_cpl/len(segments)*100:.1f}%)")

    print(f"\n前5个片段:")
    for i, seg in enumerate(segments[:5], 1):
        text = seg.get('text', '')
        print(f"{i}. [{seg['start']:.1f}-{seg['end']:.1f}] ({len(text)}字符)")
        print(f"   \"{text}\"")

except Exception as e:
    print(f"分析失败: {e}")
    sys.exit(1)
PYTHON_EOF
"$OUTPUT_FILE"

    # 检查报告
    REPORT_FILE=$(cat /tmp/rebuild_response.json | jq -r '.output.report_file // empty')
    if [ -n "$REPORT_FILE" ] && [ -f "$REPORT_FILE" ]; then
        echo -e "\n5. 重构报告:"
        head -50 "$REPORT_FILE"
    fi

    echo -e "\n✓ 测试完成！"
else
    echo "✗ 输出文件未生成"
    echo "任务响应:"
    cat /tmp/rebuild_response.json
    exit 1
fi

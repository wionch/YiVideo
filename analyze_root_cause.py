#!/usr/bin/env python3
"""
根因分析：检查断句参数和逻辑
"""
import json
from pathlib import Path

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def analyze_segmentation_params():
    """分析当前断句参数"""
    print("=" * 80)
    print("断句参数分析")
    print("=" * 80)

    # rebuild_subtitle_with_words_executor.py 中的默认参数
    params = {
        'max_cpl': 42,      # 每行最大字符数
        'max_cps': 18.0,    # 每秒最大字符数
        'min_duration': 1.0,  # 最小持续时间（秒）
        'max_duration': 7.0,  # 最大持续时间（秒）
    }

    print("\n【当前断句参数】(来自 rebuild_subtitle_with_words_executor.py)")
    for k, v in params.items():
        print(f"  {k}: {v}")

    print("\n【参数说明】")
    print("  - max_cpl (42): 每行字幕最大字符数")
    print("    这是断句的主要驱动因素！当文本超过42字符时会强制断句")
    print("  - max_cps (18): 每秒最大字符数（阅读速度限制）")
    print("  - min_duration (1s): 最小持续时间，短于1秒的字幕会尝试合并")
    print("  - max_duration (7s): 最大持续时间，长于7秒的字幕会强制分割")

def analyze_original_vs_rebuilt():
    """对比原始片段和重构后的片段"""
    print("\n" + "=" * 80)
    print("原始 vs 重构后对比")
    print("=" * 80)

    # 加载原始片段（merge_with_word_timestamps 输出）
    original_path = Path("/opt/wionch/docker/yivideo/share/workflows/video_to_subtitle_task/nodes/wservice.merge_with_word_timestamps/data/transcribe_data_video_to_word_timestamps_merged.json")
    rebuilt_path = Path("/opt/wionch/docker/yivideo/share/workflows/video_to_subtitle_task/nodes/wservice.rebuild_subtitle_with_words/data/transcribe_data_task_id_optimized_words.json")

    original_segments = load_json(original_path)
    rebuilt_segments = load_json(rebuilt_path)

    print(f"\n原始片段数: {len(original_segments)}")
    print(f"重构后片段数: {len(rebuilt_segments)}")

    # 计算平均长度
    def avg_length(segments):
        lengths = [len(s.get('text', '')) for s in segments]
        return sum(lengths) / len(lengths) if lengths else 0

    def avg_duration(segments):
        durs = [s.get('duration', 0) for s in segments]
        return sum(durs) / len(durs) if durs else 0

    print(f"\n原始平均文本长度: {avg_length(original_segments):.1f} 字符")
    print(f"重构后平均文本长度: {avg_length(rebuilt_segments):.1f} 字符")

    print(f"\n原始平均持续时间: {avg_duration(original_segments):.2f} 秒")
    print(f"重构后平均持续时间: {avg_duration(rebuilt_segments):.2f} 秒")

    # 对比前几个片段
    print("\n【前5个片段对比】")
    print("-" * 80)
    for i in range(min(5, len(original_segments), len(rebuilt_segments))):
        orig = original_segments[i]
        rebuilt = rebuilt_segments[i]
        print(f"\n原始片段 {i+1} ({orig.get('duration', 0):.2f}s, {len(orig.get('text', ''))}字符):")
        print(f"  \"{orig.get('text', '')}\"")
        print(f"重构后片段 {i+1} ({rebuilt.get('duration', 0):.2f}s, {len(rebuilt.get('text', ''))}字符):")
        print(f"  \"{rebuilt.get('text', '')}\"")

def analyze_semantic_breaks():
    """分析语义断句问题"""
    print("\n" + "=" * 80)
    print("语义断句问题分析")
    print("=" * 80)

    rebuilt_path = Path("/opt/wionch/docker/yivideo/share/workflows/video_to_subtitle_task/nodes/wservice.rebuild_subtitle_with_words/data/transcribe_data_task_id_optimized_words.json")
    segments = load_json(rebuilt_path)

    # 分析问题类型
    problems = {
        'sentence_split': [],  # 句子被切断
        'phrase_split': [],    # 短语被切断
        'abbreviation_broken': [],  # 缩写被破坏
    }

    for i, seg in enumerate(segments):
        text = seg.get('text', '').strip()

        # 1. 检查句子在不应该断的地方断了
        # 比如 "U." 后面跟着 "S." - 这是 U.S. 被分割了
        if text == "U.":
            problems['abbreviation_broken'].append({
                'id': seg.get('id', i+1),
                'text': text,
                'issue': 'U.S. 缩写被分割'
            })
        if text == "S.":
            problems['abbreviation_broken'].append({
                'id': seg.get('id', i+1),
                'text': text,
                'issue': 'U.S. 缩写被分割'
            })

        # 2. 检查小写开头的片段（可能是不完整句子）
        if text and text[0].islower():
            problems['sentence_split'].append({
                'id': seg.get('id', i+1),
                'text': text,
                'issue': '小写开头 - 可能是句子中间'
            })

        # 3. 检查无标点的片段
        if text and text[-1] not in '.!?。！？…,，':
            problems['phrase_split'].append({
                'id': seg.get('id', i+1),
                'text': text,
                'issue': '无结尾标点 - 短语被切断'
            })

    print(f"\n【缩写被分割】({len(problems['abbreviation_broken'])} 处)")
    for p in problems['abbreviation_broken'][:5]:
        print(f"  ID {p['id']}: \"{p['text']}\" - {p['issue']}")

    print(f"\n【句子被切断】小写开头 ({len(problems['sentence_split'])} 处)")
    print("  部分示例:")
    for p in problems['sentence_split'][:10]:
        print(f"    ID {p['id']}: \"{p['text']}\"")

    print(f"\n【短语被切断】无结尾标点 ({len(problems['phrase_split'])} 处)")
    print("  部分示例:")
    for p in problems['phrase_split'][:10]:
        print(f"    ID {p['id']}: \"{p['text']}\"")

def analyze_text_continuity():
    """分析文本连续性"""
    print("\n" + "=" * 80)
    print("文本连续性分析")
    print("=" * 80)

    rebuilt_path = Path("/opt/wionch/docker/yivideo/share/workflows/video_to_subtitle_task/nodes/wservice.rebuild_subtitle_with_words/data/transcribe_data_task_id_optimized_words.json")
    segments = load_json(rebuilt_path)

    # 检查连续片段之间是否有时间间隙
    gaps = []
    for i in range(len(segments) - 1):
        curr_end = segments[i].get('end', 0)
        next_start = segments[i + 1].get('start', 0)
        gap = next_start - curr_end

        if gap > 0.1:  # 大于100ms的间隙
            gaps.append({
                'after_id': segments[i].get('id', i+1),
                'gap': gap,
                'curr_end': curr_end,
                'next_start': next_start,
            })

    print(f"\n【片段间时间间隙】(>100ms)")
    print(f"  共有 {len(gaps)} 处间隙")

    for g in gaps[:10]:
        print(f"    ID {g['after_id']} 后: {g['gap']:.3f}s (结束于 {g['curr_end']:.2f}s, 下一片段开始于 {g['next_start']:.2f}s)")

    if len(gaps) > 10:
        print(f"    ... 还有 {len(gaps) - 10} 处")

def main():
    analyze_segmentation_params()
    analyze_original_vs_rebuilt()
    analyze_semantic_breaks()
    analyze_text_continuity()

    # 总结
    print("\n" + "=" * 80)
    print("根因总结")
    print("=" * 80)
    print("""
【核心问题】

1. max_cpl=42 过于严格
   - 英文单词平均5-6个字符，加上空格后约7字符
   - 42字符约可容纳 6-7个单词
   - 但自然句子通常更长，强制截断导致句子不完整

2. 断句策略优先级问题
   - 第一层强标点断句被跳过（因为 PySBD 全局断句优先）
   - 但 PySBD 只在文本超过 max_cpl 后才进一步分割
   - 结果是基于字符数的硬截断，而非语义断句

3. 缺少句子完整性检查
   - 没有检测片段是否构成完整句子
   - 没有合并小写开头的片段
   - 没有处理缩写（如 U.S.）被分割的问题

【建议修复方向】

A. 调整 max_cpl 参数（短期方案）
   - 增加到 80-100 字符，让句子更完整
   - 或者根据实际内容动态调整

B. 改进断句策略（中期方案）
   - 优先保持句子完整性
   - 只在句子边界处断句
   - 合并过短的小写开头片段

C. 添加后处理（长期方案）
   - 检测并合并不完整的片段
   - 修复缩写分割问题
   - 确保每段都是完整语义单元
""")

if __name__ == "__main__":
    main()

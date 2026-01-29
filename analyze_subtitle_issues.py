#!/usr/bin/env python3
"""
字幕重构问题分析脚本
"""
import json
from pathlib import Path

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_text(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

def analyze_segments(segments):
    """分析片段问题"""
    issues = []

    for i, seg in enumerate(segments):
        text = seg.get('text', '').strip()
        duration = seg.get('duration', 0)
        word_count = len(seg.get('words', []))

        # 1. 检查片段是否以标点结尾
        ends_with_punct = text[-1] in '.!?。！？…' if text else False

        # 2. 检查片段开头是否小写（可能是不完整句子）
        starts_lowercase = text[0].islower() if text and text[0].isalpha() else False

        # 3. 检查过短片段
        is_too_short = len(text) <= 3

        # 4. 检查过长片段
        is_too_long = len(text) > 42

        # 5. 检查持续时间
        is_short_duration = duration < 1.0
        is_long_duration = duration > 7.0

        issue = {
            'id': seg.get('id', i+1),
            'text': text,
            'duration': duration,
            'word_count': word_count,
            'starts_lowercase': starts_lowercase,
            'ends_with_punct': ends_with_punct,
            'is_too_short': is_too_short,
            'is_too_long': is_too_long,
            'is_short_duration': is_short_duration,
            'is_long_duration': is_long_duration,
        }
        issues.append(issue)

    return issues

def print_issues(issues):
    """打印问题"""
    print("=" * 80)
    print("字幕重构问题分析报告")
    print("=" * 80)

    # 统计
    total = len(issues)
    no_end_punct = sum(1 for i in issues if not i['ends_with_punct'])
    starts_lower = sum(1 for i in issues if i['starts_lowercase'])
    too_short = sum(1 for i in issues if i['is_too_short'])
    too_long = sum(1 for i in issues if i['is_too_long'])
    short_dur = sum(1 for i in issues if i['is_short_duration'])
    long_dur = sum(1 for i in issues if i['is_long_duration'])

    print(f"\n【统计摘要】")
    print(f"  总片段数: {total}")
    print(f"  无结尾标点: {no_end_punct} ({no_end_punct/total*100:.1f}%)")
    print(f"  小写开头: {starts_lower} ({starts_lower/total*100:.1f}%)")
    print(f"  过短文本(<=3字符): {too_short} ({too_short/total*100:.1f}%)")
    print(f"  过长文本(>42字符): {too_long} ({too_long/total*100:.1f}%)")
    print(f"  过短时长(<1s): {short_dur} ({short_dur/total*100:.1f}%)")
    print(f"  过长时长(>7s): {long_dur} ({long_dur/total*100:.1f}%)")

    # 详细问题
    print(f"\n【详细问题列表】")
    print("-" * 80)

    for i in issues:
        problems = []
        if not i['ends_with_punct']:
            problems.append("无结尾标点")
        if i['starts_lowercase']:
            problems.append("小写开头")
        if i['is_too_short']:
            problems.append("过短")
        if i['is_too_long']:
            problems.append("过长")
        if i['is_short_duration']:
            problems.append("时长短")
        if i['is_long_duration']:
            problems.append("时长长")

        if problems:
            print(f"\nID {i['id']}:")
            print(f"  文本: \"{i['text']}\"")
            print(f"  时长: {i['duration']:.2f}s | 词数: {i['word_count']}")
            print(f"  问题: {', '.join(problems)}")

    # 特殊模式：连续片段分析
    print(f"\n【连续片段连贯性分析】")
    print("-" * 80)

    consecutive_issues = []
    for i in range(len(issues) - 1):
        curr = issues[i]
        next_seg = issues[i + 1]

        # 当前片段无标点且下一片段小写开头 → 可能断句错误
        if not curr['ends_with_punct'] and next_seg['starts_lowercase']:
            consecutive_issues.append({
                'type': '可能断句错误（当前无标点+下一段小写）',
                'curr_id': curr['id'],
                'curr_text': curr['text'],
                'next_id': next_seg['id'],
                'next_text': next_seg['text']
            })

        # 极短片段后面跟着小写开头
        if curr['is_too_short'] and next_seg['starts_lowercase']:
            consecutive_issues.append({
                'type': '极短片段后接小写（可能属于同一句）',
                'curr_id': curr['id'],
                'curr_text': curr['text'],
                'next_id': next_seg['id'],
                'next_text': next_seg['text']
            })

    for issue in consecutive_issues[:15]:  # 只显示前15个
        print(f"\n{issue['type']}:")
        print(f"  ID {issue['curr_id']}: \"{issue['curr_text']}\"")
        print(f"  ID {issue['next_id']}: \"{issue['next_text']}\"")

    if len(consecutive_issues) > 15:
        print(f"\n... 还有 {len(consecutive_issues) - 15} 个类似问题")

def main():
    # 文件路径
    rebuilt_path = Path("/opt/wionch/docker/yivideo/share/workflows/video_to_subtitle_task/nodes/wservice.rebuild_subtitle_with_words/data/transcribe_data_task_id_optimized_words.json")

    # 加载数据
    segments = load_json(rebuilt_path)

    # 分析
    issues = analyze_segments(segments)

    # 打印报告
    print_issues(issues)

if __name__ == "__main__":
    main()

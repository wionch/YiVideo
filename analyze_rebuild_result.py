#!/usr/bin/env python3
"""
分析字幕重构结果文件

直接分析已存在的 optimized_words.json 文件
"""
import json
import os
import sys
from pathlib import Path

def analyze_subtitle_file(filepath):
    """分析字幕文件质量"""
    print("=" * 80)
    print(f"分析文件: {filepath}")
    print("=" * 80)

    if not os.path.exists(filepath):
        print(f"✗ 文件不存在: {filepath}")
        return False

    file_size = os.path.getsize(filepath)
    print(f"文件大小: {file_size:,} bytes ({file_size/1024:.1f} KB)")

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            segments = json.load(f)
    except Exception as e:
        print(f"✗ 读取文件失败: {e}")
        return False

    print(f"总片段数: {len(segments)}")

    # 质量统计
    stats = {
        'total': len(segments),
        'too_short': 0,
        'incomplete': 0,
        'exceeds_cpl': 0,
        'perfect': 0,
        'no_punctuation': 0,
        'lowercase_start': 0
    }

    for seg in segments:
        text = seg.get('text', '').strip()
        text_len = len(text)

        # 统计各类问题
        if text_len < 3:
            stats['too_short'] += 1

        if text_len > 42:
            stats['exceeds_cpl'] += 1

        has_ending_punct = text and text[-1] in '.!?。！？…'
        is_lowercase_start = text and text[0].islower()

        if not has_ending_punct:
            stats['no_punctuation'] += 1
            if is_lowercase_start:
                stats['incomplete'] += 1

        if is_lowercase_start:
            stats['lowercase_start'] += 1

        # 完美片段：有标点、大写开头、长度适中
        if has_ending_punct and not is_lowercase_start and 3 <= text_len <= 42:
            stats['perfect'] += 1

    # 打印统计
    print("\n" + "=" * 80)
    print("质量统计报告")
    print("=" * 80)

    def print_stat(label, count, total):
        percentage = count / total * 100 if total > 0 else 0
        indicator = "✓" if percentage < 5 else "⚠" if percentage < 20 else "✗"
        print(f"{indicator} {label:40s}: {count:4d} ({percentage:5.1f}%)")

    print_stat("极短片段 (<3字符)", stats['too_short'], stats['total'])
    print_stat("超过CPL限制 (>42字符)", stats['exceeds_cpl'], stats['total'])
    print_stat("无结尾标点", stats['no_punctuation'], stats['total'])
    print_stat("小写开头", stats['lowercase_start'], stats['total'])
    print_stat("不完整片段 (小写开头+无标点)", stats['incomplete'], stats['total'])
    print_stat("完美片段 (有标点+大写开头+长度合适)", stats['perfect'], stats['total'])

    # 显示示例片段
    print("\n" + "=" * 80)
    print("前10个片段示例")
    print("=" * 80)

    for i, seg in enumerate(segments[:10], 1):
        text = seg.get('text', '')
        words_count = len(seg.get('words', []))
        start = seg.get('start', 0)
        end = seg.get('end', 0)

        # 标记问题
        issues = []
        if len(text) < 3:
            issues.append("极短")
        if len(text) > 42:
            issues.append("超长")
        if text and not text[-1] in '.!?。！？…':
            issues.append("无标点")
        if text and text[0].islower():
            issues.append("小写开头")

        issue_str = f" [{', '.join(issues)}]" if issues else " [OK]"

        print(f"\n{i}. [{start:.1f}-{end:.1f}s] ({len(text)}字符, {words_count}词){issue_str}")
        print(f"   \"{text}\"")

    # 查找问题片段
    print("\n" + "=" * 80)
    print("问题片段示例（前5个）")
    print("=" * 80)

    problem_segments = []
    for i, seg in enumerate(segments, 1):
        text = seg.get('text', '').strip()
        if len(text) < 3 or len(text) > 42 or (text and not text[-1] in '.!?。！？…' and text[0].islower()):
            problem_segments.append((i, seg))

    if problem_segments:
        for idx, (seg_num, seg) in enumerate(problem_segments[:5], 1):
            text = seg.get('text', '')
            print(f"\n{idx}. 片段#{seg_num} [{seg['start']:.1f}-{seg['end']:.1f}s] ({len(text)}字符)")
            print(f"   \"{text}\"")
    else:
        print("✓ 未发现问题片段！")

    return True

def main():
    # 查找输出文件
    possible_paths = [
        "share/workflows/video_to_subtitle_task/nodes/wservice.rebuild_subtitle_with_words/data/transcribe_data_task_id_optimized_words.json",
        "share/workflows/video_to_subtitle_task/nodes/wservice.rebuild_subtitle_with_words/data/transcribe_data_*_optimized_words.json",
    ]

    filepath = None
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
    else:
        # 尝试查找文件
        for pattern in possible_paths:
            matches = list(Path('.').glob(pattern))
            if matches:
                filepath = str(matches[0])
                break

    if not filepath:
        print("用法: python analyze_rebuild_result.py [文件路径]")
        print("\n或将脚本放在项目根目录运行，自动查找输出文件")
        print("\n可能的文件位置:")
        for path in possible_paths:
            print(f"  - {path}")
        sys.exit(1)

    success = analyze_subtitle_file(filepath)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()

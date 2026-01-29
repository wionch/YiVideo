#!/usr/bin/env python3
"""
分析字幕重构后的问题

目标:
1. 逐条检查字幕，发现分段和内容问题
2. 分析问题的根本原因
"""

import json
import sys
from typing import List, Dict, Any

def load_json(filepath: str) -> List[Dict[str, Any]]:
    """加载JSON文件"""
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if isinstance(data, dict) and 'segments' in data:
        return data['segments']
    return data

def analyze_segment(seg: Dict[str, Any], index: int) -> List[str]:
    """分析单个字幕段落可能存在的问题"""
    issues = []
    
    text = seg.get('text', '')
    words = seg.get('words', [])
    duration = seg.get('duration', 0)
    start = seg.get('start', 0)
    end = seg.get('end', 0)
    
    # 问题1: 文本与words不匹配
    words_text = ''.join(w.get('word', '') for w in words)
    if text.strip() != words_text.strip():
        issues.append(f"文本不匹配: text='{text}' vs words='{words_text}'")
    
    # 问题2: 字幕过短（少于3个字符的实质内容）
    stripped_text = text.strip()
    if len(stripped_text) < 3 and stripped_text not in ['?', '!', '.', 'Oh', 'So', 'No']:
        issues.append(f"字幕过短: '{text}' ({len(stripped_text)} chars)")
    
    # 问题3: 字幕过长（超过60个字符）
    if len(stripped_text) > 60:
        issues.append(f"字幕过长: {len(stripped_text)} chars")
    
    # 问题4: 持续时间异常
    if duration < 0.3:
        issues.append(f"持续时间过短: {duration:.2f}s")
    elif duration > 10:
        issues.append(f"持续时间过长: {duration:.2f}s")
    
    # 问题5: 时间戳不连续
    if words:
        prev_end = None
        for i, word in enumerate(words):
            word_start = word.get('start', 0)
            word_end = word.get('end', 0)
            
            if word_end < word_start:
                issues.append(f"词时间戳错误: word[{i}] end < start")
            
            if prev_end is not None and word_start < prev_end:
                issues.append(f"词时间戳重叠: word[{i-1}]->word[{i}]")
            
            prev_end = word_end
    
    # 问题6: 句子被异常分割
    # 检查是否在句中断开（不以标点结尾但下一个以小写开头）
    if text and not text.rstrip().endswith(('.', '!', '?', ',', ':', ';', '。', '！', '？', '，', '、')):
        issues.append(f"句子未完整: 不以标点结尾")
    
    # 问题7: 标点单独成段
    if stripped_text in [',', '.', '!', '?', ';', ':', '，', '。', '！', '？', '、', '；', '：']:
        issues.append(f"标点单独成段")
    
    # 问题8: 检查是否有空词
    empty_words = [i for i, w in enumerate(words) if not w.get('word', '').strip()]
    if empty_words:
        issues.append(f"存在空词: indices {empty_words}")
    
    return issues

def analyze_segmentation_flow(segments: List[Dict[str, Any]]) -> List[str]:
    """分析字幕流的分段合理性"""
    flow_issues = []
    
    for i in range(len(segments) - 1):
        current = segments[i]
        next_seg = segments[i + 1]
        
        current_text = current.get('text', '').strip()
        next_text = next_seg.get('text', '').strip()
        
        current_end = current.get('end', 0)
        next_start = next_seg.get('start', 0)
        
        # 问题1: 两段之间时间重叠
        if next_start < current_end:
            flow_issues.append(
                f"段落 {current.get('id')} -> {next_seg.get('id')}: "
                f"时间重叠 ({current_end:.2f} > {next_start:.2f})"
            )
        
        # 问题2: 两段之间间隔过大（超过2秒）
        gap = next_start - current_end
        if gap > 2.0:
            flow_issues.append(
                f"段落 {current.get('id')} -> {next_seg.get('id')}: "
                f"间隔过大 ({gap:.2f}s)"
            )
        
        # 问题3: 当前段不以标点结尾，下一段以小写开头（可能是句子被分割）
        if current_text and next_text:
            if not current_text[-1] in '.!?,;:。！？，、；：' and next_text[0].islower():
                flow_issues.append(
                    f"段落 {current.get('id')} -> {next_seg.get('id')}: "
                    f"句子可能被分割: '{current_text[-20:]}' -> '{next_text[:20]}'"
                )
    
    return flow_issues

def check_specific_patterns(segments: List[Dict[str, Any]]) -> List[str]:
    """检查特定的问题模式"""
    pattern_issues = []
    
    # 模式1: "snap--trap" 类型的连字符问题
    for seg in segments:
        text = seg.get('text', '')
        if '--' in text or '- -' in text:
            pattern_issues.append(
                f"段落 {seg.get('id')}: 连字符格式问题: '{text}'"
            )
    
    # 模式2: 单词被不当分离（如 "S. It's" 应该连在一起）
    for i in range(len(segments) - 1):
        current = segments[i]
        next_seg = segments[i + 1]
        
        current_text = current.get('text', '').strip()
        next_text = next_seg.get('text', '').strip()
        
        # 检查类似 "U." 和 "S. It's" 的情况
        if current_text and len(current_text) <= 3 and current_text.endswith('.'):
            # 可能是缩写被分离
            if next_text and next_text[0].isupper():
                pattern_issues.append(
                    f"段落 {current.get('id')} -> {next_seg.get('id')}: "
                    f"缩写可能被分离: '{current_text}' + '{next_text}'"
                )
    
    # 模式3: " just a hundred" 这种分词问题
    for seg in segments:
        words = seg.get('words', [])
        for i, word in enumerate(words):
            word_text = word.get('word', '')
            # 检查是否有多个词被合并（如 "just a" 应该是两个词）
            if ' ' not in word_text.strip() and word_text.strip().startswith('just a'):
                pattern_issues.append(
                    f"段落 {seg.get('id')}: 词合并问题: '{word_text}'"
                )
    
    return pattern_issues

def main():
    filepath = "/opt/wionch/docker/yivideo/share/workflows/video_to_subtitle_task/nodes/wservice.rebuild_subtitle_with_words/data/transcribe_data_task_id_optimized_words.json"
    
    print("="*80)
    print("字幕重构问题分析报告")
    print("="*80)
    print()
    
    # 加载数据
    segments = load_json(filepath)
    print(f"共加载 {len(segments)} 个字幕段落\n")
    
    # 1. 逐段分析
    print("【1】逐段问题检查")
    print("-"*80)
    
    segment_issues = {}
    total_issues = 0
    
    for i, seg in enumerate(segments):
        issues = analyze_segment(seg, i)
        if issues:
            segment_issues[seg.get('id', i+1)] = issues
            total_issues += len(issues)
    
    if segment_issues:
        for seg_id, issues in sorted(segment_issues.items())[:20]:  # 只显示前20个
            print(f"\n段落 {seg_id}:")
            seg = next((s for s in segments if s.get('id') == seg_id), None)
            if seg:
                print(f"  文本: '{seg.get('text', '')}'")
                print(f"  时间: {seg.get('start', 0):.2f}s - {seg.get('end', 0):.2f}s (持续 {seg.get('duration', 0):.2f}s)")
            for issue in issues:
                print(f"  ⚠ {issue}")
        
        if len(segment_issues) > 20:
            print(f"\n... 还有 {len(segment_issues) - 20} 个段落存在问题 ...")
    else:
        print("✓ 未发现段落级别问题")
    
    print(f"\n总计: {total_issues} 个段落级问题分布在 {len(segment_issues)} 个段落中")
    
    # 2. 分段流分析
    print("\n" + "="*80)
    print("【2】分段连贯性检查")
    print("-"*80)
    
    flow_issues = analyze_segmentation_flow(segments)
    if flow_issues:
        for issue in flow_issues[:15]:  # 只显示前15个
            print(f"  ⚠ {issue}")
        if len(flow_issues) > 15:
            print(f"\n... 还有 {len(flow_issues) - 15} 个流问题 ...")
    else:
        print("✓ 分段流畅，无连贯性问题")
    
    print(f"\n总计: {len(flow_issues)} 个分段流问题")
    
    # 3. 特定模式检查
    print("\n" + "="*80)
    print("【3】特定问题模式检查")
    print("-"*80)
    
    pattern_issues = check_specific_patterns(segments)
    if pattern_issues:
        for issue in pattern_issues[:15]:
            print(f"  ⚠ {issue}")
        if len(pattern_issues) > 15:
            print(f"\n... 还有 {len(pattern_issues) - 15} 个模式问题 ...")
    else:
        print("✓ 未发现特定问题模式")
    
    print(f"\n总计: {len(pattern_issues)} 个特定模式问题")
    
    # 4. 统计摘要
    print("\n" + "="*80)
    print("【4】问题统计摘要")
    print("="*80)
    
    # 统计字幕长度分布
    lengths = [len(seg.get('text', '').strip()) for seg in segments]
    durations = [seg.get('duration', 0) for seg in segments]
    
    print(f"\n字幕长度统计:")
    print(f"  平均长度: {sum(lengths)/len(lengths):.1f} 字符")
    print(f"  最短: {min(lengths)} 字符")
    print(f"  最长: {max(lengths)} 字符")
    print(f"  短字幕(<10字符): {sum(1 for l in lengths if l < 10)} 个 ({sum(1 for l in lengths if l < 10)/len(lengths)*100:.1f}%)")
    print(f"  长字幕(>50字符): {sum(1 for l in lengths if l > 50)} 个 ({sum(1 for l in lengths if l > 50)/len(lengths)*100:.1f}%)")
    
    print(f"\n字幕持续时间统计:")
    print(f"  平均时长: {sum(durations)/len(durations):.2f}s")
    print(f"  最短: {min(durations):.2f}s")
    print(f"  最长: {max(durations):.2f}s")
    print(f"  短时长(<1s): {sum(1 for d in durations if d < 1)} 个 ({sum(1 for d in durations if d < 1)/len(durations)*100:.1f}%)")
    print(f"  长时长(>7s): {sum(1 for d in durations if d > 7)} 个 ({sum(1 for d in durations if d > 7)/len(durations)*100:.1f}%)")
    
    print("\n" + "="*80)
    print("分析完成")
    print("="*80)

if __name__ == '__main__':
    main()

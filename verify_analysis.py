#!/usr/bin/env python3
"""
验证分析：检查PySBD分句结果 vs 最终输出
"""
import json
import sys
sys.path.insert(0, '/opt/wionch/docker/yivideo')

from services.common.subtitle.segmenter import MultilingualSubtitleSegmenter

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def main():
    # 加载原始词数据
    original_path = "/opt/wionch/docker/yivideo/share/workflows/video_to_subtitle_task/nodes/wservice.merge_with_word_timestamps/data/transcribe_data_video_to_word_timestamps_merged.json"
    segments = load_json(original_path)

    # 扁平化词列表
    flat_words = []
    for seg in segments:
        for word in seg.get('words', []):
            flat_words.append(word)

    print("=" * 80)
    print("验证：PySBD 全局分句 vs 最终输出")
    print("=" * 80)

    # 创建 segmenter
    segmenter = MultilingualSubtitleSegmenter()

    # 步骤1: 查看 PySBD 全局分句结果
    print("\n【步骤1】PySBD 全局语义分句结果:")
    pysbd_segments = segmenter._apply_pysbd_global_split(flat_words, "en")
    print(f"  分出 {len(pysbd_segments)} 个语义片段")
    for i, seg in enumerate(pysbd_segments[:5]):
        text = "".join(w.get('word', '') for w in seg).strip()
        print(f"    片段{i+1}: {len(text)}字符 - \"{text[:60]}{'...' if len(text)>60 else ''}\"")

    # 步骤2: 查看最终输出
    print("\n【步骤2】最终输出（经过 _split_with_fallback）:")
    final_segments = segmenter.segment(flat_words, language="en", max_cpl=42, max_cps=18.0, min_duration=1.0, max_duration=7.0)
    print(f"  最终 {len(final_segments)} 个片段")
    for i, seg in enumerate(final_segments[:10]):
        text = "".join(w.get('word', '') for w in seg).strip()
        ends_with_punct = text[-1] in '.!?。！？…' if text else False
        starts_lower = text[0].islower() if text and text[0].isalpha() else False
        issues = []
        if not ends_with_punct: issues.append("无结尾标点")
        if starts_lower: issues.append("小写开头")
        print(f"    ID{i+1}: {len(text)}字符 - \"{text}\" {issues if issues else '✓'}")

    # 步骤3: 测试如果放宽 max_cpl 会怎样
    print("\n【步骤3】如果放宽 max_cpl 到 100:")
    relaxed_segments = segmenter.segment(flat_words, language="en", max_cpl=100, max_cps=18.0, min_duration=1.0, max_duration=7.0)
    print(f"  最终 {len(relaxed_segments)} 个片段")
    incomplete = sum(1 for seg in relaxed_segments
                     if not "".join(w.get('word', '') for w in seg).strip()[-1] in '.!?。！？…')
    print(f"  无结尾标点的片段: {incomplete}")

    # 步骤4: 找出被强制切分的片段
    print("\n【步骤4】被强制切分的片段示例:")
    for i, pysbd_seg in enumerate(pysbd_segments[:3]):
        text = "".join(w.get('word', '') for w in pysbd_seg).strip()
        if len(text) > 42:
            print(f"\n  原始语义片段 {i+1} ({len(text)}字符):")
            print(f"    \"{text}\"")
            print(f"    因超过 max_cpl=42 被切分为:")
            # 模拟 _split_with_fallback 的效果
            sub_segments = segmenter._split_with_fallback(
                pysbd_seg, max_cpl=42, max_cps=18.0, min_duration=1.0, max_duration=7.0
            )
            for j, sub in enumerate(sub_segments):
                sub_text = "".join(w.get('word', '') for w in sub).strip()
                print(f"      子片段{j+1}: \"{sub_text}\"")

if __name__ == "__main__":
    main()

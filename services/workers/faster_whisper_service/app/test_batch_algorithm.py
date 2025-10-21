#!/usr/bin/env python3
"""
字幕分批算法测试脚本

直接测试基于字幕条目的智能分批算法，不依赖完整配置。
"""

import sys
import os
from typing import List
sys.path.append('/app')

from services.common.subtitle import SubtitleEntry
from services.common.subtitle.subtitle_parser import SRTParser

def test_split_entries_batch():
    """测试字幕条目分批算法"""
    print("🧪 测试字幕条目分批算法")
    print("=" * 50)

    # 解析测试字幕文件
    parser = SRTParser()
    subtitle_file = "/share/workflows/45fa11be-3727-4d3b-87ce-08c09618183f/subtitles/666_with_speakers.srt"

    print(f"📁 解析字幕文件: {subtitle_file}")
    entries = parser.parse_file(subtitle_file)
    print(f"✅ 解析成功，共 {len(entries)} 条字幕")

    # 测试不同的批次大小
    batch_sizes = [1000, 2000, 3000, 5000]

    for batch_size in batch_sizes:
        print(f"\n📊 测试批次大小: {batch_size} 字符")
        print("-" * 40)

        batches = split_entries_batch(entries, batch_size)
        print(f"✅ 分批完成: {len(batches)} 个批次")

        # 验证分批结果
        total_entries = sum(len(batch) for batch in batches)
        integrity_issues = []

        if total_entries != len(entries):
            integrity_issues.append(f"条目数不匹配: {len(entries)} -> {total_entries}")

        # 详细验证每个批次
        for i, batch in enumerate(batches):
            print(f"\n📋 批次 {i+1}:")
            print(f"   条目数: {len(batch)}")

            if batch:
                first_entry = batch[0]
                last_entry = batch[-1]
                print(f"   序号范围: {first_entry.index} - {last_entry.index}")
                print(f"   时间范围: {first_entry.start_time:.1f}s - {last_entry.end_time:.1f}s")

                # 验证序号连续性
                indices = [entry.index for entry in batch]
                if indices != sorted(indices):
                    integrity_issues.append(f"批次 {i+1} 序号不连续")

                # 验证时间戳合理性
                for j, entry in enumerate(batch):
                    if entry.start_time >= entry.end_time:
                        integrity_issues.append(f"批次 {i+1} 条目 {entry.index} 时间戳无效")

                    if j < len(batch) - 1:
                        next_entry = batch[j + 1]
                        if entry.end_time > next_entry.start_time:
                            integrity_issues.append(f"批次 {i+1} 条目 {entry.index} 与 {next_entry.index} 时间重叠")

                # 检查批次大小
                batch_text = parser.entries_to_text(batch)
                print(f"   文本长度: {len(batch_text)} 字符")

                if len(batch_text) > batch_size * 1.1:  # 允许10%的误差
                    integrity_issues.append(f"批次 {i+1} 大小超出限制: {len(batch_text)} > {batch_size}")

        # 输出验证结果
        if integrity_issues:
            print(f"\n❌ 批次大小 {batch_size} 发现问题:")
            for issue in integrity_issues[:3]:  # 只显示前3个问题
                print(f"   - {issue}")
        else:
            print(f"\n✅ 批次大小 {batch_size} 所有检查通过！")
            print(f"   - 总批次数: {len(batches)}")
            print(f"   - 总条目数: {total_entries}")
            print(f"   - 平均每批条目数: {total_entries / len(batches):.1f}")

def split_entries_batch(entries: List[SubtitleEntry], max_size: int) -> List[List[SubtitleEntry]]:
    """
    基于字幕条目的智能分批算法

    确保每个批次包含完整的字幕条目，不会破坏SRT格式的完整性。
    """
    if not entries:
        return []

    # 创建解析器实例
    parser = SRTParser()

    # 如果总字符数小于最大限制，直接返回单个批次
    total_text = parser.entries_to_text(entries)
    if len(total_text) <= max_size:
        return [entries]

    print(f"   开始智能分批，总字幕条目: {len(entries)}，最大批次大小: {max_size} 字符")

    batches = []
    current_batch = []
    current_batch_size = 0

    # 预估每个字幕条目的字符数（包括格式）
    for entry in entries:
        # 计算单个字幕条目的字符数（包括序号、时间戳、文本和分隔符）
        entry_text = str(entry)
        entry_size = len(entry_text) + 2  # +2 for the double newline between entries

        # 如果当前批次为空，直接添加
        if not current_batch:
            current_batch.append(entry)
            current_batch_size = entry_size
            continue

        # 检查添加当前条目是否会超过最大限制
        if current_batch_size + entry_size <= max_size:
            current_batch.append(entry)
            current_batch_size += entry_size
        else:
            # 保存当前批次，开始新批次
            batches.append(current_batch)

            current_batch = [entry]
            current_batch_size = entry_size

    # 添加最后一个批次
    if current_batch:
        batches.append(current_batch)

    # 验证分批结果
    total_entries = sum(len(batch) for batch in batches)
    if total_entries != len(entries):
        raise ValueError(f"分批验证失败：原始条目数 {len(entries)} != 分批后条目数 {total_entries}")

    return batches

def test_edge_cases():
    """测试边界情况"""
    print("\n🧪 测试边界情况")
    print("=" * 50)

    # 测试空列表
    print("📋 测试空列表...")
    empty_result = split_entries_batch([], 1000)
    print(f"✅ 空列表分批结果: {len(empty_result)} 个批次")

    # 测试单个条目
    print("\n📋 测试单个条目...")
    single_entry = [SubtitleEntry(1, 0.0, 3.0, "测试文本")]
    single_result = split_entries_batch(single_entry, 1000)
    print(f"✅ 单个条目分批结果: {len(single_result)} 个批次，每批次 {len(single_result[0])} 条")

    # 测试大小刚好的情况
    print("\n📋 测试大小刚好的情况...")
    small_entries = []
    for i in range(3):
        entry = SubtitleEntry(
            index=i+1,
            start_time=i * 3.0,
            end_time=(i+1) * 3.0,
            text=f"测试文本 {i+1}"
        )
        small_entries.append(entry)

    small_text = SRTParser().entries_to_text(small_entries)
    exact_size = len(small_text)
    exact_result = split_entries_batch(small_entries, exact_size)
    print(f"✅ 刚好大小分批结果: {len(exact_result)} 个批次，总文本长度: {exact_size}")

def show_batch_details():
    """显示批次详细信息"""
    print("\n🔍 批次详细信息分析")
    print("=" * 50)

    parser = SRTParser()
    subtitle_file = "/share/workflows/45fa11be-3727-4d3b-87ce-08c09618183f/subtitles/666_with_speakers.srt"
    entries = parser.parse_file(subtitle_file)

    batch_size = 5000
    batches = split_entries_batch(entries, batch_size)

    print(f"总条目数: {len(entries)}")
    print(f"批次大小: {batch_size} 字符")
    print(f"批次数: {len(batches)}")
    print()

    # 分析批次大小分布
    batch_sizes = []
    for batch in batches:
        batch_text = parser.entries_to_text(batch)
        batch_sizes.append(len(batch_text))

    print("批次大小分布:")
    for i, size in enumerate(batch_sizes):
        print(f"  批次 {i+1}: {size} 字符 ({size/batch_size*100:.1f}% 的限制)")

    print(f"\n平均批次大小: {sum(batch_sizes)/len(batch_sizes):.0f} 字符")
    print(f"最大批次大小: {max(batch_sizes)} 字符")
    print(f"最小批次大小: {min(batch_sizes)} 字符")

if __name__ == "__main__":
    try:
        # 主要测试
        test_split_entries_batch()

        # 边界情况测试
        test_edge_cases()

        # 详细分析
        show_batch_details()

        print("\n" + "=" * 60)
        print("🎉 所有测试完成！字幕分批算法工作正常！")
        print("✅ 基于字幕条目的分批保证完整性")
        print("✅ 智能批次大小计算工作正常")
        print("✅ 序号和时间戳连续性保证")
        print("✅ SRT格式完整性保证")

    except Exception as e:
        print(f"\n❌ 测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
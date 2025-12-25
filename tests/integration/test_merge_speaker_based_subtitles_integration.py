# tests/integration/test_merge_speaker_based_subtitles_integration.py
# -*- coding: utf-8 -*-

"""
基于说话人时间区间的字幕合并集成测试
"""

import json
import tempfile
import os
from pathlib import Path

from services.common.context import WorkflowContext, StageExecution
from services.workers.wservice.executors import WServiceMergeSpeakerBasedSubtitlesExecutor


def test_merge_speaker_based_subtitles_integration():
    """集成测试：完整的执行器流程"""

    # 准备测试数据
    transcript_segments = [
        {
            'start': 10.0,
            'end': 15.0,
            'text': 'Hello world this is a test',
            'words': [
                {'word': ' Hello', 'start': 10.0, 'end': 10.5, 'probability': 0.9},
                {'word': ' world', 'start': 10.6, 'end': 11.2, 'probability': 0.95},
                {'word': ' this', 'start': 12.0, 'end': 12.3, 'probability': 0.88},
                {'word': ' is', 'start': 12.4, 'end': 12.6, 'probability': 0.92},
                {'word': ' a', 'start': 13.0, 'end': 13.1, 'probability': 0.85},
                {'word': ' test', 'start': 13.2, 'end': 13.8, 'probability': 0.91}
            ]
        }
    ]

    diarization_segments = [
        {'start': 9.5, 'end': 11.5, 'speaker': 'SPEAKER_00', 'speaker_confidence': 0.95},
        {'start': 11.8, 'end': 13.0, 'speaker': 'SPEAKER_01', 'speaker_confidence': 0.92},
        {'start': 13.0, 'end': 14.5, 'speaker': 'SPEAKER_00', 'speaker_confidence': 0.88}
    ]

    # 创建临时目录和文件
    with tempfile.TemporaryDirectory() as tmpdir:
        # 保存测试数据到文件
        segments_file = os.path.join(tmpdir, 'transcribe_data.json')
        with open(segments_file, 'w', encoding='utf-8') as f:
            json.dump(transcript_segments, f)

        diarization_data = {
            'speaker_enhanced_segments': diarization_segments,
            'detected_speakers': ['SPEAKER_00', 'SPEAKER_01']
        }
        diarization_file = os.path.join(tmpdir, 'diarization_result.json')
        with open(diarization_file, 'w', encoding='utf-8') as f:
            json.dump(diarization_data, f)

        # 创建工作流上下文
        workflow_context = WorkflowContext(
            workflow_id='test-integration-001',
            shared_storage_path=tmpdir,
            input_params={
                'task_name': 'wservice.merge_speaker_based_subtitles',
                'input_data': {
                    'segments_file': segments_file,
                    'diarization_file': diarization_file,
                    'overlap_threshold': 0.5
                }
            },
            stages={}
        )

        # 创建执行器
        executor = WServiceMergeSpeakerBasedSubtitlesExecutor(
            stage_name='wservice.merge_speaker_based_subtitles',
            context=workflow_context
        )

        # 执行
        result_context = executor.execute()

        # 验证结果
        assert result_context.workflow_id == 'test-integration-001'

        # 获取当前阶段的输出
        stage = result_context.stages.get('wservice.merge_speaker_based_subtitles')
        assert stage is not None
        assert stage.status == 'SUCCESS'

        output = stage.output
        assert 'merged_segments_file' in output
        assert output['total_segments'] == 3  # 应该生成 3 个 segments
        assert output['matched_segments'] >= 2  # 至少有 2 个有匹配词

        # 验证输出文件
        merged_file = output['merged_segments_file']
        assert os.path.exists(merged_file)

        # 读取并验证合并结果
        with open(merged_file, 'r', encoding='utf-8') as f:
            merged_segments = json.load(f)

        assert len(merged_segments) == 3

        # 验证第一个 segment
        seg1 = merged_segments[0]
        assert seg1['speaker'] == 'SPEAKER_00'
        assert seg1['start'] == 9.5
        assert seg1['end'] == 11.5
        assert 'Hello' in seg1['text'] or 'world' in seg1['text']
        assert 'match_quality' in seg1

        # 验证第二个 segment
        seg2 = merged_segments[1]
        assert seg2['speaker'] == 'SPEAKER_01'
        assert seg2['start'] == 11.8
        assert seg2['end'] == 13.0

        # 验证第三个 segment
        seg3 = merged_segments[2]
        assert seg3['speaker'] == 'SPEAKER_00'
        assert seg3['start'] == 13.0
        assert seg3['end'] == 14.5

        print("✅ 集成测试通过")
        print(f"生成的 segments 数量: {len(merged_segments)}")
        print(f"有匹配词的 segments: {output['matched_segments']}")
        print(f"无匹配词的 segments: {output['empty_segments']}")

        return True


def test_merge_speaker_based_subtitles_with_upstream_nodes():
    """集成测试：从上游节点获取数据"""

    # 准备测试数据
    transcript_segments = [
        {
            'start': 10.0,
            'end': 12.0,
            'text': 'Test segment',
            'words': [
                {'word': ' Test', 'start': 10.0, 'end': 10.5, 'probability': 0.9},
                {'word': ' segment', 'start': 10.6, 'end': 11.2, 'probability': 0.95}
            ]
        }
    ]

    diarization_segments = [
        {'start': 9.5, 'end': 11.5, 'speaker': 'SPEAKER_00', 'speaker_confidence': 0.95}
    ]

    # 创建临时目录
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建工作流上下文，模拟上游节点已完成
        workflow_context = WorkflowContext(
            workflow_id='test-integration-002',
            shared_storage_path=tmpdir,
            input_params={
                'task_name': 'wservice.merge_speaker_based_subtitles',
                'input_data': {}  # 不提供参数，从上游节点获取
            },
            stages={
                'faster_whisper.transcribe_audio': StageExecution(
                    status='SUCCESS',
                    output={
                        'segments': transcript_segments
                    }
                ),
                'pyannote_audio.diarize_speakers': StageExecution(
                    status='SUCCESS',
                    output={
                        'speaker_enhanced_segments': diarization_segments,
                        'detected_speakers': ['SPEAKER_00']
                    }
                )
            }
        )

        # 创建执行器
        executor = WServiceMergeSpeakerBasedSubtitlesExecutor(
            stage_name='wservice.merge_speaker_based_subtitles',
            context=workflow_context
        )

        # 执行
        result_context = executor.execute()

        # 验证结果
        stage = result_context.stages.get('wservice.merge_speaker_based_subtitles')
        assert stage is not None
        assert stage.status == 'SUCCESS'

        output = stage.output
        assert 'merged_segments_file' in output
        assert output['total_segments'] == 1

        print("✅ 上游节点数据获取测试通过")

        return True


if __name__ == '__main__':
    print("运行集成测试...")
    print("\n测试 1: 完整执行器流程")
    test_merge_speaker_based_subtitles_integration()

    print("\n测试 2: 从上游节点获取数据")
    test_merge_speaker_based_subtitles_with_upstream_nodes()

    print("\n✅ 所有集成测试通过")

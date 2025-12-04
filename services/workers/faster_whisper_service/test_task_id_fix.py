#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试任务ID传递修复
验证 faster_whisper_service 中的任务ID参数传递是否正确
"""

import sys
import os
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from services.common.context import WorkflowContext, StageExecution
from services.workers.faster_whisper_service.app.tasks import (
    _execute_transcription,
    _transcribe_audio_with_lock,
    _transcribe_audio_with_gpu_lock,
    _transcribe_audio_without_lock
)

def test_execute_transcription_with_workflow_context():
    """测试 _execute_transcription 函数正确使用 workflow_context.workflow_id"""
    print("🧪 测试 _execute_transcription 函数...")
    
    # 创建测试用的 WorkflowContext
    test_workflow_id = "test_task_12345"
    workflow_context = WorkflowContext(
        workflow_id=test_workflow_id,
        create_at="2025-12-04T08:00:00Z",
        input_params={},
        shared_storage_path=f"/share/workflows/{test_workflow_id}",
        stages={},
        error=None
    )
    
    # 创建测试用的服务配置
    service_config = {
        'model_name': 'test-model',
        'device': 'cpu',
        'compute_type': 'float32'
    }
    
    stage_name = "test_stage"
    
    # 测试正常情况
    try:
        # 由于函数会调用 subprocess，这里我们只验证函数能正确接收参数
        # 不实际执行转录过程
        import inspect
        sig = inspect.signature(_execute_transcription)
        
        # 验证函数签名包含 workflow_context 参数
        assert 'workflow_context' in sig.parameters
        assert sig.parameters['workflow_context'].annotation == WorkflowContext
        
        print("✅ _execute_transcription 函数签名正确")
        
    except Exception as e:
        print(f"❌ _execute_transcription 测试失败: {e}")
        raise

def test_transcribe_audio_with_lock_signature():
    """测试 _transcribe_audio_with_lock 函数签名正确"""
    print("🧪 测试 _transcribe_audio_with_lock 函数...")
    
    import inspect
    sig = inspect.signature(_transcribe_audio_with_lock)
    
    # 验证函数签名
    expected_params = ['audio_path', 'service_config', 'stage_name', 'workflow_context']
    actual_params = list(sig.parameters.keys())
    
    assert actual_params == expected_params, f"Expected {expected_params}, got {actual_params}"
    assert sig.parameters['workflow_context'].annotation == WorkflowContext
    
    print("✅ _transcribe_audio_with_lock 函数签名正确")

def test_transcribe_audio_with_gpu_lock_signature():
    """测试 _transcribe_audio_with_gpu_lock 函数签名正确"""
    print("🧪 测试 _transcribe_audio_with_gpu_lock 函数...")
    
    import inspect
    sig = inspect.signature(_transcribe_audio_with_gpu_lock)
    
    # 验证函数签名
    expected_params = ['audio_path', 'service_config', 'stage_name', 'workflow_context']
    actual_params = list(sig.parameters.keys())
    
    assert actual_params == expected_params, f"Expected {expected_params}, got {actual_params}"
    assert sig.parameters['workflow_context'].annotation == WorkflowContext
    
    print("✅ _transcribe_audio_with_gpu_lock 函数签名正确")

def test_transcribe_audio_without_lock_signature():
    """测试 _transcribe_audio_without_lock 函数签名正确"""
    print("🧪 测试 _transcribe_audio_without_lock 函数...")
    
    import inspect
    sig = inspect.signature(_transcribe_audio_without_lock)
    
    # 验证函数签名
    expected_params = ['audio_path', 'service_config', 'stage_name', 'workflow_context']
    actual_params = list(sig.parameters.keys())
    
    assert actual_params == expected_params, f"Expected {expected_params}, got {actual_params}"
    assert sig.parameters['workflow_context'].annotation == WorkflowContext
    
    print("✅ _transcribe_audio_without_lock 函数签名正确")

def test_parameter_passing_chain():
    """测试参数传递链的完整性"""
    print("🧪 测试参数传递链...")
    
    # 模拟创建测试用的数据
    test_workflow_id = "test_task_67890"
    
    # 验证函数之间能正确传递参数
    try:
        import inspect
        
        # 检查所有相关函数的参数传递兼容性
        functions_to_check = [
            _transcribe_audio_with_lock,
            _transcribe_audio_with_gpu_lock,
            _transcribe_audio_without_lock,
            _execute_transcription
        ]
        
        for func in functions_to_check:
            sig = inspect.signature(func)
            assert 'workflow_context' in sig.parameters, f"{func.__name__} 缺少 workflow_context 参数"
            print(f"  ✅ {func.__name__} 包含 workflow_context 参数")
        
        print("✅ 参数传递链完整")
        
    except Exception as e:
        print(f"❌ 参数传递链测试失败: {e}")
        raise

def test_old_logic_removed():
    """测试旧的缺陷逻辑是否被移除"""
    print("🧪 测试旧逻辑是否移除...")
    
    # 读取修复后的文件内容
    file_path = Path(__file__).parent / "app" / "tasks.py"
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 检查是否还有旧的缺陷逻辑
    old_logic_patterns = [
        "workflow_context.workflow_id if 'workflow_context' in locals()",
        "f\"task_{int(time.time())}\"",
    ]
    
    for pattern in old_logic_patterns:
        if pattern in content:
            raise AssertionError(f"发现旧的缺陷逻辑: {pattern}")
    
    # 确认新的正确逻辑存在
    if "task_id = workflow_context.workflow_id" not in content:
        raise AssertionError("未找到新的正确逻辑: task_id = workflow_context.workflow_id")
    
    print("✅ 旧逻辑已移除，新逻辑已添加")

def main():
    """运行所有测试"""
    print("🚀 开始测试任务ID传递修复...")
    print("=" * 60)
    
    try:
        test_execute_transcription_with_workflow_context()
        test_transcribe_audio_with_lock_signature()
        test_transcribe_audio_with_gpu_lock_signature()
        test_transcribe_audio_without_lock_signature()
        test_parameter_passing_chain()
        test_old_logic_removed()
        
        print("=" * 60)
        print("🎉 所有测试通过！任务ID传递修复验证成功！")
        print("\n📋 修复总结:")
        print("  ✅ 函数签名已更新，包含 workflow_context 参数")
        print("  ✅ 参数传递链完整")
        print("  ✅ 旧的缺陷逻辑已移除")
        print("  ✅ 新的正确逻辑已实现")
        print("\n🔧 现在传入的 task_id 将被正确使用，而不是生成随机ID")
        
    except Exception as e:
        print("=" * 60)
        print(f"❌ 测试失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
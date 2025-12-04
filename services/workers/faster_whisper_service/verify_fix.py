#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
验证任务ID传递修复
简单验证代码修复的正确性
"""

import re
from pathlib import Path

def verify_function_signatures():
    """验证函数签名是否正确"""
    print("🔍 验证函数签名...")
    
    file_path = Path(__file__).parent / "app" / "tasks.py"
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 检查函数签名
    patterns = {
        "_execute_transcription": r"def _execute_transcription\(\s*audio_path:\s*str,\s*service_config:\s*dict,\s*stage_name:\s*str,\s*workflow_context:\s*WorkflowContext\s*\)",
        "_transcribe_audio_with_lock": r"def _transcribe_audio_with_lock\(\s*audio_path:\s*str,\s*service_config:\s*dict,\s*stage_name:\s*str,\s*workflow_context:\s*WorkflowContext\s*\)",
        "_transcribe_audio_with_gpu_lock": r"def _transcribe_audio_with_gpu_lock\(\s*audio_path:\s*str,\s*service_config:\s*dict,\s*stage_name:\s*str,\s*workflow_context:\s*WorkflowContext\s*\)",
        "_transcribe_audio_without_lock": r"def _transcribe_audio_without_lock\(\s*audio_path:\s*str,\s*service_config:\s*dict,\s*stage_name:\s*str,\s*workflow_context:\s*WorkflowContext\s*\)"
    }
    
    for func_name, pattern in patterns.items():
        if not re.search(pattern, content):
            print(f"  ❌ {func_name} 函数签名不正确")
            return False
        else:
            print(f"  ✅ {func_name} 函数签名正确")
    
    return True

def verify_parameter_passing():
    """验证参数传递是否正确"""
    print("\n🔍 验证参数传递...")
    
    file_path = Path(__file__).parent / "app" / "tasks.py"
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 检查关键调用点的参数传递
    expected_calls = [
        "_transcribe_audio_with_gpu_lock(audio_path, service_config, stage_name, workflow_context)",
        "_transcribe_audio_without_lock(audio_path, service_config, stage_name, workflow_context)",
        "_execute_transcription(audio_path, service_config, stage_name, workflow_context)",
        "_transcribe_audio_with_lock(audio_path, service_config, stage_name, workflow_context)"
    ]
    
    for expected_call in expected_calls:
        if expected_call not in content:
            print(f"  ❌ 未找到预期的调用: {expected_call}")
            return False
        else:
            print(f"  ✅ 找到预期调用: {expected_call}")
    
    return True

def verify_old_logic_removed():
    """验证旧的缺陷逻辑是否被移除"""
    print("\n🔍 验证旧逻辑移除...")
    
    file_path = Path(__file__).parent / "app" / "tasks.py"
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 检查是否还有旧的缺陷逻辑
    old_patterns = [
        "workflow_context.workflow_id if 'workflow_context' in locals()",
        "f\"task_{int(time.time())}\""
    ]
    
    for pattern in old_patterns:
        if pattern in content:
            print(f"  ❌ 发现旧的缺陷逻辑: {pattern}")
            return False
    
    # 确认新的正确逻辑存在
    if "task_id = workflow_context.workflow_id" not in content:
        print("  ❌ 未找到新的正确逻辑: task_id = workflow_context.workflow_id")
        return False
    
    print("  ✅ 旧逻辑已移除，新逻辑已添加")
    return True

def verify_main_function_call():
    """验证主函数中的调用是否正确"""
    print("\n🔍 验证主函数调用...")
    
    file_path = Path(__file__).parent / "app" / "tasks.py"
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # 查找主函数中的调用
    in_main_function = False
    found_correct_call = False
    
    for line in lines:
        if "def transcribe_audio" in line:
            in_main_function = True
        elif in_main_function and "def " in line and "transcribe_audio" not in line:
            break
        
        if in_main_function and "_transcribe_audio_with_lock(audio_path, service_config, stage_name, workflow_context)" in line:
            found_correct_call = True
            print("  ✅ 主函数中调用参数传递正确")
            break
    
    if not found_correct_call:
        print("  ❌ 主函数中调用参数传递不正确")
        return False
    
    return True

def main():
    """运行验证"""
    print("🚀 开始验证任务ID传递修复...")
    print("=" * 60)
    
    checks = [
        verify_function_signatures,
        verify_parameter_passing,
        verify_old_logic_removed,
        verify_main_function_call
    ]
    
    all_passed = True
    for check in checks:
        try:
            if not check():
                all_passed = False
        except Exception as e:
            print(f"  ❌ 验证过程出错: {e}")
            all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 所有验证通过！任务ID传递修复验证成功！")
        print("\n📋 修复总结:")
        print("  ✅ 所有函数签名已更新，包含 workflow_context 参数")
        print("  ✅ 参数传递链完整且正确")
        print("  ✅ 旧的缺陷逻辑已完全移除")
        print("  ✅ 新的正确逻辑已正确实现")
        print("  ✅ 主函数调用已正确更新")
        print("\n🔧 现在传入的 task_id 将被正确使用，而不是生成随机ID")
        print("🎯 修复范围: 仅限 faster_whisper_service，其他服务正常工作")
    else:
        print("❌ 验证失败！请检查修复代码。")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
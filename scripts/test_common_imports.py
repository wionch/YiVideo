#!/usr/bin/env python3
"""测试services/common模块的导入功能"""

def test_subtitle_imports():
    """测试字幕相关导入"""
    try:
        from services.common.subtitle import SRTParser, SubtitleEntry
        from services.common.subtitle import parse_srt_file, write_srt_file
        from services.common.subtitle import AIProviderFactory, SubtitleCorrector
        print("✓ 字幕模块导入成功")
        return True
    except ImportError as e:
        print(f"✗ 字幕模块导入失败: {e}")
        return False

def test_gpu_memory_imports():
    """测试GPU内存管理导入"""
    try:
        from services.common.gpu_memory_manager import (
            initialize_worker_gpu_memory,
            cleanup_worker_gpu_memory,
            cleanup_paddleocr_processes
        )
        print("✓ GPU内存管理模块导入成功")
        return True
    except ImportError as e:
        print(f"✗ GPU内存管理模块导入失败: {e}")
        return False

def test_lock_manager_imports():
    """测试锁管理器导入"""
    try:
        from services.common import SmartGpuLockManager
        print("✓ SmartGpuLockManager导入成功")
        return True
    except ImportError as e:
        print(f"✗ SmartGpuLockManager导入失败: {e}")
        return False

def test_common_imports():
    """测试其他通用导入"""
    try:
        from services.common import get_logger, CONFIG, WorkflowContext, StageExecution
        from services.common import gpu_lock, state_manager
        print("✓ 通用模块导入成功")
        return True
    except ImportError as e:
        print(f"✗ 通用模块导入失败: {e}")
        return False

if __name__ == "__main__":
    print("开始测试services/common模块导入...")
    results = [
        test_subtitle_imports(),
        test_gpu_memory_imports(),
        test_lock_manager_imports(),
        test_common_imports()
    ]

    if all(results):
        print("\n🎉 所有测试通过！")
    else:
        print("\n❌ 部分测试失败，需要进一步修复")
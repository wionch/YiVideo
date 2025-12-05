# 修复 paddleocr_service 导入错误

## 变更概述

**变更ID**: fix-paddleocr-import-error
**类型**: 修复 (fix)
**优先级**: 高
**影响范围**: paddleocr_service

## Why

在执行 `paddleocr.detect_subtitle_area` 任务时，系统报错：
```
ModuleNotFoundError: No module named 'services.workers.paddleocr_service.app.utils.progress_logger'
```

**根本原因**: `decoder.py` 尝试从不存在的模块 `utils.progress_logger` 导入 `create_progress_bar`，但该模块已被删除。正确的模块位置在 `services/common/progress_logger`，需要修正导入路径。

**错误位置**:
- 文件: `services/workers/paddleocr_service/app/modules/decoder.py`
- 行号: 10
- 问题代码: `from ..utils.progress_logger import create_progress_bar`

## What Changes

- 修改 `services/workers/paddleocr_service/app/modules/decoder.py` 第10行导入语句
  - 从: `from ..utils.progress_logger import create_progress_bar`
  - 改为: `from services.common.progress_logger import create_progress_bar`

- 修改 `services/workers/paddleocr_service/app/modules/change_detector.py` 第11行导入语句
  - 从: `from ..utils.progress_logger import create_stage_progress`
  - 改为: `from services.common.progress_logger import create_stage_progress`

## 预期解决方案

将导入路径修正为 `services.common.progress_logger`，该模块包含所需的 `create_progress_bar` 函数。

## 成功标准

1. `decoder.py` 能够正确导入 `create_progress_bar`
2. `paddleocr.detect_subtitle_area` 任务能够成功执行
3. 不产生 `ModuleNotFoundError` 错误

## 风险评估

**风险等级**: 低
**风险描述**: 这是一个简单的导入路径修复，不涉及业务逻辑变更
**缓解措施**: 修改后通过执行测试任务验证功能正常

## 变更范围

### 需要修改的文件
- `services/workers/paddleocr_service/app/modules/decoder.py` (第10行导入语句)

### 不会影响的功能
- 其他所有 paddleocr_service 功能保持不变
- 其他服务模块不受影响

## 验证计划

1. 验证导入语句修复后模块可以正常加载
2. 测试完整的 `paddleocr.detect_subtitle_area` 工作流

## 回滚计划

如果修复后出现新问题，可以直接回滚导入语句到原始状态，或使用原来的模块路径（如果恢复）。

## 实施时间线

预计完成时间: 5分钟
测试时间: 5分钟
总时间: 10分钟

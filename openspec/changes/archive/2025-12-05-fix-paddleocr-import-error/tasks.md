# 修复 paddleocr_service 导入错误 - 任务清单

## 任务概览

**变更ID**: fix-paddleocr-import-error
**目标**: 修复 decoder.py 中的模块导入错误
**预估时间**: 10分钟

## 任务列表

### 1. 修改导入语句 (2分钟)
**状态**: 待执行
**描述**: 修正 `decoder.py` 第10行的导入语句
**操作**:
- 打开 `services/workers/paddleocr_service/app/modules/decoder.py`
- 将第10行的 `from ..utils.progress_logger import create_progress_bar`
- 修改为 `from services.common.progress_logger import create_progress_bar`
**验证**: 确认文件保存成功

### 2. 验证模块加载 (2分钟)
**状态**: 待执行
**描述**: 验证修复后 decoder.py 能够正常导入
**操作**:
- 在 Python 环境中尝试导入 decoder 模块
- 确认无 ModuleNotFoundError
**预期结果**: 模块导入成功，无错误信息

### 3. 功能测试 (5分钟)
**状态**: 待执行
**描述**: 测试 paddleocr.detect_subtitle_area 任务执行
**操作**:
- 使用现有的测试数据或创建简单的测试场景
- 执行完整的 detect_subtitle_area 工作流
**预期结果**: 任务成功完成，无导入错误

### 4. 检查其他引用 (1分钟)
**状态**: 待执行
**描述**: 确认没有其他文件依赖已删除的 progress_logger 模块
**操作**:
- 搜索项目中是否还有其他文件从 `utils.progress_logger` 导入
- 如有发现，一并修复
**预期结果**: 无其他需要修复的文件

## 验证清单

- [ ] decoder.py 导入语句已修改
- [ ] Python 模块加载测试通过
- [ ] paddleocr.detect_subtitle_area 任务执行成功
- [ ] 无 ModuleNotFoundError 错误
- [ ] 其他 paddleocr 功能未受影响

## 依赖关系

无外部依赖，本修复为自包含操作。

## 并行化机会

任务1完成后可立即并行执行任务2和任务4。

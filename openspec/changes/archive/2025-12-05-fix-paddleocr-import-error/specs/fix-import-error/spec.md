# 修复 paddleocr_service 导入错误 - 技术规范

## Purpose
修复 paddleocr_service 中 decoder.py 模块的导入错误，解决 ModuleNotFoundError，使 paddleocr.detect_subtitle_area 任务能够正常执行。

## Why
当前 decoder.py 尝试从不存在的模块 `utils.progress_logger` 导入 `create_progress_bar`，导致任务执行失败。正确的模块位置在 `services.common.progress_logger`，需要修正导入路径。

## MODIFIED Requirements

### Requirement: 修正 decoder.py 导入语句
decoder.py SHALL 将第10行的导入语句从相对导入修改为绝对导入，以解决 ModuleNotFoundError。

#### Scenario: 导入错误修复
- **GIVEN** paddleocr.detect_subtitle_area 任务开始执行
- **AND** 需要导入 decoder.py 中的 GPUDecoder 类
- **WHEN** 系统加载模块时
- **THEN** decoder.py 成功从 services.common.progress_logger 导入 create_progress_bar
- **AND** 不出现 ModuleNotFoundError
- **AND** GPUDecoder 类可以正常实例化

#### Scenario: 进度条功能正常工作
- **GIVEN** decoder.py 能够正常导入
- **AND** 调用 GPUDecoder 的 decode 方法时设置 log_progress=True
- **WHEN** 执行视频解码过程
- **THEN** create_progress_bar 正常创建并显示进度条
- **AND** 进度条能够正确更新解码进度
- **AND** 解码完成后进度条显示完成信息

#### Scenario: detect_subtitle_area 任务成功执行
- **GIVEN** 使用有效的视频文件和关键帧
- **AND** 调用 paddleocr.detect_subtitle_area 任务
- **WHEN** 任务执行过程涉及 decoder.py 的加载和使用
- **THEN** 任务成功完成
- **AND** 不出现 ModuleNotFoundError
- **AND** 返回正确的字幕区域检测结果

## Verification
运行 `python -c "from services.workers.paddleocr_service.app.modules.decoder import GPUDecoder"` 验证导入成功，并执行完整的 detect_subtitle_area 工作流测试功能正常性。

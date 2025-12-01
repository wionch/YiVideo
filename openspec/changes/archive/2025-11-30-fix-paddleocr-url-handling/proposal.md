# 变更: 修复PaddleOCR字幕区域检测任务的URL处理问题

## Why
`paddleocr.detect_subtitle_area` 任务无法正确处理 `http://host.docker.internal:9000/...` 格式的URL输入，导致工作流执行失败。具体错误为：
```
ValueError: 无法获取有效的关键帧目录: http://host.docker.internal:9000/yivideo/task_id/keyframes
```

根本原因：当前的URL检测逻辑过于严格，只识别配置中定义的MinIO服务器主机名（如 `minio:9000`），不支持 `host.docker.internal` 等其他主机名，导致HTTP URL无法被正确识别为MinIO资源。

## What Changes
- 改进 `detect_subtitle_area` 任务的URL检测逻辑，支持任意HTTP/HTTPS URL格式
- 扩展MinIO URL识别，支持非标准主机名的MinIO服务器
- 保持向后兼容性，所有现有URL格式继续正常工作
- 在容器内进行了全面测试验证

## Impact
- **受影响的能力**: `paddleocr.detect_subtitle_area` 任务
- **受影响代码**: 
  - `services/workers/paddleocr_service/app/tasks.py` (第205-253行URL处理逻辑)
- **向后兼容**: ✅ 完全兼容现有功能
- **破坏性变更**: ❌ 无

## 验收标准
1. 能够正确处理 `http://host.docker.internal:9000/...` 格式的MinIO URL
2. 保持对现有URL格式的支持（`http://minio:9000/...`, `minio://...`）
3. 关键帧目录验证逻辑正确执行
4. 任务执行成功后返回正确的字幕区域检测结果
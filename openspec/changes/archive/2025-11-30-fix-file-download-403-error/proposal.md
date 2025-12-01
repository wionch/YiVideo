# 修复ffmpeg_service文件下载403错误

## 为什么
当前ffmpeg_service在处理视频下载任务时出现403错误，导致关键帧提取失败。错误日志显示尝试访问 `http://host.docker.internal:9000/yivideo/task_id/223.mp4` 时被拒绝，这影响了整个视频处理工作流的执行。

## 什么会改变
- **修复文件下载认证问题**: 改进MinIO访问认证机制，确保正确的身份验证
- **优化Docker环境兼容性**: 解决容器内外网络连接问题，特别是host.docker.internal的访问
- **增强错误处理**: 提供更详细的错误信息和重试机制
- **URL格式标准化**: 使用更可靠的MinIO访问方式
- **添加连接诊断**: 增加网络连接和权限检查功能

## 影响
- **受影响的规格**: 文件服务、FFmpeg服务、工作流执行
- **受影响的代码**: 
  - `services/common/file_service.py` - 核心文件下载逻辑
  - `services/workers/ffmpeg_service/app/tasks.py` - 关键帧提取任务
  - 可能需要更新的Docker配置和环境变量
- **风险评估**: 
  - 低风险：主要是修复现有功能的bug
  - 需要测试确保MinIO认证正常工作
  - 确保不影响其他服务的文件访问功能

## 修复策略
1. **使用现有MinIO模块**: 优先使用项目中的`MinIOFileService`和`minio_directory_download`模块
2. **修复URL识别逻辑**: 改进`file_service.py`中的HTTP MinIO URL识别和转换
3. **增强错误处理**: 提供更清晰的错误信息帮助诊断
4. **优化下载策略**: 在HTTP下载失败时自动回退到MinIO客户端下载

## 成功标准
- ffmpeg_service能够成功下载视频文件
- 403错误完全消除
- 工作流关键帧提取任务正常完成
- 提供详细的下载进度和错误日志信息
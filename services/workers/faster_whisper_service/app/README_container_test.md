# 字幕校正功能容器内测试指南

## 🎯 测试目标
在Docker容器内部测试字幕校正功能的完整性和可用性。

## 📋 前置条件

### 1. 容器内环境
```bash
# 进入faster_whisper_service容器
docker exec -it faster_whisper_service bash

# 或者使用compose
docker-compose exec faster_whisper_service bash
```

### 2. 关键路径验证
```bash
# 检查工作目录
pwd  # 应该是 /app

# 检查关键目录
ls -la /app/config/
ls -la /app/config/system_prompt/
ls -la /share/workflows/
```

### 3. 环境变量配置
```bash
# 检查API密钥配置
echo $DEEPSEEK_API_KEY
echo $GEMINI_API_KEY
echo $ZHIPU_API_KEY
echo $VOLCENGINE_API_KEY
```

## 🚀 测试执行

### 1. 基础功能测试
```bash
# 进入工作目录
cd /app

# 运行基础测试（不需要API密钥）
python services/workers/faster_whisper_service/app/test_subtitle_correction.py

# 或者使用完整路径
python app/test_subtitle_correction.py
```

### 2. 指定字幕文件测试
```bash
# 使用指定的字幕文件
python app/test_subtitle_correction.py \
  --test-file /share/workflows/45fa11be-3727-4d3b-87ce-08c09618183f/subtitles/666_with_speakers.srt
```

### 3. 指定AI提供商测试
```bash
# 测试特定AI提供商
python app/test_subtitle_correction.py \
  --provider deepseek \
  --test-file /share/workflows/45fa11be-3727-4d3b-87ce-08c09618183f/subtitles/666_with_speakers.srt
```

### 4. 完整API测试
```bash
# 包含实际API调用的完整测试
python app/test_subtitle_correction.py \
  --provider deepseek \
  --test-file /share/workflows/45fa11be-3727-4d3b-87ce-08c09618183f/subtitles/666_with_speakers.srt \
  --full-test
```

## 📊 测试输出解读

### 成功输出示例
```
🎬 YiVideo 字幕校正功能测试 - 容器内版本
============================================================
🔍 检测容器内环境...
✅ 工作目录: /app
✅ Python路径: /usr/local/bin/python
...

📽️ 检查测试字幕文件: /share/workflows/.../666_with_speakers.srt
✅ 字幕文件存在 (1234 bytes)

✅ 所有模块导入成功

🔧 测试SRT解析器...
✅ 解析成功，共 15 条字幕
✅ 统计信息: {'total_entries': 15, ...}
...

✅ 字幕校正器基础功能测试完成（未进行实际API调用）

✅ AI提供商测试完成: 4/4 成功

============================================================
📊 测试结果汇总
============================================================
SRT解析器           : ✅ 通过
配置管理           : ✅ 通过
API密钥配置        : ✅ 通过
AI提供商           : ✅ 通过
字幕校正器基础     : ✅ 通过

总计: 5/5 测试通过
🎉 所有测试通过！字幕校正功能在容器内运行正常。
```

### 完整API测试成功示例
```
🚀 完整字幕校正测试 (提供商: deepseek)...
🔄 自动开始完整API测试...
✅ 字幕校正成功!
   原始文件: /share/workflows/.../666_with_speakers.srt
   校正文件: /share/workflows/.../666_with_speakers_corrected.srt
   使用提供商: deepseek
   处理时间: 45.23秒
   统计信息: {'original_entries': 15, 'corrected_entries': 14, ...}
   原始内容长度: 1234 字符
   校正内容长度: 1198 字符
   内容变化: 有变化
```

## 🔧 故障排除

### 1. 模块导入失败
```
❌ 导入模块失败: No module named 'services.common.subtitle_parser'
```
**解决方案**:
- 检查Python路径: `echo $PYTHONPATH`
- 确认工作目录: `pwd`
- 检查services目录: `ls -la /app/services/`

### 2. 配置文件不存在
```
❌ 系统提示词文件不存在: /app/config/system_prompt/subtitle_optimization.md
```
**解决方案**:
- 检查config映射: `ls -la /app/config/`
- 重新启动容器: `docker-compose restart faster_whisper_service`

### 3. API密钥未配置
```
❌ DEEPSEEK_API_KEY: 未配置
```
**解决方案**:
- 在宿主机设置环境变量
- 重新启动容器: `docker-compose restart faster_whisper_service`

### 4. 字幕文件不存在
```
❌ 字幕文件不存在
```
**解决方案**:
- 检查文件路径: `ls -la /share/workflows/`
- 使用临时测试文件: `--test-file /tmp/test.srt`

## 📈 性能基准

### 预期测试时间
- **基础功能测试**: 5-15秒
- **完整API测试**: 30-90秒（取决于AI提供商响应速度）

### 资源消耗
- **内存使用**: 100-200MB
- **网络请求**: 1-5MB
- **CPU使用**: 5-15%

## 🎯 测试成功标准

### 基础功能测试
- ✅ 所有模块导入成功
- ✅ SRT解析器正常工作
- ✅ 配置管理正确加载
- ✅ AI提供商创建成功
- ✅ 字幕校正器基础功能正常

### 完整API测试
- ✅ API密钥配置正确
- ✅ AI服务调用成功
- ✅ 字幕校正输出正确
- ✅ 时间戳保持准确
- ✅ 统计信息完整

## 📞 技术支持

如果遇到问题，请：
1. 查看容器日志: `docker logs faster_whisper_service`
2. 检查配置文件: `cat /app/config.yml | grep subtitle_correction`
3. 验证环境变量: `env | grep API_KEY`
4. 测试网络连接: `curl -I https://api.deepseek.com`
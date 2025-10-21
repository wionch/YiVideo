# YiVideo 字幕校正功能使用指南

## 📋 功能概述

YiVideo字幕校正功能基于AI技术，能够对faster-whisper转录的字幕进行智能校正、修复和优化。支持多个主流AI服务提供商，有效提升字幕质量和准确性。

### ✨ 主要特性

- **多AI支持**: 支持DeepSeek、Gemini、智谱AI、火山引擎等多个AI服务提供商
- **智能校正**: 基于专业提示词，修复语音识别错误，优化断句和表达
- **时间戳保持**: 精确保持原始时间轴，确保音视频同步
- **批量处理**: 支持长字幕文件的自动分批处理
- **灵活配置**: 可通过配置文件灵活切换AI提供商和参数
- **错误处理**: 完善的重试机制和错误处理
- **统计报告**: 提供详细的处理统计和质量分析

## 🏗️ 架构设计

### 核心组件

```
services/common/
├── subtitle_correction.py       # 主字幕校正模块
├── ai_providers.py             # AI服务提供商适配器
├── subtitle_parser.py          # SRT字幕格式解析器
└── subtitle_correction_config.py  # 配置管理模块
```

### 工作流程

1. **字幕生成**: faster_whisper_service生成原始SRT字幕
2. **AI校正**: 根据配置调用指定AI服务进行内容校正
3. **时间戳对齐**: 保持原始时间戳，确保音视频同步
4. **文件输出**: 生成校正后的字幕文件
5. **统计报告**: 提供处理统计和质量分析

## ⚙️ 配置说明

### 1. 基础配置 (config.yml)

```yaml
subtitle_correction:
  # 默认AI服务提供商
  default_provider: deepseek

  # 处理参数
  max_subtitle_length: 2000      # 单次处理最大字符数
  max_tokens: 8000               # AI响应最大令牌数
  temperature: 0.1               # AI响应温度参数
  timeout_seconds: 300           # API请求超时时间

  # 文件配置
  system_prompt_path: "/app/config/system_prompt/subtitle_optimization.md"
  backup_original: true          # 是否备份原始字幕

  # 处理选项
  batch_processing: true         # 启用批量处理
  preserve_timestamps: true      # 保持原始时间戳
```

### 2. AI服务提供商配置

#### DeepSeek
```yaml
deepseek:
  api_key: ""                    # 从环境变量 DEEPSEEK_API_KEY 读取
  api_base_url: "https://api.deepseek.com/chat/completions"
  model: "deepseek-chat"
  enabled: true
```

#### Gemini
```yaml
gemini:
  api_key: ""                    # 从环境变量 GEMINI_API_KEY 读取
  api_base_url: "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent"
  model: "gemini-pro"
  enabled: true
```

#### 智谱AI
```yaml
zhipu:
  api_key: ""                    # 从环境变量 ZHIPU_API_KEY 读取
  api_base_url: "https://open.bigmodel.cn/api/paas/v4/chat/completions"
  model: "glm-4"
  enabled: true
```

#### 火山引擎
```yaml
volcengine:
  api_key: ""                    # 从环境变量 VOLCENGINE_API_KEY 读取
  api_base_url: "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
  model: "doubao-pro-32k"
  endpoint_id: ""                # 如果需要指定端点
  enabled: true
```

### 3. 环境变量配置

创建 `.env` 文件并设置API密钥：

```bash
# DeepSeek API密钥
DEEPSEEK_API_KEY=your_deepseek_api_key_here

# Gemini API密钥（复用现有配置）
GEMINI_API_KEY=your_gemini_api_key_here

# 智谱AI API密钥
ZHIPU_API_KEY=your_zhipu_api_key_here

# 火山引擎API密钥
VOLCENGINE_API_KEY=your_volcengine_api_key_here
VOLCENGINE_ENDPOINT_ID=your_endpoint_id_here
```

## 🚀 使用方法

### 1. 工作流集成

在API请求中启用字幕校正：

```json
{
  "video_path": "/share/videos/input/example.mp4",
  "input_params": {
    "enable_subtitle_correction": true,
    "correction_provider": "deepseek"
  },
  "workflow_config": {
    "workflow_chain": [
      "ffmpeg.extract_audio",
      "faster_whisper_service.generate_subtitles"
    ]
  }
}
```

### 2. 参数说明

- `enable_subtitle_correction`: 是否启用字幕校正（默认: false）
- `correction_provider`: 指定AI服务提供商（可选，默认使用配置中的default_provider）

### 3. 输出结果

字幕校正完成后，工作流输出将包含以下字段：

```json
{
  "subtitle_path": "/share/subtitles/original.srt",
  "corrected_subtitle_path": "/share/subtitles/original_corrected.srt",
  "correction_statistics": {
    "original_entries": 120,
    "corrected_entries": 118,
    "original_characters": 3500,
    "corrected_characters": 3420,
    "processing_time": 45.2,
    "provider": "deepseek"
  },
  "correction_provider_used": "deepseek",
  "original_subtitle_backup": "/share/subtitles/original_original.srt"
}
```

## 🧪 测试验证

### 1. 基础功能测试

运行测试脚本验证基础功能：

```bash
cd /path/to/YiVideo
python test_subtitle_correction.py
```

### 2. 指定提供商测试

```bash
# 测试特定AI提供商
python test_subtitle_correction.py --provider deepseek

# 完整API测试（需要有效API密钥）
python test_subtitle_correction.py --provider deepseek --full-test
```

### 3. 单独组件测试

```python
# 测试SRT解析器
from services.common.subtitle_parser import parse_srt_file
entries = parse_srt_file("subtitle.srt")

# 测试配置管理
from services.common.subtitle_correction_config import get_subtitle_correction_config
config = get_subtitle_correction_config()
print(f"默认提供商: {config.default_provider}")
```

## 📊 性能指标

### 处理速度

- **短字幕** (< 1000字符): 15-30秒
- **中等字幕** (1000-2000字符): 30-60秒
- **长字幕** (> 2000字符): 自动分批处理，每批30-60秒

### 质量提升

- **准确率提升**: 预计提升15-25%的字幕质量
- **错误修正**: 有效修复同音字、识别错误等问题
- **断句优化**: 智能合并不合理拆分的句子
- **表达优化**: 提升语言流畅度和专业性

### 资源消耗

- **网络带宽**: 每次请求约1-5KB
- **内存使用**: 基础50MB + 字幕文件大小
- **API调用**: 按字符数计费，具体取决于提供商

## 🔧 故障排除

### 常见问题

#### 1. 模块导入失败

**错误**: `ImportError: No module named 'services.common.subtitle_correction'`

**解决方案**:
- 确保在项目根目录运行脚本
- 检查Python路径设置
- 确认所有模块文件已创建

#### 2. API密钥未配置

**错误**: `API密钥未配置，请设置环境变量`

**解决方案**:
- 检查 `.env` 文件是否正确配置
- 确认环境变量名称正确
- 重启服务以加载新的环境变量

#### 3. 系统提示词文件不存在

**错误**: `系统提示词文件不存在: /app/config/system_prompt/subtitle_optimization.md`

**解决方案**:
- 确认 `config/system_prompt/subtitle_optimization.md` 文件存在
- 检查Docker容器内的文件路径映射
- 验证文件读取权限

#### 4. AI服务调用失败

**错误**: `API调用失败: 401 Unauthorized`

**解决方案**:
- 验证API密钥是否有效
- 检查网络连接
- 确认API配额是否充足
- 查看AI服务提供商的状态页面

#### 5. 字幕格式错误

**错误**: `字幕块格式不正确，至少需要3行`

**解决方案**:
- 检查原始SRT文件格式
- 确认时间戳格式正确 (HH:MM:SS,mmm)
- 验证字幕序号连续性

### 调试技巧

#### 1. 启用详细日志

在 `config.yml` 中设置：

```yaml
subtitle_correction:
  log_level: "DEBUG"
  verbose_processing: true
  log_api_stats: true
```

#### 2. 检查配置

```python
from services.common.subtitle_correction_config import get_subtitle_correction_config
config = get_subtitle_correction_config()
print(config.to_dict())
```

#### 3. 单独测试AI提供商

```python
from services.common.ai_providers import AIProviderFactory
factory = AIProviderFactory()
provider = factory.create_provider('deepseek', {'api_key': 'your_key'})
response = await provider.chat_completion([{"role": "user", "content": "测试"}])
print(response)
```

## 📈 优化建议

### 1. 性能优化

- **批量处理**: 对长字幕启用批量处理，避免单次请求过大
- **并发控制**: 合理设置批处理大小，平衡速度和稳定性
- **缓存机制**: 对重复内容启用缓存，减少API调用

### 2. 质量优化

- **温度参数**: 降低temperature参数获得更保守的校正
- **提示词优化**: 根据具体需求调整系统提示词
- **后处理**: 对AI结果进行后处理验证

### 3. 成本优化

- **提供商选择**: 根据成本效益选择合适的AI提供商
- **内容过滤**: 预先过滤无需校正的内容
- **缓存复用**: 复用相似内容的校正结果

## 🔮 未来扩展

### 计划功能

- **更多AI提供商**: 支持更多主流AI服务
- **多格式支持**: 扩展VTT、ASS等字幕格式
- **质量评估**: 集成自动质量评估机制
- **个性化校正**: 支持用户自定义校正规则
- **实时校正**: 支持实时字幕流校正

### 贡献指南

欢迎提交Issue和Pull Request来改进字幕校正功能：

1. **Bug报告**: 提供详细的错误信息和复现步骤
2. **功能建议**: 描述具体需求和使用场景
3. **代码贡献**: 遵循项目代码规范，添加必要测试

---

## 📞 技术支持

如遇到问题，请：

1. 查看本文档的故障排除部分
2. 检查项目的GitHub Issues
3. 提供详细的错误日志和环境信息
4. 包含复现步骤和期望结果

**注意**: 字幕校正功能需要有效的AI服务API密钥，请提前申请相应服务。
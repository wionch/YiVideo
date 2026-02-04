# MCP Server 详细说明

> 本文件包含每个 MCP server 的详细能力说明、调用模板和最佳实践。仅在需要具体实现细节时阅读。

---

## serena - 代码符号分析

### 核心能力
- 符号级代码定位（定义/引用/调用链）
- LSP 语义分析（类型推断/重命名）
- 影响面分析（重构前评估）

### 调用模板

#### 1. 符号定位
```python
# 查找符号定义
mcp__serena__find_symbol(
    name_path_pattern="MyClass/my_method",  # 支持绝对路径 /MyClass 或相对路径
    relative_path="services/",              # 可选：限定搜索范围
    include_body=True,                      # 是否包含代码体
    depth=1                                 # 子符号深度（0=仅当前，1=含子符号）
)

# 查找引用
mcp__serena__find_referencing_symbols(
    name_path="MyClass/my_method",
    relative_path="services/my_module.py"
)
```

#### 2. 项目激活（硬约束）
```python
# 若返回 "No active project"，必须先激活
mcp__serena__activate_project(project="YiVideo")
# 然后立即重试原操作（不得跳过）
```

### 最佳实践
- 先用 `get_symbols_overview` 了解文件结构
- 重构前必须用 `find_referencing_symbols` 评估影响面
- 不确定符号名时用 `substring_matching=True`

---

## context7 - 库文档查询

### 核心能力
- 版本特定的库文档（避免 API 幻觉）
- 代码示例抽取
- 跨版本对比

### 调用模板

```python
# 1. 解析库名到 library ID
mcp__context7__resolve-library-id(
    libraryName="fastapi",
    query="用户原始问题（用于相关性排序）"
)
# 返回：/tiangolo/fastapi 或 /tiangolo/fastapi/v0.115.0

# 2. 查询文档
mcp__context7__query-docs(
    libraryId="/tiangolo/fastapi",
    query="如何定义路由参数验证"
)
```

### 最佳实践
- query 应包含具体场景，而非泛泛的"如何使用"
- 优先使用精确版本（如 /org/project/v1.2.3）
- 结果中的代码示例可直接复制，无需验证

---

## sequential-thinking - 结构化推理

### 核心能力
- 复杂问题分解（≥3 子问题）
- 假设列举与验证
- 多方案对比与权衡

### 调用模板

```python
mcp__sequential-thinking__sequentialthinking(
    thought="当前思考步骤",
    thoughtNumber=1,
    totalThoughts=5,  # 可动态调整
    nextThoughtNeeded=True,
    isRevision=False,  # 是否修正之前的推理
    revisesThought=None  # 若 isRevision=True，指定修正哪个 thought
)
```

### 最佳实践
- 第一个 thought 应该是"问题分解"
- totalThoughts 是估计值，可在推理中调整
- 遇到矛盾时用 isRevision=True 回溯
- 最后一个 thought 应给出"工具调用计划"

---

## brave-search / exa / tavily-remote - Web 研究

### 工具选择策略

| 场景 | 优先工具 | 理由 |
|------|---------|------|
| 广覆盖发现 | brave-search | 结果多样性高 |
| 精准筛选/研究级 | exa | 高信噪比，适合技术内容 |
| 结构化抽取 | tavily-remote | 抽取字段/段落，站点级整理 |

### 调用模板

#### brave-search
```python
mcp__brave-search__brave_web_search(
    query="FastAPI async dependency injection",
    count=10,
    offset=0
)
```

#### exa
```python
mcp__exa__web_search_exa(
    query="FastAPI async dependency injection best practices",
    numResults=5,
    type="deep"  # auto/fast/deep
)
```

#### tavily-remote
```python
# 抽取页面内容
mcp__tavily-remote__tavily_extract(
    urls=["https://fastapi.tiangolo.com/..."],
    format="markdown",
    extract_depth="advanced"  # basic/advanced（advanced 用于 LinkedIn、表格）
)

# 站点级爬取
mcp__tavily-remote__tavily_crawl(
    url="https://docs.example.com/",
    max_depth=2,
    max_breadth=10,
    instructions="只抓取 API 文档页面"
)
```

### 交叉验证规则
- 时间敏感结论：至少两来源互证
- 高风险结论：优先一手来源（官方文档/规范/主仓库）
- 冲突结果：抓取官方页面解释差异

---

## chrome-devtools - 浏览器渲染兜底

### 核心能力
- 动态页面渲染（JS 依赖）
- 反爬破解（需要交互）
- 页面状态截图验证

### 调用模板

```python
# 1. 导航并等待
mcp__chrome-devtools__navigate_page(
    url="https://example.com",
    type="url"
)
mcp__chrome-devtools__wait_for(
    text="加载完成标志",
    timeout=10000
)

# 2. 获取页面结构
mcp__chrome-devtools__take_snapshot(
    verbose=False  # True 包含完整 a11y 树
)

# 3. 执行 JS 提取内容
mcp__chrome-devtools__evaluate_script(
    function="() => { return document.body.innerText; }"
)

# 4. 截图验证（可选）
mcp__chrome-devtools__take_screenshot(
    fullPage=True,
    format="png"
)
```

### 兜底路径
1. tavily-remote 抽取失败 → chrome-devtools 渲染
2. 需要点击/填表才能获取内容 → chrome-devtools 交互
3. 输出说明："通过浏览器渲染获取"

---

## filesystem - 文件系统操作

### 核心能力
- 批量文件读写
- dryRun 预览 diff
- 目录树管理

### 调用模板

```python
# 1. 确认允许目录
mcp__filesystem__list_allowed_directories()

# 2. 搜索文件
mcp__filesystem__search_files(
    path="/opt/wionch/docker/yivideo",
    pattern="**/*.py",  # 支持 glob
    excludePatterns=["**/test_*", "**/__pycache__/**"]
)

# 3. 批量读取
mcp__filesystem__read_multiple_files(
    paths=["file1.py", "file2.py"]
)

# 4. 编辑（先预览）
mcp__filesystem__edit_file(
    path="config.yml",
    edits=[{
        "oldText": "old_value",
        "newText": "new_value"
    }],
    dryRun=True  # 先预览 diff
)
# 确认后再次调用 dryRun=False
```

### 最佳实践
- 所有写操作前必须先 dryRun
- 批量操作优先用 `read_multiple_files` 而非循环 Read
- 大文件用 `head`/`tail` 参数限制读取行数

---

## hf-mcp-server - Hugging Face 模型搜索

### 核心能力
- 模型/数据集/论文搜索
- 元数据获取（下载量/stars/标签）
- 文档查询

### 调用模板

```python
# 模型搜索
mcp__hf-mcp-server__model_search(
    query="whisper",
    task="automatic-speech-recognition",
    sort="downloads",
    limit=10
)

# 数据集搜索
mcp__hf-mcp-server__dataset_search(
    query="chinese asr",
    sort="downloads",
    limit=10
)

# 获取详情
mcp__hf-mcp-server__hub_repo_details(
    repo_ids=["openai/whisper-large-v3"],
    repo_type="model"
)

# 文档搜索
mcp__hf-mcp-server__hf_doc_search(
    product="transformers",
    query="pipeline automatic speech recognition"
)
```

---

## modelscope - 魔搭社区模型搜索

### 核心能力
- 中文模型/数据集搜索
- 工作室（在线 Demo）发现
- MCP 服务器搜索

### 调用模板

```python
# 模型搜索（中文场景优先）
mcp__modelscope__search_models(
    query="语音识别",
    task="text-to-speech",
    sort="DownloadsCount",
    limit=10
)

# 数据集搜索
mcp__modelscope__search_datasets(
    query="中文对话",
    sort="downloads",
    limit=10
)

# 工作室搜索
mcp__modelscope__search_studios(
    query="图像生成",
    domains=["cv", "multi-modal"],
    sort="VisitsCount"
)
```

### 优先级策略
- 中文语音识别/TTS → ModelScope 优先（如 FunASR、SenseVoice）
- 国际前沿研究 → Hugging Face 优先
- 两者交叉验证：ModelScope 模型可能在 HF 有镜像

---

## github - GitHub 仓库管理

### 核心能力
- 仓库/代码精确搜索
- Issue/PR 管理
- Commit/Branch 查看

### 调用模板

```python
# 仓库搜索
mcp__github__search_repositories(
    query="language:python stars:>1000 topic:asr",
    sort="stars",
    minimal_output=True
)

# 代码搜索
mcp__github__search_code(
    query="whisper.load_model language:python"
)

# Issue 搜索
mcp__github__search_issues(
    query="is:open label:bug whisper",
    owner="openai",
    repo="whisper"
)

# 获取用户信息
mcp__github__get_me()
```

### 与其他工具配合
- serena 定位本地代码 → github 搜索社区实现
- hf/modelscope 找模型 → github 查看源码仓库
- brave/exa 发现项目 → github 深入仓库细节

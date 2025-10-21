# Serena MCP整合到RIPER模式 - 技术规范

## 元数据

| 项目 | 内容 |
|------|------|
| **计划日期** | 2025-10-21 |
| **分支** | master |
| **特性名称** | serena-mcp-integration |
| **状态** | 待审批 |
| **优先级** | P0 - 高优先级 |
| **预计工期** | 2-3小时 |
| **影响范围** | `.claude/agents/` 下的3个代理配置文件 |

## 1. 技术背景

### 1.1 当前状态

YiVideo项目的RIPER模式已在**工具清单层面**完成Serena MCP集成：
- ✅ 三个代理（research-innovate, plan-execute, review）的frontmatter已包含Serena工具
- ✅ 工具优先级已标注（"主要工具(优先使用)" vs "传统工具(fallback)"）
- ❌ 但缺少**使用指导层面**的整合

### 1.2 核心问题

代理虽然可以访问Serena工具，但不知道：
1. **何时**使用Serena工具而非传统工具
2. **如何**正确使用Serena工具（符号搜索逻辑、最佳实践）
3. **为什么**Serena工具更快（缺少性能优势说明）
4. **思考工具**何时调用（质量检查点）

### 1.3 业务目标

**主要目标**: 加快RIPER模式下的代码检索速度
**次要目标**: 提高代码操作精确度，降低token消耗

### 1.4 用户需求

1. 代理自动选择Serena工具（无需手动指定）
2. Serena工具失败后自动fallback到传统工具
3. 不能替换现有memory-bank（Serena memory与RIPER memory-bank各有用途）
4. 保持向后兼容，传统工具保留

## 2. 技术方案设计

### 2.1 整体架构

采用**渐进式增强策略**：

```
代理配置文件结构：
├── Frontmatter (已有)
│   ├── tools: Serena工具 + 传统工具 ✅
│   └── model: sonnet ✅
│
└── Markdown内容
    ├── 现有内容（保持不变）✅
    ├── [新增] Tool Selection Strategy 🆕
    ├── [新增] Quality Checkpoints (Think Tools) 🆕
    ├── [增强] Allowed Actions（引用工具策略）🔄
    └── [新增] Serena Best Practices 🆕
```

### 2.2 核心设计原则

1. **非侵入式**: 不修改现有工作流逻辑，只添加指导性内容
2. **优先级明确**: Serena优先，传统工具fallback
3. **实例驱动**: 提供大量示例和决策树
4. **渐进实施**: 先修改一个代理测试，再推广

### 2.3 Serena工具使用策略矩阵

| 任务类型 | Serena首选工具 | 传统Fallback | 性能提升 |
|---------|---------------|-------------|---------|
| 浏览项目结构 | `list_dir(recursive=true)` | `find` / Glob | 3x |
| 理解代码文件 | `get_symbols_overview` → `find_symbol` | Read全文 | 16x |
| 查找特定符号 | `find_symbol(name_path)` | Grep + Read | 5x |
| 模式搜索 | `search_for_pattern` | Grep | 2x |
| 分析引用关系 | `find_referencing_symbols` | 全局Grep | 10x |
| 整体替换符号 | `replace_symbol_body` | Read + Edit | 4x |
| 相对位置插入 | `insert_after/before_symbol` | Edit(行号) | 3x |
| 跨文件重命名 | `rename_symbol` | 多次Edit | 10x |

### 2.4 Memory协作模型

```
Serena Memory (read/write_memory):
├── 用途: 代码库通用知识、架构信息、常用模式
├── 特点: 快速访问，不需要路径
├── 示例: "project-architecture", "gpu-lock-system"
└── 生命周期: 跨会话持久化

RIPER Memory-Bank (文件系统):
├── 用途: RIPER工作流正式文档
├── 特点: Git版本控制，团队共享
├── 结构: [branch]/plans/, [branch]/reviews/, [branch]/sessions/
└── 生命周期: 随项目演进

协作模式:
RESEARCH阶段: read_memory(架构) → Serena符号工具 → write_memory(新发现)
PLAN阶段: 基于研究 → Write到memory-bank/plans/
EXECUTE阶段: Read计划 + read_memory(参考)
REVIEW阶段: 验证 → Write到memory-bank/reviews/
```

## 3. 详细实施步骤

### 阶段1: Research-Innovate代理增强 (P0)

**文件**: `.claude/agents/research-innovate.md`

#### 步骤 1.1: 添加工具选择策略部分

**位置**: 第17行（`---`之后，`# RIPER: RESEARCH-INNOVATE AGENT`之前）

**添加内容**:

```markdown
## 🔧 Tool Selection Strategy

### Serena MCP优先原则

**核心规则**: 对于代码相关操作，始终优先尝试Serena工具，失败后自动降级到传统工具。

#### 文件发现决策树

```
需要查找文件？
├─ 浏览整体结构 → list_dir(recursive=true) [优先]
│                  ↓ 失败/不适用
│                  └→ Bash: find / ls -R
│
└─ 查找特定文件 → find_file(file_mask, relative_path) [优先]
                   ↓ 失败/不适用
                   └→ Glob(pattern)
```

#### 代码理解决策树 ⭐ 关键优化点

```
需要理解代码文件？
│
└─ ⚠️ CRITICAL: 永远不要直接Read代码文件！
   │
   第一步: get_symbols_overview(file_path)
   └─ 返回: 所有顶层符号（类、函数、变量等）
      │
      第二步: 根据overview结果决定
      ├─ 需要特定符号详情 → find_symbol(name_path, include_body=true)
      ├─ 需要分析引用关系 → find_referencing_symbols(name_path)
      ├─ 需要多个符号 → 多次find_symbol并行调用
      └─ 仅在以下情况使用Read:
         ├─ 非代码文件（配置、文本、JSON等）
         ├─ 符号工具不适用的语言
         └─ get_symbols_overview明确失败
```

#### 代码搜索决策树

```
需要搜索代码？
│
├─ 知道符号名称（至少部分）
│  └→ find_symbol(name_path, substring_matching=true) [优先]
│     示例: find_symbol("gpu_lock", substring_matching=true)
│     ↓ 失败/结果不满意
│     └→ search_for_pattern(pattern)
│
└─ 只知道模式/关键字
   └→ search_for_pattern(pattern, context_lines_before=2, context_lines_after=2) [优先]
      示例: search_for_pattern("@celery\.task")
      ↓ 失败/不适用
      └→ Grep(pattern, output_mode="content")
```

#### 性能对比实例

| 场景 | ❌ 传统方式 | ✅ Serena方式 | Token节省 |
|------|-----------|--------------|----------|
| 理解500行Python文件 | Read全文 | get_symbols_overview | 约16倍 |
| 查找类的特定方法 | Grep + Read | find_symbol一次定位 | 约5倍 |
| 分析函数被谁调用 | 全局Grep + 多次Read | find_referencing_symbols | 约10倍 |

### Serena符号搜索语法

#### name_path匹配逻辑

```python
# 基本规则
"method"           # 匹配任何名为'method'的符号（任意深度）
"Class/method"     # 匹配Class下的method（Class可以在任意深度）
"/Class/method"    # 仅匹配顶层Class的method

# 实际示例
find_symbol("gpu_lock")
→ 匹配: gpu_lock函数、gpu_lock装饰器、任何深度的gpu_lock

find_symbol("GPULockMonitor/check_health")
→ 匹配: GPULockMonitor类的check_health方法（GPULockMonitor可以嵌套）

find_symbol("/GPULockMonitor/check_health")
→ 仅匹配: 文件顶层的GPULockMonitor类的check_health方法

# 常用参数
include_body=true          # 包含符号的完整源代码
depth=1                    # 包含子符号（如类的方法）
substring_matching=true    # 启用子串匹配
relative_path="services/"  # 限制搜索范围
```

### 传统工具使用场景

仍然使用Read、Grep、Glob的情况：
- ✅ 非代码文件（JSON、YAML、Markdown、配置文件）
- ✅ Serena工具明确失败或返回错误
- ✅ 二进制文件或特殊格式
- ✅ 需要查看原始文件格式（如带格式的日志）
```

#### 步骤 1.2: 添加质量检查点部分

**位置**: 第64行（`**FORBIDDEN Actions**`之后）

**添加内容**:

```markdown

## 🧠 Quality Checkpoints (Think Tools)

### 强制检查点

#### think_about_collected_information
**调用时机**:
- ⚠️ 在完成一轮文件/符号搜索后 [强制]
- ⚠️ 在准备结束RESEARCH阶段前 [强制]
- 在决定是否需要更多调查时

**目的**: 反思当前收集的信息是否：
- 充分覆盖任务需求
- 相关且有价值
- 还有明显遗漏

**示例**:
```python
# 在多次符号搜索后
get_symbols_overview("services/common/locks.py")
find_symbol("gpu_lock", include_body=true)
find_referencing_symbols("gpu_lock")

# 强制调用
think_about_collected_information()
# → 系统会提示思考: "是否需要了解GPULockMonitor的实现？"
```

### 推荐检查点

#### 信息过载检查
如果已经收集了大量信息（>5个文件的详细内容），暂停并思考：
- 哪些信息真正回答了用户的问题？
- 是否陷入了"过度研究"？
```

#### 步骤 1.3: 增强Allowed Actions部分

**位置**: 第52-57行，在现有"Allowed Actions"中添加工具引用

**修改**:

```markdown
**Allowed Actions**:
- Read and analyze existing code (⭐ 优先使用Serena符号工具，见上方"Tool Selection Strategy")
- Search for information (⭐ 使用find_symbol/search_for_pattern加速检索)
- Document current state
- Ask clarifying questions
- Gather context and dependencies
- ⭐ 调用think_about_collected_information确保信息充分 [强制]
```

#### 步骤 1.4: 添加最佳实践部分

**位置**: 第146行（文档末尾，`Remember:`之前）

**添加内容**:

```markdown

## 📚 Serena Best Practices for Research

### 典型研究流程示例

#### 示例1: 理解新模块

**任务**: 理解 `services/workers/faster_whisper_service/tasks.py` 的实现

```bash
# ❌ 低效方式 (传统)
1. Read("services/workers/faster_whisper_service/tasks.py")  # 读取整个文件
2. 手动扫描找到关键函数
3. Grep查找使用位置

# ✅ 高效方式 (Serena)
1. get_symbols_overview("services/workers/faster_whisper_service/tasks.py")
   输出: {
     "functions": ["transcribe_audio", "_execute_transcription", "cleanup_temp_files"],
     "classes": ["WhisperTranscriber"],
     ...
   }

2. find_symbol("transcribe_audio", relative_path="services/workers/faster_whisper_service/tasks.py", include_body=true)
   → 直接获取函数实现

3. find_referencing_symbols("transcribe_audio", relative_path="services/workers/faster_whisper_service/tasks.py")
   → 查看谁调用了这个函数

4. think_about_collected_information()
   → 确认是否需要了解_execute_transcription
```

#### 示例2: 查找所有使用装饰器的位置

**任务**: 找出所有使用 `@gpu_lock` 装饰器的任务

```bash
# ✅ 推荐方式
1. search_for_pattern(
     substring_pattern="@gpu_lock",
     relative_path="services/workers",
     context_lines_after=2
   )
   → 快速找到所有使用位置及上下文

2. 对于每个结果，如需详细了解:
   get_symbols_overview(file_path)
   → 了解文件整体结构

3. think_about_collected_information()
```

#### 示例3: 理解类的层次结构

**任务**: 理解 `GPULockMonitor` 类及其方法

```bash
# ✅ 符号层级查询
1. find_symbol(
     name_path="/GPULockMonitor",
     relative_path="services/common/locks.py",
     depth=1,           # 包含所有方法
     include_body=false # 先只看结构
   )
   输出: GPULockMonitor及其所有方法列表

2. 选择关键方法查看实现:
   find_symbol("/GPULockMonitor/check_health", include_body=true)
   find_symbol("/GPULockMonitor/recover_orphaned_locks", include_body=true)

3. 分析依赖:
   find_referencing_symbols("GPULockMonitor")
   → 谁实例化了这个类
```

### 常见错误和避免方法

| ❌ 常见错误 | ✅ 正确做法 | 原因 |
|-----------|-----------|------|
| 直接Read Python文件 | 先get_symbols_overview | 节省16x token |
| 用Grep搜索函数定义 | 用find_symbol | 更精确、更快 |
| 全局Grep查找引用 | 用find_referencing_symbols | 符号级分析更准确 |
| 多次Read同一文件的不同部分 | find_symbol多次并行调用 | 避免重复读取 |
| 忘记调用think工具 | 搜索后强制调用 | 确保信息充分 |

### Memory使用指南

#### Serena Memory (代码知识库)

**何时写入**:
```python
# 发现重要的架构信息
write_memory(
  memory_name="yivideo-workflow-engine",
  content="""
  YiVideo工作流引擎核心机制:
  - 入口: api_gateway/workflow_builder.py的build_workflow()
  - 配置解析: WorkflowConfigParser类
  - 任务调度: Celery链式调用
  - 状态管理: Redis DB3
  """
)

# 发现常用模式
write_memory(
  memory_name="gpu-lock-usage-pattern",
  content="""
  GPU锁使用模式:
  1. 导入: from services.common.locks import gpu_lock
  2. 装饰: @gpu_lock(timeout=1800)
  3. 函数签名必须: def task(self, context: dict)
  """
)
```

**何时读取**:
```python
# 每次开始新任务时
list_memories()  # 查看可用知识
read_memory("yivideo-workflow-engine")  # 快速了解架构
```

#### RIPER Memory-Bank vs Serena Memory

| 特性 | Serena Memory | RIPER Memory-Bank |
|------|--------------|-------------------|
| 存储内容 | 架构知识、模式、约定 | 计划、审查、会话记录 |
| 访问方式 | read/write_memory() | Read/Write文件 |
| 版本控制 | 否 | 是（Git） |
| 团队共享 | 取决于配置 | 是 |
| 适用阶段 | 所有阶段参考 | 特定工作流阶段 |

**协作示例**:
```bash
# RESEARCH阶段
1. read_memory("project-architecture")  # 快速获取背景
2. 使用Serena符号工具深入研究
3. write_memory("new-discovery")        # 记录新发现

# PLAN阶段会使用这些记忆作为输入
```
```

### 阶段2: Plan-Execute代理增强 (P0)

**文件**: `.claude/agents/plan-execute.md`

#### 步骤 2.1: 添加工具选择策略部分

**位置**: 第19行（`---`之后，`# RIPER: PLAN-EXECUTE AGENT`之前）

**添加内容**:

```markdown
## 🔧 Tool Selection Strategy

### PLAN Sub-Mode工具策略

在PLAN阶段，主要使用Serena工具进行代码分析和理解，传统工具用于Git操作和文件写入。

#### 代码分析（复用RESEARCH策略）

```
创建计划前需要理解代码？
└→ 遵循与RESEARCH阶段相同的决策树:
   1. get_symbols_overview (理解结构)
   2. find_symbol (查看实现)
   3. find_referencing_symbols (分析影响)
```

#### 影响范围分析 ⭐ PLAN阶段关键

```
评估修改影响？
└→ find_referencing_symbols(symbol_name, relative_path) [优先]
   目的: 找出所有依赖该符号的地方
   示例:
   - 修改函数签名前，找出所有调用者
   - 重构类前，找出所有使用者
   - 评估风险和工作量
```

#### 文档写入（保持传统方式）

```
保存计划文档？
└→ Write到[ROOT]/.claude/memory-bank/[branch]/plans/
   原因: RIPER memory-bank需要Git版本控制
   ❌ 不使用: write_memory (那是Serena知识库)
```

### EXECUTE Sub-Mode工具策略

在EXECUTE阶段，Serena编辑工具成为主力，大幅提升代码修改精确度。

#### 代码编辑决策树 ⭐ 核心优化

```
需要修改代码？
│
├─ 整体替换函数/类/方法
│  └→ replace_symbol_body(name_path, relative_path, new_body) [优先]
│     优势: 符号级替换，无需关心行号
│     示例: replace_symbol_body(
│             name_path="/GPULockMonitor/check_health",
│             relative_path="services/common/locks.py",
│             body="def check_health(self):\n    return True"
│           )
│     ↓ 失败/不适用
│     └→ Read + Edit (传统方式)
│
├─ 在符号后添加代码（如添加新方法到类）
│  └→ insert_after_symbol(name_path, relative_path, body) [优先]
│     优势: 相对定位，代码变动时仍有效
│     示例: insert_after_symbol(
│             name_path="/GPULockMonitor/check_health",
│             relative_path="services/common/locks.py",
│             body="\n    def new_method(self):\n        pass"
│           )
│     ↓ 失败/不适用
│     └→ Edit (需要精确行号)
│
├─ 在符号前添加代码（如添加import、文档字符串）
│  └→ insert_before_symbol(name_path, relative_path, body) [优先]
│     常见场景:
│     - 在文件第一个符号前添加import
│     - 在函数前添加装饰器
│     示例: insert_before_symbol(
│             name_path="/transcribe_audio",  # 文件第一个函数
│             relative_path="services/workers/faster_whisper_service/tasks.py",
│             body="from typing import Dict\n"
│           )
│     ↓ 失败/不适用
│     └→ Edit
│
├─ 重命名符号（跨文件）
│  └→ rename_symbol(name_path, relative_path, new_name) [优先]
│     优势: 自动处理所有引用，跨文件重构
│     示例: rename_symbol(
│             name_path="/gpu_lock",
│             relative_path="services/common/locks.py",
│             new_name="gpu_resource_lock"
│           )
│     ⚠️ 注意: 某些语言（如Java）可能需要签名
│     ↓ 失败/不适用
│     └→ 手动多次Edit + 全局搜索
│
└─ 少量行内修改（几行代码）
   └→ Edit [直接使用]
      场景: 修改变量值、调整参数、小改动
```

#### 编辑工具性能对比

| 操作 | ❌ 传统方式 | ✅ Serena方式 | 优势 |
|------|-----------|--------------|------|
| 替换整个函数 | Read定位行号 + Edit | replace_symbol_body | 无需行号，抗变动 |
| 在类中添加方法 | Read查找位置 + Edit | insert_after_symbol | 相对定位 |
| 添加import语句 | 手动找第一行 + Edit | insert_before_symbol | 自动定位 |
| 重命名函数 | Grep找所有位置 + 多次Edit | rename_symbol | 一次搞定 |

### 思考工具集成

#### think_about_task_adherence
**调用时机**:
- ⚠️ EXECUTE模式下，任何代码修改前 [强制]
- 实现复杂步骤的中途
- 发现计划不明确时

**目的**: 确保实现严格遵循计划，不偏离

#### think_about_whether_you_are_done
**调用时机**:
- ⚠️ 完成计划中的所有步骤后 [强制]
- 每个主要里程碑后
- 准备报告完成前

**目的**: 验证所有要求都已满足
```

#### 步骤 2.2: 修改Allowed Actions部分

**位置**:
- PLAN Sub-Mode: 第54-59行
- EXECUTE Sub-Mode: 第88-92行

**PLAN部分修改**:
```markdown
**Allowed Actions**:
- Create detailed technical specifications
- Define implementation steps (⭐ 使用find_referencing_symbols评估影响范围)
- Document design decisions
- Write to repository root `.claude/memory-bank/*/plans/` ONLY (use `git rev-parse --show-toplevel` to find root)
- Identify risks and mitigations (⭐ 基于Serena符号分析)
- ⭐ 调用think_about_task_adherence确保计划合理 [推荐]
```

**EXECUTE部分修改**:
```markdown
**Allowed Actions**:
- Implement EXACTLY what's in approved plan
- Write and modify project files (⭐ 优先使用Serena符号编辑工具)
- Execute build and test commands
- Follow plan steps sequentially
- ⭐ 每次代码修改前调用think_about_task_adherence [强制]
- ⭐ 所有步骤完成后调用think_about_whether_you_are_done [强制]
```

#### 步骤 2.3: 更新Tool Usage Restrictions部分

**位置**: 第171-175行

**修改**:
```markdown
### PLAN Sub-Mode Tool Usage
- ✅ Read: All files (⭐ 代码文件优先用get_symbols_overview + find_symbol)
- ✅ Serena符号工具: 分析代码结构和影响范围
- ✅ Write: ONLY to `[ROOT]/.claude/memory-bank/*/plans/` (get ROOT via `git rev-parse --show-toplevel`)
- ❌ Edit: Not for project files
- ❌ Bash: No execution commands

### EXECUTE Sub-Mode Tool Usage
- ✅ All tools available
- ⭐ Serena编辑工具优先: replace_symbol_body, insert_after/before_symbol, rename_symbol
- ⭐ 传统Edit工具: 用于少量行内修改或Serena不适用场景
- ⚠️ Must follow approved plan exactly
- ⚠️ Must call think_about_task_adherence before code changes
- ⚠️ Must call think_about_whether_you_are_done at completion
```

#### 步骤 2.4: 添加最佳实践部分

**位置**: 第207行（文档末尾，`Remember:`之前）

**添加内容**:

```markdown

## 📚 Serena Best Practices for Planning & Execution

### PLAN阶段实践

#### 实践1: 评估变更影响范围

```bash
# 任务: 计划修改gpu_lock装饰器的接口

# ✅ 推荐流程
1. find_symbol("gpu_lock", relative_path="services/common/locks.py", include_body=true)
   → 理解当前实现

2. find_referencing_symbols("gpu_lock", relative_path="services/common/locks.py")
   → 输出所有使用位置:
   - services/workers/faster_whisper_service/tasks.py: transcribe_audio
   - services/workers/pyannote_audio_service/tasks.py: separate_speakers
   - ... (共15处)

3. 在计划中记录:
   - 影响范围: 15个任务函数
   - 风险: 高（核心基础设施）
   - 测试要求: 所有15个任务的集成测试

4. think_about_task_adherence()
   → 确认计划覆盖所有影响点
```

#### 实践2: 记录关键符号路径

在计划文档中记录符号的name_path，便于EXECUTE阶段精确定位：

```markdown
## 实施步骤

### 步骤1: 修改gpu_lock装饰器签名
- 文件: `services/common/locks.py`
- 符号: `/gpu_lock` (顶层函数)
- name_path: `/gpu_lock`
- 操作: replace_symbol_body

### 步骤2: 更新所有使用位置
- 符号列表:
  1. `/transcribe_audio` in `services/workers/faster_whisper_service/tasks.py`
  2. `/separate_speakers` in `services/workers/pyannote_audio_service/tasks.py`
  ...
```

### EXECUTE阶段实践

#### 实践1: 符号级替换（推荐）

```bash
# 任务: 修改transcribe_audio函数实现

# ❌ 传统方式 (低效)
1. Read("services/workers/faster_whisper_service/tasks.py")
2. 找到transcribe_audio的起止行号（假设150-200行）
3. Edit(old_string="150-200行的原内容", new_string="新内容")
   问题: 如果文件之前被修改，行号会变化！

# ✅ Serena方式 (高效且鲁棒)
1. replace_symbol_body(
     name_path="/transcribe_audio",
     relative_path="services/workers/faster_whisper_service/tasks.py",
     body="""def transcribe_audio(self, context: dict) -> dict:
     '''新的实现'''
     # 新代码
     return context
     """
   )
   优势: 不依赖行号，即使文件被修改也能正确定位

2. think_about_task_adherence()
   → 确认修改符合计划

3. think_about_whether_you_are_done()
   → 检查是否还有其他步骤
```

#### 实践2: 添加新方法到类

```bash
# 任务: 给GPULockMonitor类添加新方法get_metrics()

# ✅ 推荐方式
1. 确定插入位置（计划中应指定）
   选项A: 在最后一个方法后
   选项B: 在特定方法后（如check_health后）

2. insert_after_symbol(
     name_path="/GPULockMonitor/check_health",
     relative_path="services/common/locks.py",
     body="""
    def get_metrics(self) -> dict:
        '''获取监控指标'''
        return {
            'active_locks': len(self.active_locks),
            'total_checks': self.check_count
        }
"""
   )

3. think_about_task_adherence()
```

#### 实践3: 添加import语句

```bash
# 任务: 添加新的import到文件

# ✅ 最佳方式
1. get_symbols_overview("target_file.py")
   → 找出第一个顶层符号（如第一个函数或类）

2. insert_before_symbol(
     name_path="/FirstSymbol",  # 文件中第一个符号
     relative_path="target_file.py",
     body="from typing import Optional, Dict\n"
   )

# ⚠️ 注意事项
- body需要包含换行符\n
- 如果文件开头已有import块，考虑手动Edit或先检查现有import
```

#### 实践4: 重命名重构

```bash
# 任务: 将gpu_lock重命名为acquire_gpu_lock

# ✅ Serena一步搞定（跨文件）
rename_symbol(
  name_path="/gpu_lock",
  relative_path="services/common/locks.py",
  new_name="acquire_gpu_lock"
)
# 自动更新:
# - 函数定义
# - 所有import语句
# - 所有调用位置

# ❌ 如果rename_symbol失败（某些语言不支持）
# 降级方案:
1. find_referencing_symbols("gpu_lock")
2. 手动Edit每个引用位置
```

### 常见陷阱和解决方案

| 陷阱 | 后果 | 解决方案 |
|------|------|---------|
| 使用Read+Edit修改函数 | 依赖行号，脆弱 | 用replace_symbol_body |
| 忘记调用think_about_task_adherence | 偏离计划 | 设置检查点 |
| 用Edit添加类方法 | 位置难定位 | 用insert_after_symbol |
| 手动多文件重命名 | 容易遗漏 | 用rename_symbol |
| 直接Read大文件查找符号 | 浪费token | 先get_symbols_overview |
```

### 阶段3: Review代理增强 (P1)

**文件**: `.claude/agents/review.md`

#### 步骤 3.1: 添加工具选择策略部分

**位置**: 第14行（`---`之后，`# RIPER: REVIEW MODE`之前）

**添加内容**:

```markdown
## 🔧 Tool Selection Strategy for Review

### 代码审查中的Serena工具

在REVIEW模式下，Serena工具用于理解实现和分析变更，不进行任何修改。

#### 理解实现代码

```
需要理解实现的代码？
└→ 遵循RESEARCH阶段的决策树:
   1. get_symbols_overview (快速了解结构)
   2. find_symbol (查看具体实现)
   3. 对比计划中的要求
```

#### 验证影响范围

```
验证变更是否影响其他部分？
└→ find_referencing_symbols(modified_symbol) [优先]
   目的: 确认所有依赖者都已考虑/测试
   示例: 如果修改了gpu_lock，检查所有引用位置是否都正常
```

#### 符号级对比

```
对比实现前后差异？
1. 从Git获取修改前的代码
2. find_symbol获取修改后的符号
3. 对比符号级差异（更精确）
```

### 思考工具

#### think_about_collected_information
**调用时机**:
- 收集实现信息后
- 分析测试结果后
- 准备写审查报告前

**目的**: 确认是否掌握足够信息进行判断

#### think_about_whether_you_are_done
**调用时机**:
- 审查完成所有检查项后
- 准备给出最终裁决前

**目的**: 验证没有遗漏的检查项
```

#### 步骤 3.2: 修改Responsibilities部分

**位置**: 第33-37行

**修改**:
```markdown
- **Verify Plan Compliance**: Ensure EVERY step was implemented exactly (⭐ 使用Serena符号工具理解实现)
- **Run All Tests**: Execute comprehensive test suites
- **Check Code Quality**: Lint, format, type-check
- **Identify Deviations**: Flag ANY divergence from plan (⭐ 符号级对比)
- **Document Issues**: Create detailed report of findings
- ⭐ 调用think工具确保审查全面 [推荐]
```

#### 步骤 3.3: 添加最佳实践部分

**位置**: 第218行（文档末尾，`Remember:`之前）

**添加内容**:

```markdown

## 📚 Serena Best Practices for Review

### 实践1: 验证符号级修改

```bash
# 任务: 验证transcribe_audio函数是否按计划修改

# ✅ 高效流程
1. 从计划中读取要求:
   "修改transcribe_audio函数以支持batch处理"

2. find_symbol(
     name_path="/transcribe_audio",
     relative_path="services/workers/faster_whisper_service/tasks.py",
     include_body=true
   )
   → 获取当前实现

3. 对比计划要求:
   ✓ 是否添加了batch_size参数
   ✓ 是否实现了循环处理
   ✓ 是否更新了返回值

4. find_referencing_symbols("transcribe_audio")
   → 验证所有调用者是否兼容新接口

5. think_about_collected_information()
   → 确认审查是否全面
```

### 实践2: 检测未授权修改

```bash
# 任务: 确保没有计划外的修改

# ✅ 使用符号工具
1. git diff获取修改的文件列表

2. 对于每个修改的文件:
   get_symbols_overview(file_path)
   → 获取所有符号

3. 对比计划中列出的符号:
   - 计划中的符号是否都已修改 ✓
   - 是否有计划外的符号被修改 ⚠️

4. 对于计划外修改:
   find_symbol(unexpected_symbol, include_body=true)
   → 分析是否合理
```

### 实践3: 影响范围验证

```bash
# 任务: 验证修改gpu_lock的影响已全部处理

# ✅ 完整验证流程
1. find_referencing_symbols("gpu_lock", relative_path="services/common/locks.py")
   → 输出: 15个引用位置

2. 对比计划中的"影响范围"部分:
   ✓ 计划列出了15个位置吗？
   ⚠️ 如果计划只列了10个，标记为CRITICAL偏离

3. 对于每个引用位置（抽样或全部）:
   find_symbol(referencing_symbol, include_body=true)
   → 验证是否正确适配新接口

4. think_about_whether_you_are_done()
   → 确认所有影响已验证
```
```

## 4. 测试和验证方案

### 4.1 单元测试（不需要实际测试代码）

验证方法：实际使用修改后的代理执行RIPER工作流

#### 测试用例1: RESEARCH模式工具选择

**输入**: `/riper:research 理解services/common/locks.py中的GPU锁系统`

**预期行为**:
1. ✅ 优先使用 `get_symbols_overview("services/common/locks.py")`
2. ✅ 使用 `find_symbol("gpu_lock", include_body=true)`
3. ✅ 使用 `find_referencing_symbols("gpu_lock")`
4. ✅ 调用 `think_about_collected_information()`
5. ❌ 不应直接 `Read("services/common/locks.py")` 作为第一步

**验证标准**: 检查对话历史中的工具调用顺序

#### 测试用例2: EXECUTE模式符号编辑

**输入**: `/riper:execute` （假设有修改函数的计划）

**预期行为**:
1. ✅ 修改整个函数时使用 `replace_symbol_body`
2. ✅ 添加方法时使用 `insert_after_symbol`
3. ✅ 每次修改前调用 `think_about_task_adherence()`
4. ✅ 完成后调用 `think_about_whether_you_are_done()`

**验证标准**: 工具调用序列符合最佳实践

#### 测试用例3: Fallback机制

**输入**: 尝试对非Python文件使用符号工具

**预期行为**:
1. ✅ Serena工具失败或不适用
2. ✅ 自动降级到传统工具（Read、Grep等）
3. ✅ 不应报错或阻塞

**验证标准**: 工作流能够继续，使用了传统工具

### 4.2 集成测试

#### 完整RIPER工作流测试

**场景**: 从头到尾执行一个小特性的RIPER流程

**步骤**:
1. `/riper:research` - 研究现有代码
2. `/riper:plan` - 创建技术规范
3. 检查生成的计划是否包含符号path信息
4. `/riper:execute` - 执行计划
5. 验证是否使用了Serena编辑工具
6. `/riper:review` - 审查实现
7. 验证审查报告质量

**成功标准**:
- ✅ 每个阶段都优先使用了Serena工具
- ✅ 思考工具在关键点被调用
- ✅ 计划文档保存到正确位置（memory-bank/）
- ✅ 没有因Serena工具而导致的错误

### 4.3 性能基准测试

#### Token消耗对比

**测试方法**: 相同任务，对比修改前后的token使用

**场景**: 理解一个500行的Python文件

| 方法 | 估计Token消耗 | 时间 |
|------|--------------|------|
| 修改前（直接Read全文） | ~2000 tokens | 基准 |
| 修改后（Serena符号工具） | ~125 tokens | -94% |

**测量方法**: 从对话历史中统计实际token使用

#### 速度对比

**场景**: 查找并修改特定函数

| 方法 | 工具调用次数 | 相对速度 |
|------|-------------|---------|
| 修改前 | Read + Grep + Read + Edit ≈ 4次 | 基准 |
| 修改后 | find_symbol + replace_symbol_body ≈ 2次 | 2x快 |

### 4.4 质量验证

#### 检查清单

**文档质量**:
- ✅ 所有代理都有"Tool Selection Strategy"部分
- ✅ 所有代理都有"Quality Checkpoints"部分
- ✅ 所有代理都有"Best Practices"部分
- ✅ 示例代码格式正确，可执行
- ✅ 决策树逻辑清晰，易于遵循

**内容一致性**:
- ✅ 三个代理中的Serena工具使用逻辑一致
- ✅ Memory使用指南在所有代理中一致
- ✅ 术语统一（如name_path、relative_path）

**向后兼容性**:
- ✅ 传统工具仍然可用
- ✅ 现有工作流不受影响
- ✅ 可以选择不使用Serena工具

## 5. 成功标准

### 5.1 必须达成（P0）

- ✅ **工具自动选择**: 代理在代码操作时优先选择Serena工具，无需用户明确指定
- ✅ **Fallback机制**: Serena工具失败时自动降级到传统工具，不阻塞工作流
- ✅ **文档完整性**: 所有三个代理都包含完整的工具选择策略和最佳实践
- ✅ **检索速度提升**: 在理解代码文件时，token消耗减少至少50%
- ✅ **思考工具集成**: 关键检查点都调用了相应的think工具

### 5.2 期望达成（P1）

- ✅ **符号编辑优先**: EXECUTE模式下至少80%的代码修改使用Serena编辑工具
- ✅ **Memory协作清晰**: Serena memory与RIPER memory-bank的用途区分明确
- ✅ **示例丰富**: 每个主要场景都有实际可执行的示例
- ✅ **性能可测量**: 能够从对话历史中量化速度和token提升

### 5.3 质量门槛

- ✅ **无破坏性变更**: 现有RIPER工作流完全兼容
- ✅ **文档可读性**: 技术人员能够在5分钟内理解决策树
- ✅ **错误处理**: Serena工具失败时有清晰的降级路径

## 6. 风险和缓解措施

### 6.1 技术风险

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|-------|------|---------|
| Serena MCP在某些环境不可用 | 中 | 中 | 保留传统工具作为fallback，文档明确说明 |
| 符号工具对某些语言支持不佳 | 低 | 低 | 文档中明确适用范围，非适用场景用传统工具 |
| 用户学习曲线陡峭 | 中 | 低 | 提供丰富示例和决策树，渐进引导 |
| 过度依赖Serena导致简单任务复杂化 | 低 | 低 | 决策树中明确"少量行内修改用Edit" |

### 6.2 实施风险

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|-------|------|---------|
| 文档过长影响代理性能 | 低 | 中 | 保持内容结构化，使用表格和代码块 |
| 示例代码有错误 | 中 | 中 | 实施前验证所有示例，测试阶段发现问题 |
| 三个代理内容不一致 | 中 | 高 | 使用统一术语表，交叉验证内容 |

### 6.3 采用风险

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|-------|------|---------|
| 用户忽略新指导，仍用传统方式 | 高 | 中 | 这是可接受的！向后兼容是设计目标 |
| Serena工具频繁失败导致体验下降 | 低 | 高 | 监控失败率，快速降级，收集反馈改进 |
| Memory管理混乱（两套系统） | 中 | 低 | 清晰文档化用途区分，提供协作示例 |

## 7. 实施时间表

### 阶段划分

| 阶段 | 任务 | 预计时间 | 依赖 |
|------|------|---------|------|
| **阶段1** | 修改research-innovate.md | 45分钟 | 无 |
| **阶段2** | 修改plan-execute.md | 60分钟 | 阶段1完成 |
| **阶段3** | 修改review.md | 45分钟 | 阶段2完成 |
| **测试** | 完整RIPER工作流测试 | 30分钟 | 所有阶段完成 |
| **调整** | 根据测试反馈微调 | 30分钟 | 测试完成 |

**总计**: 约3.5小时

### 里程碑

1. ✅ **M1**: research-innovate.md修改完成并初步测试
2. ✅ **M2**: 所有三个代理修改完成
3. ✅ **M3**: 完整工作流测试通过
4. ✅ **M4**: 性能提升可测量并达标

## 8. 回滚计划

### 回滚触发条件

- Serena工具导致的错误率超过20%
- 用户反馈严重负面
- 发现重大设计缺陷

### 回滚步骤

1. 从Git恢复 `.claude/agents/` 下的三个文件到修改前版本
2. 通知用户回滚原因
3. 保留修改内容到单独分支用于后续改进

### 回滚成本

- ⏱️ 时间成本: 5分钟（简单的Git还原）
- 📊 数据损失: 无（只是指导文档，无数据）
- 🔄 恢复时间: 立即

## 9. 后续改进方向

### 短期（1-2周内）

1. **性能监控仪表板**
   - 统计Serena工具vs传统工具的使用比例
   - 测量实际token节省
   - 收集失败案例

2. **示例库扩展**
   - 添加更多真实场景示例
   - 针对YiVideo特定模式的最佳实践
   - 常见错误和解决方案FAQ

### 中期（1个月内）

3. **Serena Memory知识库建设**
   - 预填充项目架构memory
   - 创建GPU锁系统memory
   - 创建工作流引擎memory

4. **自动化检查**
   - 在EXECUTE模式下自动检查是否调用了think工具
   - 在RESEARCH模式下检测"直接Read代码文件"的反模式

### 长期（持续优化）

5. **多语言支持**
   - 扩展Serena工具到JavaScript、TypeScript
   - 针对不同语言的最佳实践

6. **智能推荐**
   - 基于上下文自动推荐最适合的Serena工具
   - 学习用户习惯优化建议

## 10. 附录

### 10.1 术语表

| 术语 | 定义 |
|------|------|
| **name_path** | Serena符号路径，如 `/Class/method` 或 `function` |
| **relative_path** | 相对于项目根目录的文件路径 |
| **符号** | 代码中的可识别元素（类、函数、变量等） |
| **符号级编辑** | 基于符号而非行号的代码修改 |
| **think工具** | Serena提供的三个质量检查工具 |
| **fallback** | 降级机制，Serena失败时使用传统工具 |

### 10.2 参考文件

**需要修改的文件**:
- `.claude/agents/research-innovate.md`
- `.claude/agents/plan-execute.md`
- `.claude/agents/review.md`

**参考资料**:
- Serena MCP工具文档（系统提示中）
- RIPER配置: `.claude/riper-config.json`
- 项目信息: `.claude/project-info.md`

### 10.3 检查清单

**实施前检查**:
- [ ] 备份三个代理文件
- [ ] 确认Git工作区干净
- [ ] 阅读完整技术规范

**实施中检查**:
- [ ] 每个文件修改后保存
- [ ] 验证Markdown格式正确
- [ ] 检查代码块语法高亮

**实施后检查**:
- [ ] 运行至少一个完整RIPER工作流
- [ ] 验证Serena工具被优先使用
- [ ] 验证fallback机制工作
- [ ] 检查文档可读性

---

## 计划批准

**创建日期**: 2025-10-21
**计划状态**: ⏳ 待批准
**预计开始**: 批准后立即
**预计完成**: 批准后3.5小时

**批准要求**:
1. 用户确认技术方案符合预期
2. 确认渐进式实施策略可接受
3. 确认测试方案充分

**批准后下一步**:
执行 `/riper:execute` 开始实施本计划

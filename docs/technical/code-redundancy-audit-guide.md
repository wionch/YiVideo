# 代码冗余审计操作指南

本指南提供系统化的代码冗余审计流程、工具使用方法和最佳实践，帮助团队识别、评估和消除 YiVideo 项目中的重复代码。

## 目录

- [1. 审计工具使用指南](#1-审计工具使用指南)
- [2. 审计案例](#2-审计案例)
- [3. 审计流程说明](#3-审计流程说明)
- [4. 审计清单模板](#4-审计清单模板)
- [5. 优先级评估标准](#5-优先级评估标准)

---

## 1. 审计工具使用指南

### 1.1 工具概览

YiVideo 项目推荐使用以下工具进行代码冗余审计：

| 工具 | 用途 | 优势 | 适用场景 |
|------|------|------|---------|
| **ripgrep (rg)** | 快速文本搜索 | 速度快、支持正则、递归搜索 | 查找重复模式、统计代码出现次数 |
| **grep** | 传统文本搜索 | 通用性强、系统自带 | 简单模式匹配 |
| **serena (MCP)** | 语义级代码分析 | 理解代码结构、符号级导航 | 查找类/函数定义、分析依赖关系 |
| **ast-grep** | AST 级别搜索 | 语法感知、精确匹配 | 查找特定代码结构模式 |
| **Python AST** | 抽象语法树分析 | 深度代码理解 | 复杂代码模式分析 |

### 1.2 ripgrep (rg) 使用指南

#### 基础搜索

```bash
# 搜索包含特定模式的文件
rg "pattern" services/

# 搜索并显示行号
rg -n "pattern" services/

# 仅列出包含模式的文件名
rg -l "pattern" services/

# 统计每个文件中的匹配次数
rg -c "pattern" services/
```

#### 高级搜索技巧

```bash
# 使用正则表达式搜索类定义
rg -n "^class\s+\w+.*:" services/workers/

# 搜索函数定义
rg -n "^def\s+\w+\(" services/

# 搜索特定模式并显示上下文（前后各5行）
rg -A 5 -B 5 "workflow_context.stages" services/

# 限制文件类型（仅搜索 Python 文件）
rg --type py "except Exception as e:" services/

# 排除特定目录
rg "pattern" services/ --glob '!**/tests/**'
```

#### 冗余代码检测示例

```bash
# 1. 查找重复的配置加载模式
rg -n "class.*ConfigLoader" services/

# 2. 统计状态管理模式出现次数
rg -c "workflow_context.stages\[stage_name\] = StageExecution" services/workers/*/app/tasks.py

# 3. 查找宽泛的异常捕获
rg -n "except Exception as e:" services/ --type py

# 4. 查找重复的导入语句
rg -n "^from services.common" services/workers/ --type py | sort | uniq -c | sort -rn

# 5. 查找魔法数字和硬编码值
rg -n "\b(timeout|poll_interval)\s*=\s*\d+" services/workers/ --type py
```

### 1.3 grep 使用指南

```bash
# 递归搜索目录
grep -r "pattern" services/

# 显示行号和文件名
grep -rn "pattern" services/

# 统计匹配行数
grep -rc "pattern" services/

# 使用扩展正则表达式
grep -E "class (ConfigLoader|ModelManager)" services/ -r

# 反向匹配（不包含模式的行）
grep -v "pattern" file.py
```

### 1.4 serena (MCP) 使用指南

Serena 是基于 MCP 的语义代码分析工具，提供符号级导航和代码理解能力。

#### 查找符号定义

```python
# 使用 serena 查找类定义
mcp__serena__find_symbol(
    name_path_pattern="ConfigLoader",
    include_body=False,
    depth=1  # 包含方法列表
)

# 查找特定方法
mcp__serena__find_symbol(
    name_path_pattern="WorkflowContext/__init__",
    include_body=True
)
```

#### 查找引用关系

```python
# 查找所有引用某个类的位置
mcp__serena__find_referencing_symbols(
    name_path="ConfigLoader",
    relative_path="services/workers/audio_separator_service/app/config.py"
)
```

#### 搜索代码模式

```python
# 搜索特定模式
mcp__serena__search_for_pattern(
    substring_pattern="workflow_context\.stages\[.*\] = StageExecution",
    restrict_search_to_code_files=True,
    context_lines_before=2,
    context_lines_after=2
)
```

### 1.5 识别重复代码的模式

#### 模式1：重复的类定义

**检测命令**：
```bash
rg -n "^class\s+(\w+)" services/ --type py | \
  awk -F: '{print $3}' | sort | uniq -d
```

**示例输出**：
```
class ConfigLoader
class ModelManager
```

#### 模式2：重复的函数逻辑

**检测命令**：
```bash
# 查找相似的函数签名
rg -n "^def\s+(get_config|load_config|init_config)" services/ --type py
```

#### 模式3：重复的状态管理代码

**检测命令**：
```bash
# 统计状态管理模式
rg -c "workflow_context.stages\[stage_name\].status = " services/workers/*/app/tasks.py
```

**分析输出**：
```
services/workers/audio_separator_service/app/tasks.py:6
services/workers/faster_whisper_service/app/tasks.py:7
services/workers/ffmpeg_service/app/tasks.py:44
...
```

#### 模式4：重复的异常处理

**检测命令**：
```bash
# 查找宽泛的异常捕获
rg -l "except Exception as e:" services/ --type py | wc -l
```

### 1.6 自动化检测脚本示例

创建一个简单的审计脚本 `scripts/audit_redundancy.sh`：

```bash
#!/bin/bash
# 代码冗余快速审计脚本

echo "=== YiVideo 代码冗余审计报告 ==="
echo "生成时间: $(date)"
echo ""

echo "1. 重复的类定义检测"
echo "---"
rg -n "^class\s+ConfigLoader" services/ --type py
echo ""

echo "2. 状态管理模式统计"
echo "---"
rg -c "workflow_context.stages\[stage_name\]" services/workers/*/app/tasks.py
echo ""

echo "3. 宽泛异常捕获统计"
echo "---"
rg -c "except Exception as e:" services/ --type py | grep -v ":0$"
echo ""

echo "4. GPU 锁参数一致性检查"
echo "---"
rg -n "@gpu_lock\(" services/workers/ --type py
echo ""

echo "=== 审计完成 ==="
```

---

## 2. 审计案例

本章节提供实际的代码冗余审计案例，展示如何识别、分析和评估重复代码。

### 2.1 案例1：audio_separator 配置加载器重复

#### 问题描述

`audio_separator_service` 实现了独立的 `ConfigLoader` 类，与 `services.common.config_loader` 模块的功能重复。

#### 检测方法

```bash
# 1. 查找所有 ConfigLoader 类定义
rg -n "class ConfigLoader" services/

# 输出：
# services/workers/audio_separator_service/app/config.py:284:class ConfigLoader:

# 2. 查找 common 模块的配置加载函数
rg -n "def get_config" services/common/config_loader.py

# 输出：
# services/common/config_loader.py:48:def get_config() -> Dict[str, Any]:
# services/common/config_loader.py:391:def get_config_realtime() -> Dict[str, Any]:
```

#### 代码对比

**统一配置加载器** (`services/common/config_loader.py:48-61`)：
```python
def get_config() -> Dict[str, Any]:
    """
    获取全局配置（缓存版本）
    """
    global _config_cache
    if _config_cache is None:
        _config_cache = _load_config()
    return _config_cache
```

**独立配置加载器** (`services/workers/audio_separator_service/app/config.py:284-361`)：
```python
class ConfigLoader:
    """配置加载器"""
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or os.getenv(
            'CONFIG_PATH',
            '/app/config.yml'
        )
        self._config: Optional[Dict] = None

    def load(self) -> Dict:
        """加载配置文件"""
        if self._config is None:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self._config = yaml.safe_load(f)
        return self._config

    # ... 约80行重复的配置加载逻辑
```

#### 冗余分析

| 维度 | 统一加载器 | 独立加载器 | 重复程度 |
|------|-----------|-----------|---------|
| **功能** | 加载 YAML 配置 | 加载 YAML 配置 | 100% 重复 |
| **缓存机制** | 全局缓存 | 实例缓存 | 实现方式不同，功能相同 |
| **代码行数** | ~14行 | ~80行 | 独立实现多66行 |
| **依赖** | 无额外依赖 | 无额外依赖 | 相同 |
| **维护成本** | 单一入口 | 需要同步维护 | 独立实现增加维护负担 |

#### 影响评估

**冗余代码量**：
- 独立实现：~80行
- 可复用代码：~14行
- **冗余代码：~66行**

**维护成本**：
- 配置格式变更需要修改2处
- Bug修复需要在2处同步
- 新功能（如配置热重载）需要重复实现

**违反的设计原则**：
- ❌ **DRY (Don't Repeat Yourself)**：配置加载逻辑重复实现
- ❌ **单一职责**：配置加载应由统一模块负责

#### 重构建议

**优先级**：P1（高优先级）

**重构方案**：
1. 移除 `audio_separator_service` 中的 `ConfigLoader` 类
2. 导入并使用 `services.common.config_loader.get_config()`
3. 如有特殊配置需求，通过配置文件扩展而非代码重复

**预期收益**：
- 减少 ~66行 冗余代码
- 统一配置加载逻辑，降低维护成本
- 提高配置管理的一致性

#### 验证命令

```bash
# 重构后验证：确认不再存在独立的 ConfigLoader
rg -n "class ConfigLoader" services/workers/audio_separator_service/

# 应无输出，或仅在注释中提及

# 验证使用统一加载器
rg -n "from services.common.config_loader import get_config" \
  services/workers/audio_separator_service/
```

### 2.2 案例2：工作流状态管理模式重复

#### 问题描述

所有 Celery 工作器服务的任务文件中都包含重复的工作流状态管理代码，包括状态初始化、成功/失败处理、时长记录等逻辑。

#### 检测方法

```bash
# 1. 统计状态管理模式出现次数
rg -c "workflow_context.stages\[stage_name\] = StageExecution" \
  services/workers/*/app/tasks.py

# 输出：
# services/workers/audio_separator_service/app/tasks.py:3
# services/workers/faster_whisper_service/app/tasks.py:1
# services/workers/ffmpeg_service/app/tasks.py:4
# services/workers/indextts_service/app/tasks.py:3
# services/workers/paddleocr_service/app/tasks.py:4
# services/workers/wservice/app/tasks.py:6
# services/workers/pyannote_audio_service/app/tasks.py:3

# 2. 查看典型的状态管理代码模式
rg -A 10 -B 2 "workflow_context.stages\[stage_name\] = StageExecution" \
  services/workers/faster_whisper_service/app/tasks.py | head -30
```

#### 重复模式识别

**典型的状态管理样板代码**（每个任务都包含）：

```python
@celery_app.task(bind=True, name='service.task_name')
def task_name(self, context: dict) -> dict:
    start_time = time.time()
    workflow_context = WorkflowContext(**context)
    stage_name = self.name

    # ⚠️ 重复模式1：初始化IN_PROGRESS状态
    workflow_context.stages[stage_name] = StageExecution(status="IN_PROGRESS")
    state_manager.update_workflow_state(workflow_context)

    try:
        # 业务逻辑...

        # ⚠️ 重复模式2：设置SUCCESS状态
        workflow_context.stages[stage_name].status = 'SUCCESS'
        workflow_context.stages[stage_name].output = output_data

    except Exception as e:
        # ⚠️ 重复模式3：设置FAILED状态
        workflow_context.stages[stage_name].status = 'FAILED'
        workflow_context.stages[stage_name].error = str(e)

    finally:
        # ⚠️ 重复模式4：更新时长和最终状态
        workflow_context.stages[stage_name].duration = time.time() - start_time
        state_manager.update_workflow_state(workflow_context)

    return workflow_context.model_dump()
```

#### 冗余统计

| 服务 | 文件 | 状态管理操作次数 |
|------|------|----------------|
| audio_separator | services/workers/audio_separator_service/app/tasks.py | 3 |
| faster_whisper | services/workers/faster_whisper_service/app/tasks.py | 1 |
| ffmpeg | services/workers/ffmpeg_service/app/tasks.py | 4 |
| indextts | services/workers/indextts_service/app/tasks.py | 3 |
| paddleocr | services/workers/paddleocr_service/app/tasks.py | 4 |
| wservice | services/workers/wservice/app/tasks.py | 6 |
| pyannote_audio | services/workers/pyannote_audio_service/app/tasks.py | 3 |
| **总计** | **7个服务** | **24处** |

**估算冗余代码量**：
- 每处状态管理样板：~12行
- 总计：24处 × 12行 = **~288行冗余代码**

#### 影响评估

**维护成本**：
- 状态管理逻辑变更需要修改24处
- 新增状态（如 RETRYING）需要在24处同步
- 错误处理增强需要重复实现24次

**一致性风险**：
- 手动编写容易遗漏状态更新
- 不同服务的状态管理可能不一致
- 难以统一添加监控埋点

**违反的设计原则**：
- ❌ **DRY**：状态管理逻辑在24处重复
- ❌ **单一职责**：业务逻辑与状态管理耦合

#### 重构建议

**优先级**：P0（最高优先级）

**重构方案**：创建统一的 `WorkflowTask` 基类

```python
# services/common/workflow_task.py
from celery import Task

class WorkflowTask(Task):
    """统一的工作流任务基类"""

    def __call__(self, context: dict) -> dict:
        start_time = time.time()
        workflow_context = WorkflowContext(**context)
        stage_name = self.name

        # 自动初始化IN_PROGRESS
        workflow_context.stages[stage_name] = StageExecution(status="IN_PROGRESS")
        state_manager.update_workflow_state(workflow_context)

        try:
            # 调用子类实现的业务逻辑
            output = self.execute(workflow_context)

            # 自动设置SUCCESS
            workflow_context.stages[stage_name].status = 'SUCCESS'
            workflow_context.stages[stage_name].output = output
        except Exception as e:
            # 自动设置FAILED
            workflow_context.stages[stage_name].status = 'FAILED'
            workflow_context.stages[stage_name].error = str(e)
            raise
        finally:
            # 自动更新时长和状态
            workflow_context.stages[stage_name].duration = time.time() - start_time
            state_manager.update_workflow_state(workflow_context)

        return workflow_context.model_dump()

    def execute(self, workflow_context: WorkflowContext) -> dict:
        """子类必须实现的业务逻辑方法"""
        raise NotImplementedError
```

**使用示例**（重构后）：

```python
@celery_app.task(bind=True, base=WorkflowTask, name='faster_whisper.transcribe')
class TranscribeTask(WorkflowTask):
    def execute(self, workflow_context: WorkflowContext) -> dict:
        """仅需实现业务逻辑，状态管理自动处理"""
        audio_path = workflow_context.get_input('audio_path')
        segments = model.transcribe(audio_path)
        return process_segments(segments)
```

**预期收益**：
- 消除 ~288行 冗余代码
- 状态管理逻辑100%一致
- 修改一次全局生效
- 便于统一添加监控、重试等功能

#### 验证命令

```bash
# 重构后验证：确认使用基类
rg -n "class.*WorkflowTask" services/workers/*/app/tasks.py

# 验证不再有手动状态管理
rg -c "workflow_context.stages\[stage_name\].status = " \
  services/workers/*/app/tasks.py

# 应全部为0或大幅减少
```

---

## 3. 审计流程说明

本章节描述完整的代码冗余审计流程，包括准备、扫描、分析、评估和报告五个阶段。

### 3.1 审计流程概览

```
┌─────────────┐
│  1. 准备阶段  │  确定审计范围、目标和资源
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  2. 扫描阶段  │  使用工具自动检测重复代码
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  3. 分析阶段  │  人工分析检测结果，识别真实冗余
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  4. 评估阶段  │  评估影响和优先级
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  5. 报告阶段  │  生成审计报告和重构建议
└─────────────┘
```

### 3.2 阶段1：准备

#### 目标

- 明确审计范围和目标
- 准备审计工具和环境
- 确定审计团队和时间表

#### 具体步骤

**步骤1.1：确定审计范围**

```bash
# 列出所有服务目录
ls -la services/workers/

# 统计代码行数
find services/ -name "*.py" | xargs wc -l | tail -1

# 确定重点审计的模块
# - services/workers/*/app/tasks.py（工作流任务）
# - services/common/（公共模块）
# - services/api_gateway/（API网关）
```

**步骤1.2：准备审计工具**

```bash
# 确认ripgrep已安装
rg --version

# 确认Python环境
python --version

# 准备审计脚本目录
mkdir -p scripts/audit/
```

**步骤1.3：创建审计清单**

基于第4章的模板创建本次审计的清单文件：

```bash
cp docs/technical/code-redundancy-audit-guide.md \
   docs/audit/audit-$(date +%Y%m%d).md
```

### 3.3 阶段2：扫描

#### 目标

- 使用自动化工具快速识别潜在的重复代码
- 生成初步的冗余代码候选列表

#### 具体步骤

**步骤2.1：扫描重复的类定义**

```bash
# 查找所有类定义
rg -n "^class\s+(\w+)" services/ --type py > audit_classes.txt

# 查找重复的类名
awk -F: '{print $3}' audit_classes.txt | sort | uniq -c | sort -rn | grep -v "^\s*1 "
```

**步骤2.2：扫描重复的函数定义**

```bash
# 查找所有函数定义
rg -n "^def\s+(\w+)\(" services/ --type py > audit_functions.txt

# 统计函数名频率
awk -F: '{print $3}' audit_functions.txt | \
  sed 's/def \([a-zA-Z_]*\).*/\1/' | \
  sort | uniq -c | sort -rn | head -20
```

**步骤2.3：扫描重复的代码模式**

```bash
# 状态管理模式
rg -c "workflow_context.stages\[stage_name\]" services/workers/*/app/tasks.py \
  > audit_state_management.txt

# 异常处理模式
rg -c "except Exception as e:" services/ --type py \
  > audit_exception_handling.txt

# 配置加载模式
rg -l "ConfigLoader\|get_config\|load_config" services/ --type py \
  > audit_config_loading.txt
```

**步骤2.4：扫描魔法数字和硬编码值**

```bash
# GPU锁参数
rg -n "@gpu_lock\(" services/workers/ --type py \
  > audit_gpu_lock_params.txt

# 超时配置
rg -n "timeout\s*=\s*\d+" services/ --type py \
  > audit_timeout_values.txt
```

### 3.4 阶段3：分析

#### 目标

- 人工审查扫描结果
- 区分真实冗余和合理重复
- 识别重构机会

#### 具体步骤

**步骤3.1：分类扫描结果**

将扫描结果分为以下类别：

| 类别 | 描述 | 示例 |
|------|------|------|
| **真实冗余** | 完全重复的代码，应该消除 | 独立的ConfigLoader类 |
| **模式重复** | 相似的代码模式，可以抽象 | 状态管理样板代码 |
| **合理重复** | 虽然相似但有不同用途 | 不同服务的业务逻辑 |
| **误报** | 工具误判的重复 | 同名但功能不同的函数 |

**步骤3.2：代码对比分析**

对于每个候选冗余，执行以下分析：

```bash
# 1. 查看完整代码
rg -A 20 "class ConfigLoader" services/workers/audio_separator_service/app/config.py

# 2. 对比相似代码
diff -u <(rg -A 10 "def get_config" services/common/config_loader.py) \
        <(rg -A 10 "def load" services/workers/audio_separator_service/app/config.py)

# 3. 查找引用关系（使用serena）
# 确认是否可以安全重构
```

**步骤3.3：记录分析结果**

为每个真实冗余填写分析表：

| 字段 | 内容 |
|------|------|
| 冗余ID | REDUNDANCY-001 |
| 类型 | 类定义重复 |
| 位置 | services/workers/audio_separator_service/app/config.py:284 |
| 冗余代码量 | ~80行 |
| 影响范围 | 仅audio_separator_service |
| 重构难度 | 低 |

### 3.5 阶段4：评估

#### 目标

- 评估每个冗余的影响和优先级
- 制定重构计划

#### 具体步骤

**步骤4.1：影响评估**

使用以下维度评估影响：

```
影响分数 = (冗余代码量 × 0.3) + (维护成本 × 0.4) + (一致性风险 × 0.3)

其中：
- 冗余代码量：0-10分（每10行代码1分，最高10分）
- 维护成本：0-10分（需要同步修改的位置数，每处1分）
- 一致性风险：0-10分（主观评估，逻辑不一致的风险）
```

**步骤4.2：优先级评估**

根据影响分数和重构难度确定优先级（详见第5章）：

| 优先级 | 条件 | 处理时限 |
|--------|------|---------|
| P0 | 影响分数≥8 且 重构难度≤中 | 立即处理 |
| P1 | 影响分数≥6 或 重构难度=低 | 本迭代 |
| P2 | 影响分数≥4 | 下一迭代 |
| P3 | 影响分数<4 | 待定 |

**步骤4.3：制定重构计划**

为每个P0/P1级别的冗余创建重构任务：

```markdown
## 重构任务：消除audio_separator ConfigLoader冗余

- 优先级：P1
- 预计工时：2小时
- 依赖：无
- 步骤：
  1. 修改audio_separator_service使用common.config_loader
  2. 移除独立的ConfigLoader类
  3. 运行测试验证
  4. 更新文档
```

### 3.6 阶段5：报告

#### 目标

- 生成审计报告
- 提交重构建议
- 跟踪改进进度

#### 具体步骤

**步骤5.1：生成审计报告**

报告应包含以下章节：

1. **执行摘要**
   - 审计范围和时间
   - 发现的冗余总数
   - 估算的冗余代码量
   - 关键发现和建议

2. **详细发现**
   - 每个冗余的详细分析
   - 代码示例和对比
   - 影响评估

3. **重构建议**
   - 按优先级排序的重构任务
   - 预期收益
   - 实施计划

4. **附录**
   - 审计清单
   - 扫描脚本
   - 验证命令

**步骤5.2：提交OpenSpec变更提案**

对于需要重构的冗余，创建独立的OpenSpec提案：

```bash
# 创建重构提案
openspec proposal refactor-config-loader-redundancy

# 编写proposal.md，包含：
# - 为什么：基于审计发现
# - 调研：引用审计报告
# - 变更内容：具体重构步骤
# - 影响：受影响的文件和服务
```

**步骤5.3：跟踪改进进度**

维护冗余代码清单（见第4章），定期更新状态：

```bash
# 每周更新清单
# 标记已完成的重构
# 添加新发现的冗余
# 重新评估优先级
```




---

## 4. 审计清单模板

本章节提供可复用的代码冗余审计清单模板,用于记录、跟踪和管理发现的冗余代码问题。

### 4.1 冗余代码清单表格

使用以下 Markdown 表格模板记录审计发现：

```markdown
## YiVideo 代码冗余审计清单

**审计日期**：YYYY-MM-DD
**审计人员**：[姓名]
**审计范围**：[服务/模块名称]

| ID | 冗余类型 | 位置 | 冗余代码量 | 影响范围 | 优先级 | 状态 | 负责人 | 目标完成日期 | 备注 |
|----|---------|------|-----------|---------|--------|------|--------|------------|------|
| R-001 | 类定义重复 | `services/workers/audio_separator_service/app/config.py:284` | ~80行 | audio_separator_service | P1 | 待处理 | - | - | 与 common.config_loader 重复 |
| R-002 | 状态管理模式 | `services/workers/*/app/tasks.py` (7处) | ~288行 | 所有工作器服务 | P0 | 待处理 | - | - | 需要创建 WorkflowTask 基类 |
| R-003 | 异常处理模式 | `services/` (18个文件) | ~54行 | 多个服务 | P2 | 待处理 | - | - | 宽泛的 Exception 捕获 |
| R-004 | GPU锁参数 | `services/workers/*/app/tasks.py` | ~20行 | GPU服务 | P2 | 待处理 | - | - | 参数不一致 |
```

### 4.2 字段说明

| 字段 | 说明 | 示例值 |
|------|------|--------|
| **ID** | 唯一标识符,格式：`R-XXX` | R-001, R-002 |
| **冗余类型** | 重复代码的类别 | 类定义重复、函数逻辑重复、状态管理模式、异常处理模式、配置加载重复 |
| **位置** | 冗余代码的文件路径和行号 | `services/workers/audio_separator_service/app/config.py:284-361` |
| **冗余代码量** | 估算的重复代码行数 | ~80行、~288行 |
| **影响范围** | 受影响的服务或模块 | audio_separator_service、所有工作器服务 |
| **优先级** | 基于影响评估的优先级 | P0（最高）、P1（高）、P2（中）、P3（低） |
| **状态** | 当前处理状态 | 待处理、进行中、已完成、已验证、已关闭 |
| **负责人** | 负责重构的开发人员 | 张三、李四 |
| **目标完成日期** | 计划完成日期 | 2024-12-31 |
| **备注** | 额外说明和上下文 | 与 common.config_loader 重复、需要创建基类 |

### 4.3 状态定义

| 状态 | 描述 | 转换条件 |
|------|------|---------|
| **待处理** | 已识别但未开始重构 | 初始状态 |
| **进行中** | 正在进行重构工作 | 已分配负责人并开始实施 |
| **已完成** | 重构代码已提交 | 代码变更已合并到主分支 |
| **已验证** | 重构后验证通过 | 测试通过且无回归问题 |
| **已关闭** | 问题已解决并归档 | 验证通过后归档 |

### 4.4 使用示例

**场景1：新增审计发现**

```markdown
| R-005 | 模型管理重复 | `services/workers/faster_whisper_service/app/model.py:45` | ~120行 | faster_whisper_service | P1 | 待处理 | - | - | 可抽象为 BaseModelManager |
```

**场景2：更新处理进度**

```markdown
| R-001 | 类定义重复 | `services/workers/audio_separator_service/app/config.py:284` | ~80行 | audio_separator_service | P1 | 进行中 | 张三 | 2024-12-15 | 已创建重构分支 |
```

**场景3：标记完成**

```markdown
| R-001 | 类定义重复 | `services/workers/audio_separator_service/app/config.py:284` | ~80行 | audio_separator_service | P1 | 已验证 | 张三 | 2024-12-15 | 已使用 common.config_loader,测试通过 |
```

### 4.5 审计清单维护流程

```
┌─────────────┐
│  发现冗余代码  │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  添加到清单   │  分配 ID、评估优先级、记录详情
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  定期审查    │  每周/每迭代更新状态
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  分配任务    │  根据优先级分配负责人
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  跟踪进度    │  更新状态、验证结果
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  归档关闭    │  验证通过后归档
└─────────────┘
```

### 4.6 清单模板文件

创建 `docs/audit/redundancy-checklist-template.md`：

```markdown
# YiVideo 代码冗余审计清单

**审计日期**：YYYY-MM-DD
**审计人员**：[姓名]
**审计范围**：[服务/模块名称]
**审计版本**：[Git commit hash]

## 执行摘要

- **扫描文件数**：XXX
- **发现冗余项**：XXX
- **估算冗余代码量**：XXX 行
- **高优先级问题**：XXX (P0/P1)
- **建议重构项**：XXX

## 冗余代码清单

| ID | 冗余类型 | 位置 | 冗余代码量 | 影响范围 | 优先级 | 状态 | 负责人 | 目标完成日期 | 备注 |
|----|---------|------|-----------|---------|--------|------|--------|------------|------|
| R-001 | | | | | | 待处理 | - | - | |
| R-002 | | | | | | 待处理 | - | - | |
| R-003 | | | | | | 待处理 | - | - | |

## 审计统计

### 按冗余类型分类

| 冗余类型 | 数量 | 冗余代码量 | 占比 |
|---------|------|-----------|------|
| 类定义重复 | | | |
| 函数逻辑重复 | | | |
| 状态管理模式 | | | |
| 异常处理模式 | | | |
| 配置加载重复 | | | |
| **总计** | | | 100% |

### 按优先级分类

| 优先级 | 数量 | 冗余代码量 | 建议处理时限 |
|--------|------|-----------|------------|
| P0（最高） | | | 立即处理 |
| P1（高） | | | 本迭代 |
| P2（中） | | | 下一迭代 |
| P3（低） | | | 待定 |
| **总计** | | | - |

### 按服务分类

| 服务 | 冗余项数量 | 冗余代码量 | 主要问题 |
|------|-----------|-----------|---------|
| audio_separator_service | | | |
| faster_whisper_service | | | |
| ffmpeg_service | | | |
| **总计** | | | - |

## 重构建议

### 高优先级重构任务

1. **[任务名称]**
   - 优先级：P0/P1
   - 预计工时：XX 小时
   - 依赖：无/[依赖项]
   - 预期收益：减少 XX 行冗余代码

### 中优先级重构任务

1. **[任务名称]**
   - 优先级：P2
   - 预计工时：XX 小时

## 附录

### 审计命令记录

```bash
# 扫描命令
rg -c "pattern" services/

# 统计命令
wc -l files
```

### 参考文档

- [代码冗余审计操作指南](../technical/code-redundancy-audit-guide.md)
- [OpenSpec 变更提案](../../openspec/changes/)
```

---

## 5. 优先级评估标准

本章节定义代码冗余问题的优先级评估标准,帮助团队合理分配重构资源。

### 5.1 优先级定义

| 优先级 | 名称 | 影响分数范围 | 重构难度 | 处理时限 | 典型特征 |
|--------|------|-------------|---------|---------|---------|
| **P0** | 最高优先级 | ≥ 8.0 | 低-中 | 立即处理（1周内） | 严重影响维护性、高风险、广泛影响 |
| **P1** | 高优先级 | 6.0 - 7.9 | 低-中 | 本迭代（2-4周） | 显著冗余、中等影响、明确收益 |
| **P2** | 中优先级 | 4.0 - 5.9 | 任意 | 下一迭代（1-2月） | 局部冗余、有限影响、可延后 |
| **P3** | 低优先级 | < 4.0 | 任意 | 待定（按需处理） | 轻微冗余、低影响、可选优化 |

### 5.2 影响分数计算方法

影响分数由三个维度加权计算：

```
影响分数 = (冗余代码量得分 × 0.3) + (维护成本得分 × 0.4) + (一致性风险得分 × 0.3)

其中：
- 冗余代码量得分：0-10分（每10行代码1分,最高10分）
- 维护成本得分：0-10分（需要同步修改的位置数,每处1分,最高10分）
- 一致性风险得分：0-10分（主观评估,逻辑不一致的风险）
```

#### 5.2.1 冗余代码量得分

| 冗余代码行数 | 得分 |
|------------|------|
| < 10 行 | 1 |
| 10-19 行 | 2 |
| 20-29 行 | 3 |
| 30-39 行 | 4 |
| 40-49 行 | 5 |
| 50-59 行 | 6 |
| 60-79 行 | 7 |
| 80-99 行 | 8 |
| 100-149 行 | 9 |
| ≥ 150 行 | 10 |

#### 5.2.2 维护成本得分

| 需要同步修改的位置数 | 得分 |
|------------------|------|
| 1 处 | 1 |
| 2 处 | 2 |
| 3 处 | 3 |
| 4 处 | 4 |
| 5 处 | 5 |
| 6 处 | 6 |
| 7 处 | 7 |
| 8 处 | 8 |
| 9 处 | 9 |
| ≥ 10 处 | 10 |

#### 5.2.3 一致性风险得分

| 风险等级 | 描述 | 得分 |
|---------|------|------|
| **极低** | 代码完全一致,无差异 | 1-2 |
| **低** | 仅有微小差异（如变量名） | 3-4 |
| **中** | 有部分逻辑差异,但功能相同 | 5-6 |
| **高** | 逻辑差异明显,容易产生不一致 | 7-8 |
| **极高** | 逻辑严重不一致,已导致 Bug | 9-10 |

### 5.3 重构难度评估

| 难度等级 | 描述 | 典型工时 | 风险 |
|---------|------|---------|------|
| **低** | 简单替换,无依赖变更,测试覆盖充分 | 2-8 小时 | 低 |
| **中** | 需要修改接口,有少量依赖变更,测试需补充 | 1-3 天 | 中 |
| **高** | 涉及架构变更,广泛依赖调整,需要大量测试 | 1-2 周 | 高 |

### 5.4 优先级评估决策矩阵

| 影响分数 | 重构难度：低 | 重构难度：中 | 重构难度：高 |
|---------|------------|------------|------------|
| **≥ 8.0** | **P0** | **P0** | **P1** |
| **6.0 - 7.9** | **P1** | **P1** | **P2** |
| **4.0 - 5.9** | **P1** | **P2** | **P2** |
| **< 4.0** | **P2** | **P3** | **P3** |

**决策规则**：
- 影响分数 ≥ 8.0 且重构难度 ≤ 中 → **P0**（立即处理）
- 影响分数 ≥ 6.0 或重构难度 = 低 → **P1**（本迭代）
- 影响分数 ≥ 4.0 → **P2**（下一迭代）
- 影响分数 < 4.0 → **P3**（待定）

### 5.5 优先级评估示例

#### 示例1：audio_separator ConfigLoader 冗余

**冗余分析**：
- 冗余代码量：~80行 → 得分 8
- 维护成本：2处（独立实现 + 统一实现）→ 得分 2
- 一致性风险：中等（功能相同但实现不同）→ 得分 6

**影响分数计算**：
```
影响分数 = (8 × 0.3) + (2 × 0.4) + (6 × 0.3)
        = 2.4 + 0.8 + 1.8
        = 5.0
```

**重构难度**：低（简单替换,无依赖变更）

**优先级判定**：
- 影响分数 = 5.0（在 4.0-5.9 范围）
- 重构难度 = 低
- 根据决策矩阵 → **P1（高优先级）**

**结论**：应在本迭代内完成重构。

---

#### 示例2：工作流状态管理模式冗余

**冗余分析**：
- 冗余代码量：~288行 → 得分 10
- 维护成本：24处（7个服务,24处状态管理）→ 得分 10
- 一致性风险：高（手动编写容易遗漏）→ 得分 8

**影响分数计算**：
```
影响分数 = (10 × 0.3) + (10 × 0.4) + (8 × 0.3)
        = 3.0 + 4.0 + 2.4
        = 9.4
```

**重构难度**：中（需要创建基类,修改所有任务）

**优先级判定**：
- 影响分数 = 9.4（≥ 8.0）
- 重构难度 = 中
- 根据决策矩阵 → **P0（最高优先级）**

**结论**：应立即处理,1周内完成。

---

#### 示例3：宽泛异常捕获模式

**冗余分析**：
- 冗余代码量：~54行（18个文件 × 3行）→ 得分 6
- 维护成本：18处 → 得分 10
- 一致性风险：低（仅代码风格问题）→ 得分 3

**影响分数计算**：
```
影响分数 = (6 × 0.3) + (10 × 0.4) + (3 × 0.3)
        = 1.8 + 4.0 + 0.9
        = 6.7
```

**重构难度**：中（需要识别具体异常类型,补充测试）

**优先级判定**：
- 影响分数 = 6.7（在 6.0-7.9 范围）
- 重构难度 = 中
- 根据决策矩阵 → **P1（高优先级）**

**结论**：应在本迭代内完成重构。

---

### 5.6 优先级调整因素

在基础评估之外,以下因素可能影响最终优先级：

| 调整因素 | 影响 | 示例 |
|---------|------|------|
| **安全风险** | ↑ 提升1级 | 冗余代码包含安全漏洞 |
| **性能影响** | ↑ 提升1级 | 冗余导致显著性能下降 |
| **即将发布** | ↑ 提升1级 | 影响即将发布的关键功能 |
| **技术债务** | ↓ 降低1级 | 历史遗留代码,影响有限 |
| **依赖阻塞** | ↓ 降低1级 | 需要等待其他重构完成 |

### 5.7 优先级审查机制

**定期审查**：
- 每周审查 P0/P1 级别问题的进度
- 每月审查 P2/P3 级别问题的优先级
- 每季度重新评估所有未解决问题

**触发重新评估的条件**：
- 发现新的相关冗余代码
- 业务需求变化
- 技术栈升级
- 团队资源调整

**审查流程**：
```
1. 收集最新数据（代码变更、新发现）
2. 重新计算影响分数
3. 评估当前重构难度
4. 应用决策矩阵
5. 考虑调整因素
6. 更新清单中的优先级
7. 重新分配资源
```

---

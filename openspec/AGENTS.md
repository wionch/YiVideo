# OpenSpec 指南 (OpenSpec Instructions)

使用 OpenSpec 进行规范驱动开发 (Spec-driven Development) 的 AI 编程助手指南。

***

## 快速自查表(TL;DR Quick Checklist)

- **搜索现有工作**：`openspec spec list --long`, `openspec list`（仅在进行全文本搜索时使用 `rg`）。

- **确定范围**：是新增能力还是修改现有能力。

- **选择唯一的** **`change-id`**：使用 kebab-case，以动词开头（`add-`, `update-`, `remove-`, `refactor-`）。

- **构建脚手架**：创建 `proposal.md`, `tasks.md`, `design.md`（仅在需要时），以及针对受影响能力的增量规范 (delta specs)。

- **强制创建 docs/ 目录**：**必须**创建 `docs/ITERATION_LOG.md` 和 `docs/RESEARCH.md`，缺一不可。这是提案有效性的前提条件。

- **编写增量**：使用 `## ADDED|MODIFIED|REMOVED|RENAMED Requirements`；每个要求至少包含一个 `#### Scenario:`。

- **验证**：运行 `openspec validate [change-id] --strict` 并修复问题。

- **请求批准**：在提案获得批准前，**不得**开始实施。

- **同步更新**：修改 `proposal.md` 时必须同步更新迭代日志，确保决策可追溯。

***

## 工程原则（OpenSpec 特定约束）

> **基础原则**：KISS/DRY/YAGNI/SOLID 的核心定义见 system prompt（CLAUDE.md → 🏛️ 全局架构约束）。
>
> 以下为 **OpenSpec 提案创建的量化约束**，用于防止过度工程。

### 反过度开发规则（强制执行）

这些规则是**不可逾越的**保护栏，旨在确保 OpenSpec 驱动的工作始终对齐"最小正确变更"。

1. **始终从验收场景出发**

   - 仅实现满足场景所必需的内容

   - 如果场景没有要求，就不要构建

2. **优先选择"乏味"但成熟的模式**

   - 避免引入新的框架、层或模式

   - 除非有可衡量的约束条件支撑（规模、延迟、安全要求）

3. **量化约束**

   - **默认新增代码控制在 100 行以内**

   - **优先采用单文件实现**，直到证明不足为止

   - 如果提议增加复杂性，必须在"调研(Research)"中记录证据

***

## MCP 服务使用约束（OpenSpec 增强规范）

> **基础工具定义**：serena/context7/sequential-thinking 的用途和触发阈值见 system prompt（CLAUDE.md → 🧠 MCP 核心认知协议）。
>
> 以下为 **OpenSpec 工作流的特定使用规范**。

### MCP 工具执行顺序（调研阶段）

在 **阶段 3（调研与证据收集）** 中，必须按以下顺序使用 MCP 工具：

```
阶段 1: sequential-thinking（需求分析）
    ↓
阶段 2: 学习规范（打开 AGENTS.md）
    ↓
阶段 3: 调研与证据收集
    ├─ Step 1: serena（代码探索）
    │   ├─ find_symbol：定位相关代码
    │   ├─ get_symbols_overview：理解代码结构
    │   └─ find_referencing_symbols：查找引用关系
    │
    ├─ Step 2: context7（API 验证）
    │   ├─ 查询框架/库文档
    │   └─ 验证版本兼容性
    │
    └─ Step 3: 记录到 docs/RESEARCH.md
```

**注意：**

- "优先级顺序"（serena > sequential-thinking > context7）是指 **通用优先级**，适用于所有编程任务

- "执行顺序"（sequential-thinking → serena → context7）是指 **OpenSpec 调研阶段的特定流程**

### OpenSpec 特定约束

1. **证据强制要求**

   - 所有调研发现必须提供精确的文件/行证据

   - **代码证据格式**：`path/to/file.ts:123`

   - **文档证据格式**：文档链接 + 关键结论

2. **禁止猜测**

   - 严禁在未通过 MCP 验证的情况下假设 API 行为或文件位置

   - 如果结论依赖于外部库行为，必须通过 context7 验证并记录在"调研(Research)"中

### MCP 服务降级策略

#### 何时使用降级策略

**触发场景**：

- [ ] MCP 服务启动失败或连接超时

- [ ] 特定 MCP 工具返回错误（如 serena 索引缺失）

- [ ] 项目禁用了某些 MCP 服务（检查 `.kilocode/rules/mcp-services.md`）

- [ ] 紧急修复场景，无时间排查 MCP 问题

#### 使用降级时的强制要求

1. 在`proposal.md` → Research 中记录："由于 [原因]，未使用 [MCP 服务]"
2. 额外提供 2 倍以上的手动验证证据（如多次`rg` 搜索结果）
3. 在 `tasks.md` 的验证章节增加人工复查任务

#### 替代方案表

| MCP 服务              | 主要用途       | 替代工具                   | 使用方法                                             | 限制说明      |
| ------------------- | ---------- | ---------------------- | ------------------------------------------------ | --------- |
| serena              | 代码探索符号导航   | `rg` + `findread_file` | `find . -name "*.py" -type frg -n "class Foo" .` | 需手动验证符号引用 |
| sequential-thinking | 任务分解推理验证   | 手动清单自检问题               | 列出步骤清单每步问"遗漏了什么？"                                | 无自动化缺口检测  |
| context7            | API 文档版本验证 | 官方文档GitHub README      | 访问 library 官网查看 package.json                     | 无版本自动对齐   |

**示例**：

```markdown
## 调研 (Research)

**限制说明**：由于 serena 不可用，通过 rg 搜索代码（限制：无法确认所有引用）

### 已检查的内容

-   代码（通过 rg 手动搜索）：
    -   `rg -n "class UserAuth" services/` → 找到 3 处定义
    -   `rg -n "import.*UserAuth" services/` → 找到 12 处引用
    -   **手动验证**：逐个检查上述引用是否需要更新
```

***

## 三阶段工作流

> **触发规则**：何时进入 OpenSpec 工作流见 system prompt（CLAUDE.md → 🚨 OpenSpec 触发机制）。
>
> 以下为提案创建的 **决策树**。

### 第一阶段：创建变更 (Research → Proposal → Tasks)

#### 决策树：何时创建提案

```
收到新请求？
├─ 修复 Bug 并恢复规范行为？ → 直接修复
├─ 错别字/格式/注释？ → 直接修复
├─ 新特性/能力？ → 创建提案
├─ 破坏性变更？ → 创建提案
├─ 架构变更？ → 创建提案
└─ 不明确？ → 创建提案（更安全）
```

**必须创建提案的场景：**

- 添加特性或功能

- 进行破坏性变更（API、模式）

- 更改架构或模式

- 优化性能（改变行为）

- 更新安全模式

**无需创建提案的场景：**

- Bug 修复（恢复预期行为）

- 错别字、格式、注释

- 依赖项更新（非破坏性）

- 配置变更

- 针对现有行为的测试

**工作流**

1. **上下文摄入**：

   - 查看 `openspec/project.md`、`openspec list` 和 `openspec list --specs` 以了解当前上下文。

2. **调研 (Research)（新增，必需）**：

   - 收集"为什么要改"和"改什么"的证据。

   - 记录确切来源（规范章节、代码点、文档、日志）。

   - 确保调研内容能直接支持 `tasks.md`，且无需任何猜测。

3. **选择唯一的、以动词开头的** **`change-id`** **并构建脚手架**：

   **步骤 3.1 - 创建目录结构**：

   - 创建 `openspec/changes/<id>/` 根目录

   - 创建 `openspec/changes/<id>/docs/` 子目录

   - 创建 `openspec/changes/<id>/specs/` 子目录

   **步骤 3.2 - 强制创建 docs/ 必需文件（优先级最高）**：

   - **必须**创建 `docs/ITERATION_LOG.md` 迭代日志文档

   - **必须**创建 `docs/RESEARCH.md` 初始调研文档

   - 这两个文件是提案有效性的**前提条件**，缺一不可

   **步骤 3.3 - 创建其他必需文件**：

   - 创建 `proposal.md` 提案文档

   - 创建 `tasks.md` 任务清单

   - （可选）创建 `design.md` 设计文档

   - 在 `specs/` 下创建规范增量文件

4. **起草** **`proposal.md`（见下方的增强模板），然后起草规范增量**：

   - 使用 `## ADDED|MODIFIED|REMOVED|RENAMED Requirements`。

   - 每个要求至少包含一个 `#### Scenario:`。

   - **必须包含"迭代概览"章节**，引用 `docs/ITERATION_LOG.md`。

5. **起草** **`tasks.md`**（仅限原子任务；严格遵守下方的**强制规则**）。

   - **必须包含迭代日志同步验证任务**。

6. **验证**：

   - 运行 `openspec validate <id> --strict` 并在分享提案前解决所有问题。

7. **请求批准**：

   - 在提案被评审并获得批准前，不得开始实施。

### 第二阶段：实施变更

将这些步骤作为 TODO 进行跟踪并逐一完成。

1. **阅读** **`proposal.md`** —— 理解正在构建什么以及为什么（有证据支撑）。
2. **阅读** **`design.md`（如果存在）** —— 查看技术决策。
3. **阅读** **`tasks.md`** —— 获取实施检查清单（原子化+ 可执行）。
4. **按顺序实施任务** —— 按顺序完成；不要跳过关卡。
5. **文档 / 规范更新必须在执行期间增量完成**：

   - **不得**在变更结束时批量进行所有文档/规范更改。

   - 当任务改变了行为时，请在接下来的文档/规范任务中（或在同一批相邻任务中）立即更新相应的文档/规范。

   - **迭代日志更新**：任何对`proposal.md` 的修改必须同步更新 `docs/ITERATION_LOG.md`。
6. **确认完成** —— 在更新状态前，确保`tasks.md` 中的每一项都已完成。
7. **更新检查清单** —— 工作全部完成后，将每个任务设置为 `- [x]`，使列表反映现实。
8. **批准关卡** —— 在提案获得评审和批准前，不得开始实施。

### 第三阶段：归档变更

部署后，创建一个单独的 PR 以执行：

- 移动整个提案目录 → `changes/archive/YYYY-MM-DD-[name]/`

  - **包括`docs/`** **目录**（保留完整的决策历史和调研证据）

  - **包括** **`proposal.md`、`tasks.md`、`design.md`**

  - **包括** **`specs/`** **目录**（增量变更记录）

- 如果能力发生变化，更新主规范库 `specs/`

- 对于仅涉及工具的变更，使用 `openspec archive <change-id> --skip-specs --yes`（始终显式传递变更 ID）。

- 运行 `openspec validate --strict` 以确认归档的变更通过了检查。

***

## 任何任务开始前

**上下文检查清单：**

- [ ] 阅读 `specs/[capability]/spec.md` 中的相关规范。

- [ ] 检查 `changes/` 中是否有待处理的冲突变更。

- [ ] 阅读 `openspec/project.md` 以了解惯例。

- [ ] 运行 `openspec list` 以查看活跃的变更。

- [ ] 运行 `openspec list --specs` 以查看现有的能力。

- [ ] 应用工程原则 (KISS/SOLID/DRY/YAGNI) 以防止过度开发。

- [ ] 优先使用 MCP 服务 (`serena` → `sequential-thinking` → `context7`) 进行验证和计划。

- [ ] 检查 `docs/ITERATION_LOG.md` 以了解需求演变历史。

**创建规范前：**

- 始终检查能力是否已经存在。

- 优先修改现有规范，而不是创建重复项。

- 使用 `openspec show [spec]` 查看当前状态。

- 如果请求模糊，在构建脚手架前提出 1-2 个澄清问题。

### 搜索指南

- 枚举规范：`openspec spec list --long`（或脚本使用的 `--json`）。

- 枚举变更：`openspec list`（或 `openspec change list --json` - 已弃用但仍可用）。

- 显示详情：

  - 规范：`openspec show <spec-id> --type spec`（使用 `--json` 进行过滤）。

  - 变更：`openspec show <change-id> --json --deltas-only`。

- 全文本搜索（使用 ripgrep）：`rg -n "Requirement:|Scenario:" openspec/specs`。

***

## 快速开始 (Quick Start)

### CLI 命令

```bash
# 核心命令
openspec list # 列出活跃变更
openspec list --specs          # 列出规范
openspec show [item]           # 显示变更或规范
openspec validate [item]       # 验证变更或规范
openspec archive <change-id> [--yes|-y]   # 部署后归档（非交互式运行请添加 --yes）

# 项目管理
openspec init [path]           # 初始化 OpenSpec
openspec update [path]         # 更新指令文件

# 交互模式
openspec show  # 提示进行选择
openspec validate              # 批量验证模式

# 调试
openspec show [change] --json --deltas-only
openspec validate [change] --strict
```

### 命令标志 (Flags)

- `--json` - 机器可读输出

- `--type change|spec` - 区分项目类型

- `--strict` - 全面验证

- `--no-interactive` - 禁用提示

- `--skip-specs` - 归档时不更新规范

- `--yes`/`-y` - 跳过确认提示（用于非交互式归档）

***

## 目录结构 (Directory Structure)

```
openspec/
├── project.md              # 项目惯例
├── specs/                # 当前真相 - 已构建的内容
│   └── [capability]/       # 单一聚焦的能力
│       ├── spec.md         # 需求和场景
│       └── design.md       # 技术模式
├── changes/                # 提案 - 应改变的内容
│   ├── [change-name]/
│   │   ├── proposal.md     # 为什么、改什么、影响（+ 调研证据）
│   │   ├── tasks.md        # 实施检查清单（严格执行的原子任务）
│   │   ├── design.md       # 技术决策（可选；见标准）
│   │   ├── docs/          # 讨论、澄清、调研文档（必需）
│   │   │   ├── ITERATION_LOG.md  # 迭代日志（必需）
│   │   │   ├── RESEARCH.md       # 初始调研（必需）
│   │   │   └── ... # 其他分析文档
│   │   └── specs/          # 增量变更
│   │       └── [capability]/
│   │           └── spec.md # ADDED/MODIFIED/REMOVED/RENAMED
│   └── archive/            # 已完成的变更
```

### 提案目录文件管理规范

- **根目录允许文件**：

  - `proposal.md`（必需）

  - `tasks.md`（必需）

  - `design.md`（可选，仅在需要时）

  - `specs/` 目录（必需，用于规范增量）

  - `docs/` 目录（必需，用于讨论和澄清文档）

- **辅助文档存放**：

  - 所有讨论、澄清、**初始调研**过程中产生的辅助文档必须放置在 `docs/` 目录下

  - **必须创建** `docs/RESEARCH.md` 记录初始调研过程和发现

  - 其他分析文档：`ARCHITECTURE_REVIEW.md`、`PERFORMANCE_ANALYSIS.md` 等

  - 文档命名应使用大写蛇形命名法

  - **禁止**在提案根目录下创建除规定文件外的其他文档

- **迭代日志要求**：

  - 必须创建 `docs/ITERATION_LOG.md` 记录需求演进过程

  - 每次更新`proposal.md` 时必须同步更新迭代日志

  - 迭代日志必须包含完整的版本历史、决策依据和引用

### 命名规范总结

| 元素类型        | 命名规范                  | 示例                                  | 说明            |
| ----------- | --------------------- | ----------------------------------- | ------------- |
| 变更 ID（目录名）  | `kebab-case`          | `add-two-factor-auth`               | 动词开头，唯一       |
| 能力名称（目录）    | `kebab-case`          | `user-auth/`                        | 动词-名词组合       |
| docs/ 文档    | `UPPER_SNAKE_CASE.md` | `RESEARCH.mdARCHITECTURE_REVIEW.md` | 全大写+下划线       |
| 提案根文件       | `lowercase.md`        | `proposal.mdtasks.md`               | 小写，固定名称       |
| specs/ 增量文件 | `spec.md`（固定）         | `specs/auth/spec.md`                | 必须命名为 spec.md |
| specs/ 能力目录 | `kebab-case`          | `user-auth/video-merge/`            | 与主规范库对齐       |

***

## 创建变更提案

### 决策树

```
收到新请求？
├─ 修复 Bug并恢复规范行为？ → 直接修复
├─ 错别字/格式/注释？ → 直接修复
├─ 新特性/能力？ → 创建提案
├─ 破坏性变更？ → 创建提案
├─ 架构变更？ → 创建提案
└─ 不明确？ → 创建提案（更安全）
```

### 提案结构（增强版：包含调研）

1. 创建目录：`changes/[change-id]/`（使用 kebab-case，动词开头，唯一）。**必须创建** `docs/ITERATION_LOG.md` 和 `docs/RESEARCH.md`。

2. 编写 `proposal.md`：

```markdown
# 变更：[简短的变更描述]

## 为什么 (Why)

[用 1-2 句话说明问题/机会。]
[陈述用户痛点 / 业务需求 / 正确性缺口。]

## 调研 (Research)（必需）

记录证据以证明变更的合理性并降低风险。
本章节必须足够详尽，以便在没有猜测的情况下支持 tasks.md。

### 已检查的内容

-   初始调研：
    -   `docs/RESEARCH.md#可行性分析` - 技术可行性评估
    -   `docs/RESEARCH.md#关键发现` - 前期调研结论
-   规范：
    -   `specs/<capability>/spec.md` 章节：[确切标题 + 简短说明]
-   文档：
    -   `path/to/doc.md:行号-行号` [文档目前的声明]
-   代码：
    -   `path/to/file.ts:123` [目前的行为]
    -   `path/to/other.go:45` [相关的分支/验证]
-   运行时/ 日志 / 指标（如果有）：
    -   [命令 + 时间戳 + 关键观察结果]
-   外部文档（如果有，通过 MCP/context7）：
    -   [文档页面 + 相关的 API 行为]

### 发现 (Findings)（附证据）

每个"发现"必须以明确的"决策"结尾，以便 tasks.md 中没有"可能/如果需要"。

-   可选格式：发现表

    -   为了可读性，发现可以表示为 Markdown 表格。
    -   每一行仍必须包含：发现（声明）、证据（确切指针）、决策，以及（可选）备注。
    -   证据必须保持精确（规范标题或`path/to/file.ext:行号-行号`），以便在编写 tasks.md 时无需猜测。

-   发现 1：[声明]

    -   证据：[规范标题 / 文件:行号 / 文档行]
    -   决策：[仅文档 | 仅代码 | 文档+代码 | 仅规范增量 | 标记为不支持 | 超出范围]
    -   备注：[约束/兼容性/边界情况]

-   发现 2：...

### 为什么采用此方法（KISS/YAGNI 检查）

-   满足场景的最小变更：
    -   [...]
-   明确拒绝的替代方案（及原因）：
    -   [...]
-   超出范围的内容（非目标）：
    -   [...]

## 迭代概览 (Iteration Overview)

### 变更演进历程

本提案经历了以下关键迭代，详细记录见 `docs/ITERATION_LOG.md`：

1. **v0.1 (YYYY-MM-DD)**：[初始需求描述]
2. **v0.2 (YYYY-MM-DD)**：[基于什么发现，做了什么调整]
3. **v1.0 (YYYY-MM-DD)**：[当前版本描述]

### 关键决策点

-   **[决策 1]**：[简要说明]（证据：`docs/文档.md#章节`）
-   **[决策 2]**：[简要说明]（证据：`docs/文档.md#章节`）

### 当前版本总结

[最终方案描述]，已在 `specs/` 中定义，并通过 `tasks.md` 规划实施。

## 变更内容

-   [变更列表]
-   [用**BREAKING** 标记破坏性变更]
-   [列出新增/修改的需求以及受影响的流程]

## 影响 (Impact)

-   受影响的规范：
    -   `specs/<capability>/spec.md` (ADDED/MODIFIED/REMOVED/RENAMED:...)
-   受影响的代码：
    -   `path/to/file.ts` (将要更改的内容)
    -   `path/to/dir/` (原因)
-   发布/迁移说明（如果需要）：
    -   [...]
-   风险：
    -   [...]
```

1. 创建规范增量：`specs/[capability]/spec.md`

```markdown
## ADDED Requirements

### Requirement: 新特性名称

系统应提供……

#### Scenario: 成功案例

-   **WHEN** 用户执行了动作
-   **THEN** 预期结果

## MODIFIED Requirements

### Requirement: 现有特性名称

[完整的修改后的需求内容]

## REMOVED Requirements

### Requirement: 旧特性名称

**原因**：[为什么要移除]
**迁移**：[如何处理]

## RENAMED Requirements

-   FROM: `### Requirement: 旧名称`
-   TO: `### Requirement: 新名称`
```

如果影响多个能力，请在 `changes/[change-id]/specs/<capability>/spec.md` 下创建多个增量文件 —— 每个能力一个。

1. 创建 `tasks.md`（见下方的"tasks.md 规则"；仅限原子任务）。**必须包含迭代日志同步验证任务**。

2. 在需要时创建 `design.md`：
   如果满足以下任何条件，请创建 `design.md`；否则省略：

- 横切变更（涉及多个服务/模块）或新的架构模式。

- 新的外部依赖或显著的数据模型变更。

- 安全性、性能或迁移复杂性。

- 在编码前进行技术决策有助于消除歧义。

最小化`design.md` 骨架：

```markdown
## 上下文 (Context)

[背景、约束、利益相关者]

## 目标 / 非目标

-   目标：[...]
-   非目标：[...]

## 决策 (Decisions)

-   决策：[什么以及为什么]
-   考虑过的替代方案：[选项 + 理由]

## 风险 / 权衡

-   [风险] → 缓解措施

## 迁移计划

[步骤、回滚]

## 开放性问题

-   [...]
```

## 文档实时同步机制

### 基本原则

1. **证据驱动**：`docs/` 目录下的文档是原始证据来源
2. **决策中心**：`proposal.md` 基于证据做出决策并引用来源
3. **执行关联**：`tasks.md` 完全基于 `proposal.md` 的决策
4. **规范对齐**：`specs/` 体现最终达成共识的规范
5. **增量更新**：任何文档修改必须同步更新所有相关引用

### 文档层级与引用关系

- **证据层(docs/)**：讨论、分析、调研产生的原始文档- 命名规范：`UPPER_SNAKE_CASE.md`

  - 内容要求：包含可供引用的结构化发现

  - **不引用其他提案文档**，保持原始性

- **决策层 (proposal.md)**：基于证据做出变更决策

  - 必须在"调研(Research)"中明确引用证据文档

  - 引用格式：`docs/FILE_NAME.md#章节或行范围`

  - 承担信息整合和决策记录的职责

- **执行层 (tasks.md)**：基于决策的执行计划

  - 每个任务必须引用 `proposal.md` 的具体发现

  - 不直接引用 `docs/` 文档，通过提案间接追溯

- **规范层 (specs/)**：最终的行为标准

  - 基于提案决策的正式规范

  - 归档时合并到主规范库

### 同步更新流程

1. **讨论产生** → 记录到 `docs/`
2. **证据确认** → 提案引用并决策
3. **决策确定** → 更新 `tasks.md` 执行计划
4. **实施完成** → 更新 `specs/` 规范
5. **循环验证** → 确保各层一致性

## 需求迭代追踪与日志管理

### 强制约束：迭代日志维护

1. **必须创建**：每个提案必须包含独立的迭代日志文档`docs/ITERATION_LOG.md`
2. **必须同步**：每次更新 `proposal.md` 时，必须同步更新迭代日志
3. **必须引用**：`proposal.md` 中必须包含"迭代概览"章节，引用和总结迭代日志
4. **必须验证**：`tasks.md` 中必须包含迭代日志一致性的验证任务
5. **必须检查**：`openspec validate` 必须包含迭代一致性检查

### 迭代日志内容要求

```markdown
# 迭代日志 - [变更 ID]

## 概述

记录 [变更描述] 提案的完整演进过程，包括初始需求、讨论过程、决策变更和最终方案。

## 版本历史

| 版本 | 日期       | 状态     | 关键决策点                     | 相关文档                    | 提出者/决策者 |
| ---- | ---------- | -------- | ------------------------------ | --------------------------- | ------------- |
| v0.1 | YYYY-MM-DD | 已废弃   | 初始需求：a, b, c              | 无                          | @user1        |
| v0.2 | YYYY-MM-DD | 已采纳   | 移除 c，增加 d，基于性能考虑   | `docs/PERF_ANALYSIS.md#3.2` | @user2        |
| v0.3 | YYYY-MM-DD | 已采纳   | d 拆分为 e 和 f，优化架构      | `docs/ARCH_REVIEW.md#建议1` | @user3        |
| v1.0 | YYYY-MM-DD | 当前版本 | 最终方案：a, b, e, f，增加监控 | `docs/FINAL_REVIEW.md`      | 团队共识      |

## 详细迭代记录

### 版本 v0.1 - 初始提案 (YYYY-MM-DD)

-   **原始需求**：[描述]
-   **决策背景**：[背景说明]
-   **状态变化**：[何时废弃/修改]
-   **废弃原因**：[原因说明]

### 版本 v0.2 - 技术调整 (YYYY-MM-DD)

-   **变更内容**：[具体变更]
-   **决策依据**：`docs/文档.md#具体章节`
-   **关键讨论**：`docs/讨论文档.md`
-   **影响范围**：
    -   更新 `proposal.md` [具体章节]
    -   新增/修改 `specs/[能力]/spec.md`

### 版本 v1.0 - 最终方案 (YYYY-MM-DD)

-   **变更内容**：[最终调整]
-   **决策依据**：[综合评估]
-   **完成标准**：[验收标准]
-   **归档计划**：部署后执行 `openspec archive`
```

### 迭代日志维护工作流

#### 规则 1：创建提案时必须初始化

- 创建 `proposal.md` 时，必须同时创建 `docs/ITERATION_LOG.md`

- 初始日志至少包含 v0.1 版本记录

#### 规则 2：讨论产生新发现时必须更新

```
触发场景                → 执行动作
─────────────────────────────────────────────────────────────────
讨论发现技术限制/新方案                  → 1. 记录到 `docs/NEW_FINDING.md`
                → 2. 更新 `ITERATION_LOG.md` 添加新版本
                                          → 3. 更新 `proposal.md` 迭代概览
                                          → 4. 同步 `tasks.md` 和 `specs/`
```

#### 规则 3：提案修改必须同步日志

- 任何对`proposal.md` 内容的修改（需求、范围、决策）必须：

  1. 先在 `ITERATION_LOG.md` 中创建新版本记录
  2. 然后在 `proposal.md` 中更新迭代概览
  3. 最后执行实际修改

#### 规则 4：验证时检查同步状态

- `openspec validate --strict` 将检查：

  1. `proposal.md` 是否包含迭代概览章节
  2. `docs/ITERATION_LOG.md` 是否存在且格式正确
  3. 提案版本与日志最新版本是否一致
  4. 所有引用的证据文档是否存在

#### 规则 5：归档时生成最终摘要

- 执行 `openspec archive` 时，自动生成迭代过程摘要

  - 摘要包含：迭代次数、关键决策点、最终方案对比

***

## tasks.md 规则（严格 + 强制执行 100% 原子化）

`tasks.md` 是一个执行合同。每个任务**必须**是原子的、无歧义的且可直接执行。

如果 `tasks.md` 不严格符合以下规则，在提案被视为有效之前，必须重新生成。

### 硬性门槛："强制执行 100% 原子化"的定义

只有当**所有**任务满足以下条件时，`tasks.md` 才被视为符合"强制原子化"：

- 每个任务恰好有一个主要的变更输出。

- 每个任务恰好涉及一个文件（一个路径）。

- 任务中**不得**出现任何条件性语言（"如果需要"、"必要时"、"可能"、"按需"、"相关"、"等等"、"..."）。

- 具有至少一个可运行命令的可验证验收标准。

如果一项变更确实需要多个文件，它**必须**表示为多个任务，每个任务对应一个确切的文件。

### 必需章节

`tasks.md` 必须包含以下章节（按此顺序）：

1. `## Traceability (Research → Tasks)`（可追溯性）
2. `## 1. Implementation`（实施）
3. `## 2. Validation`（验证）
4. `## 3. Self-check (ENFORCED)`（自检）

如果缺少任何章节，请重新生成 `tasks.md`。

### 绝对要求（逐项任务字段）

每个复选框任务必须包含以下所有字段（无一例外）：

- **证据 (Evidence)**：指向提案"调研 (Research)"发现的指针（例如 `proposal.md → Research → Finding2(Decision: Doc+Code)`）。

- **编辑范围 (Edit scope)**：恰好一个文件路径 + 确切的行范围（优先选择）或确切的文档章节标题 + 行范围。

- **命令 (Commands)**：至少一个用于验证变更的可运行命令（即使是文档任务）。

- **完成标志 (Done when)**：与命令输出 / 模式验证 / 测试通过标准挂钩的客观验收条件。

如果任何字段缺失或模糊，请重新生成 `tasks.md`。

### 原子化规则（严格）

- 一项任务**必须**恰好产生一个主要的产物变更。

- 一项任务**必须**恰好触及一个文件：

  - 对于文档：恰好一个 `.md` 文件。

  - 对于代码：恰好一个源文件。

  - 对于测试：恰好一个测试文件。

- **不要**编写类似"更新 A 和 B"或"将 X 与 Y 同步"的任务。

  - 将它们分解为多个任务，每个任务范围限定在一个文件和一个输出。

- 文档/代码一致性工作必须按节点/端点拆分：

  - 每个工作流节点文档示例变更对应一个任务（一个节点 == 一个任务 == 一个文档文件变更）。

  - 每个 API 端点文档块变更对应一个任务（一个端点 == 一个任务 == 一个文档文件变更）。

- 文档/规范任务必须交替进行（增量更新）：

  - 对于大型变更，**不得**将所有文档/规范任务放在 `tasks.md` 的末尾。

  - 在实施或更改行为后，紧接着安排相关的文档/规范更新任务。

- "可能/如果需要"的逻辑必须在提案的"调研决策"中解决，而不是在任务中解决。

  - 如果你无法决定，请先添加一个带有决策要求的调研发现（并重新生成任务）。

### 原子化规则的例外情况

仅以下两种情况允许单个任务涉及多个文件：

#### 例外 1：原子性重命名

**场景**：文件重命名必须同时更新所有导入引用，否则破坏构建

**条件**：

- 重命名操作（`mv old.ts new.ts`）与更新引用必须在单次提交完成

- **影响文件数 ≤ 10**（超过则必须拆分）

- 所有引用更新都是机械性的（查找替换）

**任务格式示例**：

```markdown
-   [ ] 1.3 重命名 UserAuth.ts → Authentication.ts 并更新所有引用
    -   Evidence: proposal.md → Research → Finding3
    -   Edit scope:
        -   `src/auth/UserAuth.ts` → `src/auth/Authentication.ts`
        -   更新引用：`src/**/*.ts`（通过 rg 识别，共 8 个文件）
    -   Commands:
        -   `mv src/auth/UserAuth.ts src/auth/Authentication.ts`
        -   `rg -l "UserAuth" src/ | xargs sed -i 's/UserAuth/Authentication/g'`
        -   `npm run build` # 验证无引用错误
    -   Done when:
        -   文件已重命名
        -   所有引用已更新（验证：`rg "UserAuth" src/` 无结果）
        -   项目构建成功
```

#### 例外 2：工具生成代码

**场景**：使用官方工具（protobuf、OpenAPI、代码生成器）生成多个文件

**条件**：

- 生成命令产生多个文件，但逻辑上不可分割

- **仅限官方工具**（在项目 README 或依赖中有文档）

- **禁止自定义脚本**（自定义脚本应拆分为生成+验证任务）

- 生成的文件不应手动编辑

**任务格式示例**：

```markdown
-   [ ] 2.1 从 schema.proto 生成 gRPC 代码
    -   Evidence: proposal.md → Research → Finding5
    -   Edit scope: `generated/grpc/`（目录）
    -   Commands:
        -   `protoc --python_out=generated/grpc schema.proto`
        -   `ls -la generated/grpc/` # 验证文件生成
    -   Done when:
        -   generated/grpc/ 包含所有预期的 .py 文件
        -   文件可被项目正常导入
```

#### 判断流程图

```
任务涉及多个文件？
│
├─ 是文件重命名操作？
│  ├─ 影响文件数 ≤ 10？ → ✓ 允许例外1
│  └─ 影响文件数 > 10？ → ✗ 拆分为多个任务
│
├─ 是官方工具生成代码？
│  ├─ 工具在项目 README 中有文档？ → ✓ 允许例外2
│  └─ 自定义脚本？ → ✗ 生成后拆分为验证任务
│
└─ 其他情况？ → ✗ 必须拆分为单文件任务
```

**重要**：这些是**严格受限的例外**，仅在符合上述条件时使用。如有疑问，默认拆分为多个单文件任务。

### 禁止的任务模式（扩展）

禁止在任何复选框项文本、证据、编辑范围、命令、完成标志中使用：

- 条件词汇："如果需要 / 必要时 / 可能 / 按需 / 相关 / 等等 / 视情况 / 暂定/ 后续/ 再确认 / 待定/ TBD / TBC / ? / ……"

- "按需重构"、"提高代码质量"、"更新文档"、"修复问题"。

- 没有任何能更新提案调研的具体交付物的"调查 X"。

- 在"编辑范围"中引用多个文件的任何任务。

### 命令要求（不得有空命令）

- 文档任务仍必须包含至少一个验证命令，例如：

  - `rg -n "<pattern>" docs/...`

  - `python -m compileall ...`（如果包含代码引用）

  - `openspec validate <change-id> --strict`（通常属于验证章节，但文档任务仍可使用 rg 检查）。

- 代码任务必须包含至少一个编译/测试/检查 (lint) 命令。

- 如果项目的测试/检查命令未知，必须先通过调研发现并记录在提案中，然后再在此处使用。

### 必需的可追溯性

- 每个"调研发现 (Research Finding)"必须映射到"可追溯性"中的一个或多个任务。

- 每个任务必须恰好引用一个"发现"（保持 1:1；如果一个任务服务于多个发现，请拆分任务）。

### 迭代日志相关任务（必需）

**注意**：迭代日志验证任务已包含在下方的 tasks.md 模板（2.3 任务）中，实施时直接使用模板即可。

### 必需的 tasks.md 模板（强制执行）

```markdown
## Traceability (Research → Tasks)

-   Finding 1 → 1.1, 1.2
-   Finding 2 → 1.3
-   Finding 3 → 1.4
-   Finding 4 → 1.5

## 1. Implementation

-   [ ] 1.1 [单一动作，单一文件]

    -   Evidence: proposal.md → Research → Finding 1 (Decision: ...)
    -   Edit scope: `path/to/file.ext:行号-行号`
    -   Commands:
        -   `rg -n "..." path/to/file.ext`
    -   Done when: [与命令输出相关的客观陈述或精确的 diff 预期]

-   [ ] 1.2 [单一动作，单一文件]
    -   Evidence: proposal.md → Research → Finding 1 (Decision: ...)
    -   Edit scope: `path/to/another_file.ext:行号-行号`
    -   Commands:
        -   `[一个可运行的命令]`
    -   Done when: [客观陈述]

## 2. Validation

-   [ ] 2.1 OpenSpec 严格验证

    -   Evidence: proposal.md → Research → [发现]
    -   Commands:
        -   `openspec validate <change-id> --strict`
    -   Done when: 命令以 0 状态退出。

-   [ ] 2.2 项目检查

    -   Evidence: proposal.md → Research → [发现]
    -   Commands:
        -   `[项目测试命令]`
        -   `[项目 lint/format 命令]`
    -   Done when: 所有命令成功且没有新的警告。

-   [ ] 2.3 迭代日志同步验证

    -   Evidence: proposal.md → 迭代概览
    -   Commands:
        -   `test -f docs/ITERATION_LOG.md`
        -   `rg -n "^## 版本历史" docs/ITERATION_LOG.md`
        -   `rg -n "^### 版本 v" docs/ITERATION_LOG.md | wc -l`
    -   Done when:
        1. 日志文件存在
        2. 包含版本历史表格
        3. 提案迭代概览中的版本号在日志中都有对应记录

-   [ ] 2.4 docs/ 目录完整性验证
    -   Evidence: AGENTS.md → 第 179-182 行（强制要求）
    -   Commands:
        -   `test -f docs/ITERATION_LOG.md && echo "✓ 迭代日志存在"`
        -   `test -f docs/RESEARCH.md && echo "✓ 调研文档存在"`
        -   `rg -n "^## 迭代概览" proposal.md`
        -   `rg -n "docs/ITERATION_LOG.md" proposal.md`
    -   Done when:
        1. docs/ITERATION_LOG.md 存在
        2. docs/RESEARCH.md 存在
        3. proposal.md 包含"迭代概览"章节
        4. proposal.md 引用了迭代日志

## 3. Self-check (ENFORCED)

-   [ ] 3.1 每个任务在"编辑范围"中仅触及一个文件。
-   [ ] 3.2 每个任务恰好引用一个"发现"。
-   [ ] 3.3 任务中不包含条件性语言（如果需要/必要时/可能/按需/……）。
-   [ ] 3.4 每个任务都包含"命令"和客观的"完成标志"。
-   [ ] 3.5 迭代日志已创建且与提案同步。
-   [ ] 3.6 **docs/ 目录完整性** - 必须包含以下文件：
    -   `docs/ITERATION_LOG.md` 存在且包含版本历史表格
    -   `docs/RESEARCH.md` 存在且包含调研发现
    -   `proposal.md` 包含"迭代概览"章节并引用迭代日志
-   [ ] 3.7 **MODIFIED 需求包含完整内容** - 检查方法：对比 `specs/[capability]/spec.md` 和增量文件
    -   MODIFIED 块必须包含：原标题 + 所有原场景 + 修改后的场景
    -   不能只写新增部分，必须是完整的需求定义
```

### 生成者自检（分享前必做）

在分享提案前，助手必须验证：

- `tasks.md` 包含所有必需章节。

- 每个任务都是单文件范围且单发现范围。

- 任务中不包含条件性语言。

- 没有任务是复合意图。

- **docs/ 目录完整性**：

  - `docs/ITERATION_LOG.md` 已创建且包含版本历史表格

  - `docs/RESEARCH.md` 已创建且包含调研发现

  - `proposal.md` 包含"迭代概览"章节并引用迭代日志

- 迭代日志验证任务已包含且格式正确。

如果任何检查失败，请重新生成 `tasks.md` 直到通过。

***

## 规范文件格式 (Spec File Format)

### 关键：场景格式化

**正确**（使用 4 个 # 号标题）：

```markdown
#### Scenario: 用户登录成功

-   **WHEN** 提供了有效的凭据
-   **THEN** 返回 JWT 令牌
```

**错误**（不要使用项目符号或加粗）：

```markdown
-   **Scenario: 用户登录**❌
    **Scenario**: 用户登录 ❌

### Scenario: 用户登录 ❌
```

每个要求必须至少有一个场景。

### 需求措辞

- 对规范性要求使用 SHALL/MUST（必须/应）（除非是有意为之的非规范性内容，否则避免使用 should/may）。

### 增量操作 (Delta Operations)

- `## ADDED Requirements` - 新能力。

- `## MODIFIED Requirements` - 变更行为。

- `## REMOVED Requirements` - 弃用特性。

- `## RENAMED Requirements` - 名称变更。

标题匹配使用 `trim(header)` —— 忽略空白。

#### 何时使用 ADDED vs MODIFIED

- **ADDED**：引入一个可以作为需求独立存在的新能力或子能力。当变更与现有内容正交时（例如添加"斜杠命令配置"），而不是改变现有需求的语义时，优先使用 ADDED。

- **MODIFIED**：更改现有需求的行为、范围或验收标准。始终粘贴**完整的、更新后的**需求内容（标题 + 所有场景）。归档器将用你提供的内容替换整个需求；部分增量会导致之前的细节丢失。

- **RENAMED**：仅在名称更改时使用。如果你同时也改变了行为，请使用 RENAMED（更名）加上引用新名称的 MODIFIED（内容）。

常见陷阱：使用 MODIFIED 添加新关注点而不包含先前文本。这会导致在归档时丢失细节。如果你不是显式更改现有需求，请在 ADDED 下添加新需求。

正确编写 MODIFIED 需求：

1. 在 `openspec/specs/<capability>/spec.md` 中找到现有需求。
2. 复制整个需求块（从 `### Requirement: ...` 到其场景结束）。
3. 将其粘贴到 `## MODIFIED Requirements` 下并进行编辑以反映新行为。
4. 确保标题文本完全匹配（不区分空白），并保留至少一个 `#### Scenario:`。

RENAMED 示例：

```markdown
## RENAMED Requirements

-   FROM: `### Requirement: Login`
-   TO: `### Requirement: User Authentication`
```

***

## 故障排除

### 常见错误

**"Change must have at least one delta" (变更必须至少有一个增量)**

- 检查 `changes/[name]/specs/` 是否存在且包含 .md 文件。

- 验证文件是否有操作前缀（如 ## ADDED Requirements）。

**"Requirement must have at least one scenario" (需求必须至少有一个场景)**

- 检查场景是否使用了 `#### Scenario:` 格式（4 个 # 号）。

- 不要在场景标题中使用项目符号或加粗。

**隐蔽的场景解析失败**

- 需要确切格式：`#### Scenario: 名称`。

- 使用此命令调试：`openspec show [change] --json --deltas-only`。

**"迭代日志缺失或不完整"**

- 检查是否创建了 `docs/ITERATION_LOG.md`

- 验证 `proposal.md` 是否包含"迭代概览"章节

- 运行基础验证命令检查文件状态

### 验证技巧

```bash
# 始终使用严格模式进行全面检查
openspec validate [change] --strict

# 调试增量解析
openspec show [change] --json | jq '.deltas'

# 检查特定需求
openspec show [spec] --json -r1

# 验证迭代日志同步（详见 tasks.md 模板 2.3 任务）
```

***

## 顺利路径脚本 (Happy Path Script)

```bash
# 1) 探索当前状态
openspec spec list --long
openspec list
# 可选的全文本搜索：
# rg -n "Requirement:|Scenario:" openspec/specs
# rg -n "^#|Requirement:" openspec/changes

# 2) 选择变更 ID并构建脚手架
CHANGE=add-two-factor-auth
mkdir -p openspec/changes/$CHANGE/{specs/auth,docs}

# 2.1) 强制创建 docs/ 必需文件（优先级最高）
cat > openspec/changes/$CHANGE/docs/RESEARCH.md << 'EOF'
# 初始调研 - add-two-factor-auth

## 背景
[为什么需要这个变更]

## 可行性分析
| 维度 | 评估结果 | 证据 |
|------|----------|------|
| 技术可行性 | ... | ... |
| 资源可用性 | ... | ... |

## 关键发现
1. **发现1**：[描述]（证据：`path/to/file.ts:123`）
2. **发现2**：[描述]（证据：`specs/capability/spec.md`）

## 初步结论
[是否建议继续 / 需要什么条件]
EOF

cat > openspec/changes/$CHANGE/docs/ITERATION_LOG.md << 'EOF'
# 迭代日志 - add-two-factor-auth

## 概述
记录双重身份验证功能的演进过程。

## 版本历史
| 版本 | 日期 | 状态 | 关键决策点 | 相关文档 | 提出者/决策者 |
|------|------|------|------------|----------|---------------|
| v0.1 | $(date +%Y-%m-%d) | 当前版本 | 初始需求：添加2FA功能 | 无 | 系统 |

## 详细迭代记录

### 版本 v0.1 - 初始提案 ($(date +%Y-%m-%d))
- **原始需求**：添加双重身份验证功能
- **决策背景**：安全增强需求
- **状态变化**：初始版本
EOF

# 2.2) 创建 proposal.md（包含所有必需章节）
cat > openspec/changes/$CHANGE/proposal.md << 'EOF'
# 变更：[简短的变更描述]

## 为什么 (Why)

[用 1-2 句话说明问题/机会。]
[陈述用户痛点 / 业务需求 / 正确性缺口。]

## 调研 (Research)（必需）

记录证据以证明变更的合理性并降低风险。
本章节必须足够详尽，以便在没有猜测的情况下支持 tasks.md。

### 已检查的内容

-   初始调研：
    -   `docs/RESEARCH.md#可行性分析` - 技术可行性评估
    -   `docs/RESEARCH.md#关键发现` - 前期调研结论
-   规范：
    -   `specs/<capability>/spec.md` 章节：[确切标题 + 简短说明]
-   代码：
    -   `path/to/file.ts:123` [目前的行为]

### 发现 (Findings)（附证据）

-   发现 1：[声明]
    -   证据：[规范标题 / 文件:行号 / 文档行]
    -   决策：[仅文档 | 仅代码 | 文档+代码 | 仅规范增量]

### 为什么采用此方法（KISS/YAGNI 检查）

-   满足场景的最小变更：[...]
-   明确拒绝的替代方案（及原因）：[...]
-   超出范围的内容（非目标）：[...]

## 迭代概览 (Iteration Overview)

### 变更演进历程

本提案经历了以下关键迭代，详细记录见 `docs/ITERATION_LOG.md`：

1. **v0.1 (YYYY-MM-DD)**：[初始需求描述]

### 关键决策点

-   **[决策 1]**：[简要说明]（证据：`docs/文档.md#章节`）

### 当前版本总结

[最终方案描述]，已在 `specs/` 中定义，并通过 `tasks.md` 规划实施。

## 变更内容

-   [变更列表]
-   [用**BREAKING** 标记破坏性变更]

## 影响 (Impact)

-   受影响的规范：
    -   `specs/<capability>/spec.md` (ADDED/MODIFIED/REMOVED/RENAMED:...)
-   受影响的代码：
    -   `path/to/file.ts` (将要更改的内容)
-   风险：
    -   [...]
EOF

# 2.3) 创建 tasks.md
cat > openspec/changes/$CHANGE/tasks.md << 'EOF'
## Traceability (Research → Tasks)
- Finding1 → 1.1

## 1. Implementation
- [ ] 1.1 [单一动作，单一文件]
  - Evidence: proposal.md → Research → Finding 1 (Decision:...)
  - Edit scope: `path/to/file.ext:行号-行号`
  - Commands:
    - `rg -n "..." path/to/file.ext`
  - Done when: [与命令输出相关的客观陈述或精确的diff预期]

## 2. Validation
- [ ] 2.1 OpenSpec 严格验证
  - Evidence: proposal.md → Research → Finding 1
  - Commands:
    - openspec validate add-two-factor-auth --strict
  - Done when: 命令以0 状态退出。

- [ ] 2.2 迭代日志同步验证
  - Evidence: proposal.md → 迭代概览
  - Commands:
    - test -f docs/ITERATION_LOG.md
    - rg -n "^## 版本历史" docs/ITERATION_LOG.md
    - rg -n "^### 版本 v" docs/ITERATION_LOG.md | wc -l
  - Done when:
    1. 日志文件存在
    2. 包含版本历史表格
    3. 提案迭代概览中的版本号在日志中都有对应记录

## 3. Self-check (ENFORCED)
- [ ] 3.1 每个任务在"编辑范围"中仅触及一个文件。
- [ ] 3.2 每个任务恰好引用一个"发现"。
- [ ] 3.3 任务中不包含条件性语言。
- [ ] 3.4 每个任务都包含"命令"和客观的"完成标志"。
- [ ] 3.5 迭代日志已创建且与提案同步。
- [ ] 3.6 MODIFIED 需求包含完整内容
EOF

# 4) 添加增量（示例）
cat > openspec/changes/$CHANGE/specs/auth/spec.md << 'EOF'
## ADDED Requirements
### Requirement: 双重身份验证
用户在登录期间必须提供第二个因素。

#### Scenario: 需要OTP
- **WHEN** 提供了有效的凭据
- **THEN** 需要进行 OTP 挑战
EOF

# 5) 验证
openspec validate $CHANGE --strict
```

***

## 多能力示例 (Multi-Capability Example)

```
openspec/changes/add-2fa-notify/
├── proposal.md
├── tasks.md
├── docs/
│   ├── ITERATION_LOG.md
│   └── RESEARCH.md
└── specs/
    ├── auth/
    │   └── spec.md   # ADDED: 双重身份验证
    └── notifications/
        └── spec.md   # ADDED: OTP 邮件通知
```

auth/spec.md

```markdown
## ADDED Requirements

### Requirement: 双重身份验证

...
```

notifications/spec.md

```markdown
## ADDED Requirements

### Requirement: OTP 邮件通知

...
```

***

## 最佳实践

### 简单优先(Simplicity First)

- 默认新增代码控制在 100 行以内。

- 优先采用单文件实现，直到证明不足为止。

- 在没有明确理由的情况下避免引入框架。

- 选择乏味且成熟的模式。

- 首先应用 KISS/YAGNI；仅在有证据支撑时才引入抽象。

### 复杂性触发条件

仅在满足以下条件时才增加复杂性：

- 性能数据表明当前方案太慢。

- 具体的规模需求（>1000 用户，>100MB 数据）。

- 多个成熟的用例确实需要抽象。

- 安全/合规要求使得必须进行结构性变更。

### 清晰的引用

- 代码位置使用 `file.ts:42` 格式。

- 规范引用格式为 `specs/auth/spec.md`。

- 链接相关的变更和 PR。

- 在提案的"调研 (Research)"中，始终为每个关键声明包含"证据指针"。

- 迭代日志中必须包含完整的决策依据引用。

### 能力命名

- 使用"动词-名词"：`user-auth`, `payment-capture`。

- 每项能力单一用途。

- 10 分钟理解原则。

- 如果描述中需要使用 "AND"，请进行拆分。

### 变更 ID 命名

- 使用 kebab-case，简短且具描述性：`add-two-factor-auth`。

- 优先使用动词开头的前缀：`add-`, `update-`, `remove-`, `refactor-`。

- 确保唯一性；如果已被占用，请附加 `-2`, `-3` 等。

***

## 工具选择指南

| 任务             | 工具                       | 原因              |
| :------------- | :----------------------- | :-------------- |
| 仓库/代码探索、重构映射   | MCP: serena              | 快速 + 精确的代码导航和证据 |
| 多步计划/ 分解       | MCP: sequential-thinking | 防止遗漏步骤并提高任务原子性  |
| API/文档验证（框架/库） | MCP: context7            | 减少幻觉和版本不匹配      |
| 按模式查找文件        | Glob                     | 快速模式匹配          |
| 搜索代码内容         | Grep                     | 优化的正则搜索         |
| 读取特定文件         | Read                     | 直接访问文件          |
| 探索未知范围         | Task                     | 多步调查            |

### 工具使用优先级

- **文件查找、代码检索、读取文件**：优先使用 `serena`，系统工具作为兜底

- **文档内容搜索**：优先使用 `serena`，`rg`/`grep` 作为备用

- **目录结构探索**：优先使用 `serena`，`ls`/`tree` 作为备用

***

## 错误恢复 (Error Recovery)

### 变更冲突

1. 运行 `openspec list` 以查看活跃变更。
2. 检查是否有重叠的规范。
3. 与变更负责人进行协调。
4. 考虑合并提案。

### 验证失败

1. 使用 `--strict` 标志运行。
2. 查看 JSON 输出中的详情。
3. 验证规范文件格式。
4. 确保场景格式正确。

### 缺少上下文

1. 首先阅读 `project.md`。
2. 检查相关规范。
3. 查看最近的归档。
4. 寻求澄清。

### 迭代日志问题

1. 检查 `docs/ITERATION_LOG.md` 是否存在且格式正确
2. 验证 `proposal.md` 中是否包含"迭代概览"章节
3. 确保所有版本引用正确
4. 使用基础验证命令检查同步状态

***

## 快速参考 (Quick Reference)

### 阶段指示器

- `changes/` - 已提议，尚未构建。

- `specs/` - 已构建并部署。

- `archive/` - 已完成的变更。

### 文件用途

详细目录结构和文件说明见 [目录结构](#目录结构-directory-structure) 章节。

### CLI 核心

详细命令说明见 [快速开始](#快速开始-quick-start) 章节。

```bash
openspec list                          # 正在进行什么？
openspec show [item]                   # 查看详情
openspec validate --strict             # 是否正确？
openspec archive <change-id> [--yes]   # 标记为已完成
```

**记住：规范 (Specs) 即真相。变更 (Changes) 是提案。保持它们同步。**

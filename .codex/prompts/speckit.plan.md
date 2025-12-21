---
description: 使用计划模板执行实施规划工作流以生成设计文档。
handoffs:
    - label: 创建任务
      agent: speckit.tasks
      prompt: 将计划分解为任务
      send: true
    - label: 创建检查清单
      agent: speckit.checklist
      prompt: 为以下领域创建检查清单...
---

## 语言期望

-   此命令文件中的规划时消息和解释是用英文编写的，但是：
    -   生成的设计文档（`research.md`，`data-model.md`，`quickstart.md` 等）
        **应该**使用中文编写针对用户或利益相关者的叙述性文本。
    -   诸如 OpenAPI/GraphQL 模式之类的契约**可以**保留标准英文命名。
    -   文件路径、命令和代码片段保留其原始语言。

## 用户输入

```text
$ARGUMENTS

```

在继续之前（如果不为空），你**必须**考虑用户输入。

## 概要

1. **设置**：从仓库根目录运行 `.specify/scripts/bash/setup-plan.sh --json` 并解析 JSON 以获取 FEATURE_SPEC, IMPL_PLAN, SPECS_DIR, 和 FEATURE_NAME。对于像 "I'm Groot" 这样的参数中的单引号，请使用转义语法：例如 'I'''m Groot'（或者如果可能的话使用双引号："I'm Groot"）。
2. **加载上下文**：读取 FEATURE_SPEC 和 `.specify/memory/constitution.md`。加载 IMPL_PLAN 模板（已复制）。
3. **执行计划工作流**：遵循 IMPL_PLAN 模板中的结构以：

-   填写技术上下文（将未知数标记为 "NEEDS CLARIFICATION"）
-   填写来自宪章的宪章检查部分
-   评估门控（如果违规未被证明合理则报错）
-   阶段 0：生成 research.md（解决所有 NEEDS CLARIFICATION）
-   阶段 1：生成 data-model.md, contracts/, quickstart.md
-   阶段 1：通过运行代理脚本更新代理上下文
-   设计后重新评估宪章检查

4. **停止并报告**：命令在阶段 2 规划后结束。报告功能名称、IMPL_PLAN 路径和生成的文档。

## 阶段

### 阶段 0：大纲与研究

#### MCP 使用要求 (必需)

-   在生成 `research.md` 或做出关键技术决策之前，规划者**应该**：

1. 使用 `sequential-thinking` 来：

-   将每个 NEEDS CLARIFICATION 分解为具体的研究问题。
-   按影响、风险和依赖关系进行优先排序。

2. 使用 `context7` 来：

-   查阅官方或权威来源。
-   在 `research.md` 中捕获 URL/版本/日期和关键结论。

3. 使用 `serena` 来：

-   协调计划的架构与当前的仓库结构和惯例。

1. **从上方的技术上下文中提取未知数**：

-   对于每个 NEEDS CLARIFICATION → 研究任务
-   对于每个依赖项 → 最佳实践任务
-   对于每个集成 → 模式任务

2. **生成并分派研究代理**：

```text
对于技术上下文中的每个未知数：
  任务: "Research {unknown} for {feature context}"
对于每个技术选择：
  任务: "Find best practices for {tech} in {domain}"

```

3. **在 `research.md` 中整合发现**，使用格式：

-   决策：[选择了什么]
-   理由：[为什么选择]
-   考虑的替代方案：[评估了其他什么]

**输出**：research.md，解决了所有 NEEDS CLARIFICATION

### 阶段 1：设计与契约

**先决条件：** `research.md` 完成

1. **从功能规范中提取实体** → `data-model.md`：

-   实体名称、字段、关系
-   来自需求的验证规则
-   状态转换（如果适用）

2. **从功能需求生成 API 契约**：

-   对于每个用户动作 → 端点
-   使用标准 REST/GraphQL 模式
-   输出 OpenAPI/GraphQL 模式到 `/contracts/`

3. **代理上下文更新**：

-   运行 `.specify/scripts/bash/update-agent-context.sh codex`
-   这些脚本检测正在使用哪个 AI 代理
-   更新适当的代理特定上下文文件
-   仅添加当前计划中的新技术
-   保留标记之间的手动添加

**输出**：data-model.md, /contracts/\*, quickstart.md, 代理特定文件

## 关键规则

-   使用绝对路径
-   在门控失败或未解决的澄清上报错
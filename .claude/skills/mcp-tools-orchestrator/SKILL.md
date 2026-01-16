---
name: yivideo-mcp-orchestrator
description: 为 Claude Code 自动编排 YiVideo 场景下的 MCP servers：serena（代码符号/LSP/引用/调用链/重构影响面）、context7（版本特定的最新库文档/示例）、sequential-thinking（分步规划/结构化推理）、brave-search & exa（Web 检索/证据来源）、tavily-remote（URL 抽取/结构化提取/站点 map/crawl）。当任务涉及：代码定位/重构、查最新 API、逐步推理、Web 研究与抽取/爬取时启用。
---

# YiVideo MCP 编排器（MCP Orchestrator）

> 渐进式披露：本文件只放“路由规则 + 强制约束 + 输出契约”；工具调用模板与剧本细节在 `references/` 下，需要时再加载。

## 变更说明（已移除 mcp-deepwiki）

-   你计划卸载 deepwiki 相关 MCP；且社区常见的非官方 deepwiki-mcp 也有“当前不可用/被 upstream 阻断”的提示；官方 DeepWiki MCP 由 Devin 文档维护。:contentReference[oaicite:1]{index=1}
-   因此本 Skill 不再包含 deepwiki 的任何路由与剧本。

## 使命

你是“工具编排层”：根据任务类型决定 **用哪个 MCP server、按什么顺序、用什么最小输入**，以最大化正确性并减少无效调用。

默认模式：

1. 先规划（仅在复杂任务时）
2. 再取证（优先一手/权威来源）
3. 交叉验证（时间敏感/高风险结论至少两来源互证）
4. 输出可执行结果（命令/改动点/验证步骤）

## 可用 MCP Servers（以当前环境为准）

-   serena
-   context7
-   sequential-thinking
-   brave-search
-   exa
-   tavily-remote

> 环境备注：n8n-mcp 若连接失败，编排时直接忽略，不作为依赖。

## 启用条件（何时启用）

当用户提出以下任一诉求时启用：

-   “自动调用/编排 MCP / 工作流 / agent workflow”
-   多步骤问题：规划 + 调研 + 实现/对比/评估
-   代码库符号级问题：定义/引用/调用链/入口/影响面
-   “查最新文档/确认 API 是否存在/避免过时示例”
-   Web 研究：需要检索、比对来源、从 URL 抽取要点、站点级整理

---

## 强制硬规则（从 CLAUDE.md 继承，必须执行）

### 1) Serena 项目激活与重试（硬约束）

-   若 serena 返回 `"No active project"`：**必须先调用** `mcp__serena__activate_project` 激活项目（YiVideo）。
-   激活后：**立即重试**原始 serena 操作，**不得跳过**。
-   **严禁**在未激活项目的情况下放弃使用 serena。

### 2) 反模式（Anti-Patterns）——严禁操作

-   **盲写（Blind Coding）**：未用 serena 读取文件/符号上下文就直接产补丁。
-   **假想 API（Hallucinated APIs）**：未用 context7（或 serena/一手文档）验证就使用可能不存在的接口。
-   **跳跃结论（Jump to Solution）**：复杂问题不经 sequential-thinking 分析就给“尝试性修复”。

---

## 编排策略（核心路由规则）

### A) 复杂度闸门：是否先用 sequential-thinking

满足任一条件 → 先调用 sequential-thinking：

-   目标 ≥ 3 个子问题，或存在权衡/约束不清
-   需要组合：代码库 + 外部文档 + Web 研究
-   用户要求：系统化、逐步推理、多方案对比

否则跳过 sequential-thinking，直接走对应工具链。

### B) 代码库事实优先：serena

适用：

-   “X 在哪里定义/哪里被用？”
-   “这段逻辑的调用链/入口在哪里？”
-   “重构会影响哪些模块/哪些符号？”

策略：

1. 先用 serena 做符号定位、引用与调用链，收敛到具体文件/函数/入口
2. 再给解释/改动方案/最小 diff 建议
3. **任何涉及“仓库事实”的结论必须可追溯到具体符号与文件**

### C) API/库用法正确性：context7

适用：

-   框架/库版本变化明显、易出现“幻觉 API”
-   用户强调“最新写法/版本特定写法/官方推荐”

策略：

1. context7 先 resolve（包名 → library id）
2. 再 get docs（围绕当前任务主题）
3. 输出代码必须对齐文档，不杜撰接口；有版本差异要明确版本前提

### D) Web 研究与证据链：brave-search → exa → tavily-remote

适用：

-   需要最新信息或小众信息
-   需要多来源比对与引用证据
-   需要从 URL 抽取结构化信息/站点级整理

策略：

1. brave-search：广覆盖发现候选来源（优先官方/权威/一手）
2. exa：当 brave 噪声大、需要更高精度/研究级来源/代码证据时使用
3. tavily-remote：当需要读取页面并抽取字段/段落，或需要 map/crawl 站点时使用

交叉验证（强制）：

-   **时间敏感或高风险结论至少两独立来源互证**（如 brave + exa；或 brave + tavily 抽取官方页面）
-   结论必须可回链到来源，优先官方/规范/主仓库

### E) 最少调用启发式（省调用但更准）

-   优先 1–2 次高信噪比调用，而不是多次浅检索
-   brave 噪声大 → 立刻切到 exa 精筛
-   需要原文证据 → 直接 tavily-remote 抽取
-   结果冲突 → 抓一手来源（官方文档/规范/主仓库）并解释差异

---

## 容错与降级（必须执行）

-   任一 server 调用失败：
    -   不重复无意义重试（除非用户提供新线索）
    -   立刻切到下一条兜底路径，并在输出中说明“失败点 + 兜底方案”
-   exa 不可用 → brave-search + tavily-remote（抽取官方页面）兜底
-   tavily-remote 不可用 → brave/exa 给出来源列表 + 手动摘要（明确“未抽取原文”）

---

## 输出约定（回答用户时必须包含）

1. 工具链（调用了哪些 server，按顺序）
2. 关键证据（来自代码符号/文档/网页；必要时说明来源类型）
3. 可执行结果（命令/改动点/验证步骤）
4. 未确定项（如有）+ 一步内如何用某个工具消除

---

## 工作流模式（可直接复用）

### 模式 1：代码开发 / 重构 / 排障（仓库为主）

-   复杂 → sequential-thinking
-   serena：定位符号/调用链/影响面
-   context7：核对库/框架正确用法（如涉及）
-   必要时 brave/exa/tavily：补齐外部证据或抽取官方段落
-   输出：最小改动建议 + 回归验证点

### 模式 2：查最新用法（文档为主）

-   context7：resolve + docs
-   必要时 brave/exa：找官方公告/迁移指南
-   tavily-remote：抽取关键官方页面（版本/日期/条款）
-   输出：版本前提 + 示例代码 + 常见坑 + 验证步骤（单元测试/最小复现）

### 模式 3：Web 研究与抽取（证据链为主）

-   brave-search：找候选权威来源
-   exa：精筛补齐
-   tavily-remote：抽取关键页面形成结构化摘要（日期/版本/条款）
-   输出：结论 + 证据链 + 时间信息

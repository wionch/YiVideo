---
name: yivideo-conventional-commits
description: 为 YiVideo 生成规范的 Git commit message 与 PR 描述（Conventional Commits）。当你让我“写提交信息/commit message/PR 标题/PR 描述/变更摘要/changelog”时启用。强制使用 feat/fix/refactor/docs/style 前缀并给出可直接复制的最终文本。
---

# YiVideo Conventional Commits（提交信息/PR 文案）

## 适用范围

当用户要求：

-   生成 **commit message**
-   生成 **PR 标题/PR 描述**
-   生成 **变更摘要**（可用于 release note/changelog）

必须应用本 Skill。

## 核心规范（YiVideo 项目约束）

生成 commit message 或 PR 描述时，必须遵循以下类型前缀（项目强制）：

-   `feat: <描述>`（新功能）
-   `fix: <描述>`（Bug 修复）
-   `refactor: <描述>`（重构，不改变行为）
-   `docs: <描述>`（文档更新）
-   `style: <描述>`（格式化）

> 以上类型来自项目 CLAUDE.md 约束，不要擅自引入 chore/test/build 等类型，除非用户明确要求或项目另有说明。

## 输出格式（严格）

### A) Commit message

只输出**一行**（可直接复制），格式：
`<type>: <动词开头的简短中文描述>`

要求：

-   冒号后必须有一个半角空格（Conventional Commits 基本规则）。
-   描述要具体可检验：避免“修复一些问题/优化代码”等空泛措辞。
-   默认用中文描述，除非用户明确要求英文。

示例：

-   `feat: 新增批处理任务的失败重试配置`
-   `fix: 修复 API 网关在空请求体时的 422 异常`
-   `refactor: 重构工作流节点解析以减少重复逻辑`
-   `docs: 更新本地开发环境说明`
-   `style: 统一导入排序并移除多余空行`

### B) PR 标题

PR 标题按 commit message 同格式输出（同一行可复制）：
`<type>: <描述>`

### C) PR 描述（结构化）

输出以下小节（无则写“无”）：

-   背景/目标
-   主要改动
-   影响范围（模块/接口/配置）
-   风险与回滚方案
-   测试与验证（如果涉及代码改动，必须写清如何验证；若无法验证则写“未验证 + 原因 + 建议验证方式”）

## 选择类型的判定规则

-   新增能力/对外行为新增 → `feat`
-   修复缺陷/行为更正 → `fix`
-   内部结构调整且不改变对外行为 → `refactor`
-   仅文档/注释/README → `docs`
-   仅格式化/lint/空白/不影响逻辑 → `style`

## 交互策略

如信息不足以写出精确描述：

-   先基于已知信息给出一个“最小可用”的标题
-   再列出 2–3 个需要补齐的要点（例如：影响模块名、核心变更点、验证方式），方便用户快速补充

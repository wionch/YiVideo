---
description: 基于可用的设计文档，将现有任务转换为该功能的可操作、按依赖顺序排列的 GitHub Issues。
tools: ['github/github-mcp-server/issue_write']
---

## 用户输入

```text
$ARGUMENTS
```

在继续之前（如果不为空），你**必须**考虑用户输入。

## 概要

1. 从仓库根目录运行 `.specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks` 并解析 FEATURE_DIR 和 AVAILABLE_DOCS 列表。所有路径必须是绝对路径。对于像 "I'm Groot" 这样的参数中的单引号，请使用转义语法：例如 'I'\''m Groot'（或者如果可能的话使用双引号："I'm Groot"）。
2. 从执行的脚本中，提取 **tasks** 的路径。
3. 通过运行以下命令获取 Git 远程地址：

```bash
git config --get remote.origin.url
```

> [!CAUTION]
> 仅当远程地址是 GITHUB URL 时才继续执行下一步

4. 对于列表中的每个任务，使用 GitHub MCP 服务器在代表 Git 远程的仓库中创建一个新 Issue。

> [!CAUTION]
> 在任何情况下，都不要在与远程 URL 不匹配的仓库中创建 ISSUE

--- 
description: 通过处理并执行 tasks.md 中定义的所有任务来执行实施计划。
---

## 语言期望

- 在实施过程中向用户显示的所有交互式消息、解释和摘要必须使用中文，除了：
    - 文件路径、命令、代码片段和专有技术名称。
- 此命令描述和本文件中的规则保留英文，但与用户的运行时交互（问题、确认、状态报告）**必须**用中文生成。

## 用户输入

```text
$ARGUMENTS
```

在继续之前（如果不为空），你**必须**考虑用户输入。

## 概要

1. 从仓库根目录运行 `.specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks` 并解析 FEATURE_DIR 和 AVAILABLE_DOCS 列表。所有路径必须是绝对路径。对于像 "I'm Groot" 这样的参数中的单引号，请使用转义语法：例如 'I'\''m Groot'（或者如果可能的话使用双引号："I'm Groot"）。

2. **检查检查清单状态**（如果 FEATURE_DIR/checklists/ 存在）：

    - 扫描 checklists/ 目录中的所有检查清单文件
    - 对于每个检查清单，统计：
        - 总项目数：所有匹配 `- [ ]` 或 `- [X]` 或 `- [x]` 的行
        - 已完成项目数：匹配 `- [X]` 或 `- [x]` 的行
        - 未完成项目数：匹配 `- [ ]` 的行
    - 创建状态表：

        ```text
        | Checklist | Total | Completed | Incomplete | Status |
        |-----------|-------|-----------|------------|--------|
        | ux.md     | 12    | 12        | 0          | ✓ PASS |
        | test.md   | 8     | 5         | 3          | ✗ FAIL |
        | security.md | 6   | 6         | 0          | ✓ PASS |
        ```

    - 计算总体状态：

        - **PASS**：所有检查清单都有 0 个未完成项目
        - **FAIL**：一个或多个检查清单有未完成项目

    - **如果有任何检查清单未完成**：

        - 显示带有未完成项目计数的表格
        - **停止**并（用中文）询问：“部分检查清单未完成。您是否仍要继续实施？(yes/no)”
        - 在继续之前等待用户响应
        - 如果用户说“no”或“wait”或“stop”，停止执行
        - 如果用户说“yes”或“proceed”或“continue”，继续执行第 3 步

    - **如果所有检查清单已完成**：
        - 显示显示所有检查清单通过的表格
        - 自动继续执行第 3 步

3. 加载并分析实施上下文：

    - **必需**：读取 tasks.md 以获取完整的任务列表和执行计划
    - **必需**：读取 plan.md 以获取技术栈、架构和文件结构
    - **如果存在**：读取 data-model.md 以获取实体和关系
    - **如果存在**：读取 contracts/ 以获取 API 规范和测试要求
    - **如果存在**：读取 research.md 以获取技术决策和约束
    - **如果存在**：读取 quickstart.md 以获取集成场景

4. **项目设置验证**：

    - **必需**：根据实际项目设置创建/验证忽略文件：

    **检测和创建逻辑**：

    - 检查以下命令是否成功以确定仓库是否为 git 仓库（如果是，创建/验证 .gitignore）：

        ```sh
        git rev-parse --git-dir 2>/dev/null
        ```

    - 检查 Dockerfile* 是否存在或 plan.md 中有 Docker → 创建/验证 .dockerignore
    - 检查 .eslintrc* 是否存在 → 创建/验证 .eslintignore
    - 检查 eslint.config.* 是否存在 → 确保配置的 `ignores` 条目涵盖所需模式
    - 检查 .prettierrc* 是否存在 → 创建/验证 .prettierignore
    - 检查 .npmrc 或 package.json 是否存在 → 创建/验证 .npmignore（如果发布）
    - 检查 terraform 文件 (*.tf) 是否存在 → 创建/验证 .terraformignore
    - 检查是否需要 .helmignore（存在 helm 图表）→ 创建/验证 .helmignore

    **如果忽略文件已存在**：验证它是否包含基本模式，仅追加缺失的关键模式
    **如果忽略文件缺失**：为检测到的技术创建具有完整模式集的文件

    **按技术分类的常见模式**（来自 plan.md 技术栈）：

    - **Node.js/JavaScript/TypeScript**: `node_modules/`, `dist/`, `build/`, `*.log`, `.env*`
    - **Python**: `__pycache__/`, `*.pyc`, `.venv/`, `venv/`, `dist/`, `*.egg-info/`
    - **Java**: `target/`, `*.class`, `*.jar`, `.gradle/`, `build/`
    - **C#/.NET**: `bin/`, `obj/`, `*.user`, `*.suo`, `packages/`
    - **Go**: `*.exe`, `*.test`, `vendor/`, `*.out`
    - **Ruby**: `.bundle/`, `log/`, `tmp/`, `*.gem`, `vendor/bundle/`
    - **PHP**: `vendor/`, `*.log`, `*.cache`, `*.env`
    - **Rust**: `target/`, `debug/`, `release/`, `*.rs.bk`, `*.rlib`, `*.prof*`, `.idea/`, `*.log`, `.env*`
    - **Kotlin**: `build/`, `out/`, `.gradle/`, `.idea/`, `*.class`, `*.jar`, `*.iml`, `*.log`, `.env*`
    - **C++**: `build/`, `bin/`, `obj/`, `out/`, `*.o`, `*.so`, `*.a`, `*.exe`, `*.dll`, `.idea/`, `*.log`, `.env*`
    - **C**: `build/`, `bin/`, `obj/`, `out/`, `*.o`, `*.a`, `*.so`, `*.exe`, `Makefile`, `config.log`, `.idea/`, `*.log`, `.env*`
    - **Swift**: `.build/`, `DerivedData/`, `*.swiftpm/`, `Packages/`
    - **R**: `.Rproj.user/`, `.Rhistory`, `.RData`, `.Ruserdata`, `*.Rproj`, `packrat/`, `renv/`
    - **通用**: `.DS_Store`, `Thumbs.db`, `*.tmp`, `*.swp`, `.vscode/`, `.idea/`

    **工具特定模式**：

    - **Docker**: `node_modules/`, `.git/`, `Dockerfile*`, `.dockerignore`, `*.log*`, `.env*`, `coverage/`
    - **ESLint**: `node_modules/`, `dist/`, `build/`, `coverage/`, `*.min.js`
    - **Prettier**: `node_modules/`, `dist/`, `build/`, `coverage/`, `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`
    - **Terraform**: `.terraform/`, `*.tfstate*`, `*.tfvars`, `.terraform.lock.hcl`
    - **Kubernetes/k8s**: `*.secret.yaml`, `secrets/`, `.kube/`, `kubeconfig*`, `*.key`, `*.crt`

5. 解析 tasks.md 结构并提取：
    - **任务阶段**：设置、测试、核心、集成、完善
    - **任务依赖**：顺序 vs 并行执行规则
    - **任务详情**：ID、描述、文件路径、并行标记 [P]
    - **执行流程**：顺序和依赖要求

5.5. **每个任务的 MCP 使用优先级 (必需)**

- 在从 `tasks.md` 编辑给定任务的任何文件之前，执行者必须按此顺序：
    1. 使用 `sequential-thinking`（如果可用）来：
        - 可选地将任务细化为 1–3 个更小的子步骤。
        - 确认相对于其他任务的依赖关系和顺序。
    2. 使用 `serena`（如果可用）来：
        - 定位要触及的精确文件/符号/引用。
        - 检查可能被无意影响的附近代码。
    3. 使用 `context7`（如果需要）来：
        - 查阅外部文档、标准或最佳实践。
        - 记录链接/版本和关键结论以供稍后审查。
- 如果在预期时任何这些 MCP 服务不可用：
    -   执行者必须在实施日志中或作为显式注释记录：
        -   预期哪个服务，
        -   为什么无法使用，
        -   以及使用了哪些替代信息源。
    -   任务不得静默跳过此 MCP 步骤。

6. 按照任务计划执行实施：

    - **分阶段执行**：完成每个阶段后再进入下一个阶段
    - **尊重依赖**：按顺序运行顺序任务，并行任务 [P] 可以一起运行
    - **遵循 TDD 方法**：在相应的实施任务之前执行测试任务
    - **基于文件的协调**：影响相同文件的任务必须顺序运行
    - **验证检查点**：在继续之前验证每个阶段的完成情况

7. 实施执行规则：

    - **设置优先**：初始化项目结构、依赖项、配置
    - **代码前测试**：如果需要为合约、实体和集成场景编写测试
    - **核心开发**：实现模型、服务、CLI 命令、端点
    - **集成工作**：数据库连接、中间件、日志记录、外部服务
    - **完善和验证**：单元测试、性能优化、文档

8. 进度跟踪和错误处理：

    - 在每个完成的任务后报告进度
    - 如果任何非并行任务失败，停止执行
    - 对于并行任务 [P]，继续执行成功的任务，报告失败的任务
    - 提供带有上下文的清晰错误消息以进行调试
    - 如果实施无法继续，建议下一步
    - **重要** 对于已完成的任务，请确保在任务文件中将任务标记为 [X]。

9. 完成验证：
    - 验证所有必需的任务均已完成
    - 检查实施的功能是否符合原始规范
    - 验证测试通过且覆盖率满足要求
    - 确认实施遵循技术计划
    - 报告最终状态并总结已完成的工作

注意：此命令假设 tasks.md 中存在完整的任务分解。如果任务不完整或缺失，建议先运行 `/speckit.tasks` 以重新生成任务列表。
# YiVideo 项目宪法

## 核心原则

### I. 核心架构与开发模式 (Core Architecture & Development Model)
- **架构**: 严格遵循微服务架构。所有新功能必须作为独立的、可解耦的服务或在现有服务内以模块化方式实现。
- **开发模式**: 坚持“配置而非编码”。优先通过扩展工作流配置（JSON/YAML）来满足需求，代码是最后的手段。
- **动态工作流**: 所有业务逻辑必须通过动态工作流引擎（`api_gateway`）进行编排。

### II. 技术栈与规范 (Tech Stack & Standards)
- **语言**: Python 3.11+
- **核心框架**: Docker, Docker Compose, Celery, Redis
- **代码风格**: 遵循 PEP 8，使用 Black 和 isort 进行格式化。
- **依赖管理**: 各容器使用 `requirements.txt`。新增依赖需经过审查。

### III. 开发规范 (Development Norms)
- **SOLID**: 所有代码设计必须严格遵循 SOLID 原则。
- **YAGNI**: 所有代码设计必须严格遵循YAGNI原则, 拒绝过度设计。
- **KISS**: 所有实现必须保持最简单、最易读，禁止炫技式抽象。
- **代码组织**: 遵循 `/mnt/d/WSL2/docker/YiVideo/CLAUDE.md` 中定义的目录结构。新文件和模块必须放置在正确的位置。

### IV. 文档与输出 (Documentation & Output)
- **语言**: 所有由 `spec-kit` 生成的文档（`spec.md`, `plan.md`, `tasks.md`）以及代码注释、Commit Message **必须**使用**简体中文**。
- **Commit Message**: 遵循 Conventional Commits 规范。

### V. MCP 服务集成 (MCP Service Integration)
- **强制要求**: 在 `spec-kit` 工作流的相应阶段，必须优先调用以下 MCP 服务来提升效率和质量。
- **`spec` 阶段**:
    - 在生成初始需求规格 (`spec.md`) 时，**优先**利用代码分析 MCP (`serena` 等) 理解现有代码库，并查询知识库 MCP (如 `context7`) 以确保上下文的准确性和一致性。
    - 对于复杂需求，**推荐**使用 `sequential-thinking` 作为“结构化分解器”，在填充模板前对原始需求进行逻辑梳理，确保最终产出的 `spec.md` 结构清晰、覆盖全面。
- **`clarify` 阶段**:
    - 在澄清需求时，**优先**调用专门的需求分析专家模型 MCP，并结合实时代码上下文 (`serena`) 来提出具体、深刻的问题，而不是泛泛而谈。
    - 对于复杂的待澄清问题，**推荐**使用 `sequential-thinking` 作为“深度探查器”，在提问前对技术和业务的权衡进行分析，从而引导用户做出更明智的决策。
- **`plan` 阶段**:
    - 在进行技术规划和选型时，**优先**使用 `serena` (`get_symbols_overview`, `find_symbol`) 分析现有代码库，确保新设计与旧代码兼容。
    - 在涉及外部库或 API 时，**优先**使用 `context7` (`get_library_docs`) 获取最新文档。
    - 对于从需求到技术方案的转换过程，**推荐**使用 `sequential-thinking` 作为“架构设计推理引擎”，对技术选型、架构模式和 API 设计进行系统性权衡与推理，确保技术方案的深度和远见。
- **`tasks` 阶段**:
    - 在将 `plan.md` 分解为 `tasks.md` 时，**优先**使用 `sequential-thinking` 进行逻辑推理，以确保任务分解的合理性、依赖关系的正确性。
- **`implement` 阶段**:
    - 在执行代码修改时，**优先**优先使用 `serena` 的符号编辑工具（`replace_symbol_body`, `insert_after_symbol`, `rename_symbol`），而不是进行手动的字符串替换。

## 治理 (Governance)
- **合规性**: 所有 Pull Requests 和代码审查都必须验证是否符合本宪法。任何复杂性或对原则的偏离都必须有充分的理由。
- **修订流程**: 对本宪法的任何修订都需要更新此文档，并通过团队评审。版本号必须遵循语义化版本控制规则进行更新。
- **版本控制**:
    - **MAJOR**: 删除了原则或进行了不向后兼容的治理变更。
    - **MINOR**: 增加了新的原则或对现有指导进行了实质性扩展。
    - **PATCH**: 澄清、修正错别字或非语义性的优化。

**版本**: v1.1.0 | **批准日期**: 2025-11-06 | **最后修订**: 2025-11-06

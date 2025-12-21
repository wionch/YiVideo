---
description: Generate an actionable, dependency-ordered tasks.md for the feature based on available design artifacts.
handoffs:
    - label: Analyze For Consistency
      agent: speckit.analyze
      prompt: Run a project analysis for consistency
      send: true
    - label: Implement Project
      agent: speckit.implement
      prompt: Start the implementation in phases
      send: true
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Outline

1. **Setup**: Run `.specify/scripts/bash/check-prerequisites.sh --json` from repo root and parse FEATURE_DIR and AVAILABLE_DOCS list. All paths must be absolute. For single quotes in args like "I'm Groot", use escape syntax: e.g 'I'\''m Groot' (or double-quote if possible: "I'm Groot").

2. **Load design documents**: Read from FEATURE_DIR:

    - **Required**: plan.md (tech stack, libraries, structure), spec.md (user stories with priorities)
    - **Optional**: data-model.md (entities), contracts/ (API endpoints), research.md (decisions), quickstart.md (test scenarios)
    - Note: Not all projects have all documents. Generate tasks based on what's available.

3. **Execute task generation workflow**:

    - Load plan.md and extract tech stack, libraries, project structure
    - Load spec.md and extract user stories with their priorities (P1, P2, P3, etc.)
    - If data-model.md exists: Extract entities and map to user stories
    - If contracts/ exists: Map endpoints to user stories
    - If research.md exists: Extract decisions for setup tasks
    - Generate tasks organized by user story (see Task Generation Rules below)
    - Generate dependency graph showing user story completion order
    - Create parallel execution examples per user story
    - Validate task completeness (each user story has all needed tasks, independently testable)

4. **Generate tasks.md**: Use `.specify/templates/tasks-template.md` as structure, fill with:

    - Correct feature name from plan.md
    - Phase 1: Setup tasks (project initialization)
    - Phase 2: Foundational tasks (blocking prerequisites for all user stories)
    - Phase 3+: One phase per user story (in priority order from spec.md)
    - Each phase includes: story goal, independent test criteria, tests (if requested), implementation tasks
    - Final Phase: Polish & cross-cutting concerns
    - All tasks must follow the strict checklist format (see Task Generation Rules below)
    - Clear file paths for each task
    - Dependencies section showing story completion order
    - Parallel execution examples per story
    - Implementation strategy section (MVP first, incremental delivery)

5. **Report**: Output path to generated tasks.md and summary:
    - Total task count
    - Task count per user story
    - Parallel opportunities identified
    - Independent test criteria for each story
    - Suggested MVP scope (typically just User Story 1)
    - Format validation: Confirm ALL tasks follow the checklist format (checkbox, ID, labels, file paths)

Context for task generation: $ARGUMENTS

The tasks.md should be immediately executable - each task must be specific enough that an LLM can complete it without additional context.

### Language expectations

-   All user-facing task descriptions, section titles, and explanations in the generated `tasks.md`
    MUST be written in Chinese, unless they are:
    -   File paths, commands, code snippets, or proper technical names (library/framework/protocol names).
-   The command description and rules in this file remain in English, but the produced artifact
    (`tasks.md`) is expected to be in Chinese.

## Task Generation Rules

**CRITICAL**: Tasks MUST be organized by user story to enable independent implementation and testing.

**Tests are OPTIONAL**: Only generate test tasks if explicitly requested in the feature specification or if user requests TDD approach.

### Checklist Format (REQUIRED)

Every task MUST strictly follow this format:

```text
- [ ] [TaskID] [P?] [Story?] Description with file path
```

**Format Components**:

1. **Checkbox**: ALWAYS start with `- [ ]` (markdown checkbox)
2. **Task ID**: Sequential number (T001, T002, T003...) in execution order
3. **[P] marker**: Include ONLY if task is parallelizable (different files, no dependencies on incomplete tasks)
4. **[Story] label**: REQUIRED for user story phase tasks only
    - Format: [US1], [US2], [US3], etc. (maps to user stories from spec.md)
    - Setup phase: NO story label
    - Foundational phase: NO story label
    - User Story phases: MUST have story label
    - Polish phase: NO story label
5. **Description**: Clear action with exact file path

**Examples**:

-   ✅ CORRECT: `- [ ] T001 Create project structure per implementation plan`
-   ✅ CORRECT: `- [ ] T005 [P] Implement authentication middleware in src/middleware/auth.py`
-   ✅ CORRECT: `- [ ] T012 [P] [US1] Create User model in src/models/user.py`
-   ✅ CORRECT: `- [ ] T014 [US1] Implement UserService in src/services/user_service.py`
-   ❌ WRONG: `- [ ] Create User model` (missing ID and Story label)
-   ❌ WRONG: `T001 [US1] Create model` (missing checkbox)
-   ❌ WRONG: `- [ ] [US1] Create User model` (missing Task ID)
-   ❌ WRONG: `- [ ] T001 [US1] Create model` (missing file path)

### Task Organization

1. **From User Stories (spec.md)** - PRIMARY ORGANIZATION:

    - Each user story (P1, P2, P3...) gets its own phase
    - Map all related components to their story:
        - Models needed for that story
        - Services needed for that story
        - Endpoints/UI needed for that story
        - If tests requested: Tests specific to that story
    - Mark story dependencies (most stories should be independent)

2. **From Contracts**:

    - Map each contract/endpoint → to the user story it serves
    - If tests requested: Each contract → contract test task [P] before implementation in that story's phase

3. **From Data Model**:

    - Map each entity to the user story(ies) that need it
    - If entity serves multiple stories: Put in earliest story or Setup phase
    - Relationships → service layer tasks in appropriate story phase

4. **From Setup/Infrastructure**:
    - Shared infrastructure → Setup phase (Phase 1)
    - Foundational/blocking tasks → Foundational phase (Phase 2)
    - Story-specific setup → within that story's phase

### Phase Structure

-   **Phase 1**: Setup (project initialization)
-   **Phase 2**: Foundational (blocking prerequisites - MUST complete before user stories)
-   **Phase 3+**: User Stories in priority order (P1, P2, P3...)
    -   Within each story: Tests (if requested) → Models → Services → Endpoints → Integration
    -   Each phase should be a complete, independently testable increment
-   **Final Phase**: Polish & Cross-Cutting Concerns

### Atomicity requirements for tasks (REQUIRED)

-   Each task MUST be atomic enough that it can be completed in a single, well‑scoped edit session,
    without relying on implicit context beyond what is referenced in the task itself.
-   A task MUST target at least one of the following granular “execution units”:
    -   Code-level unit: concrete file path PLUS a class/function/constant/module name, or a clearly
        described code block range.
    -   Documentation-level unit: concrete file path PLUS a heading level (H2/H3) and section title.
    -   Information-source unit: concrete URL/version/date PLUS a short list (≤ 5) of expected
        conclusion bullet points.
-   Each task description MUST explicitly include three aspects (they can be inline, but MUST be clear):
    -   **Input**: which files/symbols/decisions it depends on (paths or explicit references).
    -   **Output**: what new or modified content is expected (paths + symbols/sections).
    -   **Acceptance**: objective criteria to decide whether the task is complete (avoid vague wording
        like “looks better” or “more clear”).

### MCP usage requirements (REQUIRED)

-   When generating tasks, if there is any uncertainty about:
    -   where exactly in the codebase to apply a change,
    -   how to split work into atomic tasks,
    -   or which best practices to follow,
        the workflow MUST prefer using MCP services in this order:
    1. `sequential-thinking`: to decompose and order tasks, and to identify dependencies and risks.
    2. `serena`: to locate files/symbols/references and nearby implementation patterns in the repo.
    3. `context7`: to consult external authoritative sources and capture links/versions in decisions.
-   If MCP services are unavailable, the generator MUST add an explicit “note task” explaining:
    -   which MCP service was expected,
    -   why it could not be used,
    -   and which alternative information sources (files/commits/URLs) should be consulted instead.

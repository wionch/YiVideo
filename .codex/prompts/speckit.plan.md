---
description: Execute the implementation planning workflow using the plan template to generate design artifacts.
handoffs:
    - label: Create Tasks
      agent: speckit.tasks
      prompt: Break the plan into tasks
      send: true
    - label: Create Checklist
      agent: speckit.checklist
      prompt: Create a checklist for the following domain...
---

## Language expectations

-   Planning-time messages and explanations are written in English in this command file, but:
    -   The generated design artifacts (`research.md`, `data-model.md`, `quickstart.md`, etc.)
        SHOULD use Chinese for narrative text aimed at the user or stakeholders.
    -   Contracts such as OpenAPI/GraphQL schemas MAY keep standard English naming.
    -   File paths, commands, and code snippets remain in their original language.

## User Input

```text
$ARGUMENTS

```

You **MUST** consider the user input before proceeding (if not empty).

## Outline

1. **Setup**: Run `.specify/scripts/bash/setup-plan.sh --json` from repo root and parse JSON for FEATURE_SPEC, IMPL_PLAN, SPECS_DIR, and FEATURE_NAME. For single quotes in args like "I'm Groot", use escape syntax: e.g 'I'''m Groot' (or double-quote if possible: "I'm Groot").
2. **Load context**: Read FEATURE_SPEC and `.specify/memory/constitution.md`. Load IMPL_PLAN template (already copied).
3. **Execute plan workflow**: Follow the structure in IMPL_PLAN template to:

-   Fill Technical Context (mark unknowns as "NEEDS CLARIFICATION")
-   Fill Constitution Check section from constitution
-   Evaluate gates (ERROR if violations unjustified)
-   Phase 0: Generate research.md (resolve all NEEDS CLARIFICATION)
-   Phase 1: Generate data-model.md, contracts/, quickstart.md
-   Phase 1: Update agent context by running the agent script
-   Re-evaluate Constitution Check post-design

4. **Stop and report**: Command ends after Phase 2 planning. Report feature name, IMPL_PLAN path, and generated artifacts.

## Phases

### Phase 0: Outline & Research

#### MCP usage requirements (REQUIRED)

-   Before generating `research.md` or making key technology decisions, the planner SHOULD:

1. Use `sequential-thinking` to:

-   Break down each NEEDS CLARIFICATION into concrete research questions.
-   Prioritize by impact, risk, and dependency.

2. Use `context7` to:

-   Consult official or otherwise authoritative sources.
-   Capture URLs/versions/dates and key conclusions in `research.md`.

3. Use `serena` to:

-   Reconcile planned architecture with the current repository structure and conventions.

1. **Extract unknowns from Technical Context** above:

-   For each NEEDS CLARIFICATION → research task
-   For each dependency → best practices task
-   For each integration → patterns task

2. **Generate and dispatch research agents**:

```text
For each unknown in Technical Context:
  Task: "Research {unknown} for {feature context}"
For each technology choice:
  Task: "Find best practices for {tech} in {domain}"

```

3. **Consolidate findings** in `research.md` using format:

-   Decision: [what was chosen]
-   Rationale: [why chosen]
-   Alternatives considered: [what else evaluated]

**Output**: research.md with all NEEDS CLARIFICATION resolved

### Phase 1: Design & Contracts

**Prerequisites:** `research.md` complete

1. **Extract entities from feature spec** → `data-model.md`:

-   Entity name, fields, relationships
-   Validation rules from requirements
-   State transitions if applicable

2. **Generate API contracts** from functional requirements:

-   For each user action → endpoint
-   Use standard REST/GraphQL patterns
-   Output OpenAPI/GraphQL schema to `/contracts/`

3. **Agent context update**:

-   Run `.specify/scripts/bash/update-agent-context.sh codex`
-   These scripts detect which AI agent is in use
-   Update the appropriate agent-specific context file
-   Add only new technology from current plan
-   Preserve manual additions between markers

**Output**: data-model.md, /contracts/\*, quickstart.md, agent-specific file

## Key rules

-   Use absolute paths
-   ERROR on gate failures or unresolved clarifications

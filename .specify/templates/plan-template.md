# Implementation Plan: [FEATURE]

**Branch**: `[###-feature-name]` | **Date**: [DATE] | **Spec**: [link]
**Input**: Feature specification from `/specs/[###-feature-name]/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

[Extract from feature spec: primary requirement + technical approach from research]

## Technical Context

<!--
  ACTION REQUIRED: Replace the content in this section with the technical details
  for the project. The structure here is presented in advisory capacity to guide
  the iteration process.
-->

**Language/Version**: [e.g., Python 3.8+ (as per constitution)]
**Primary Dependencies**: [e.g., Celery, Redis, FastAPI]
**Storage**: [e.g., Redis, Shared Filesystem (`/share`)]
**Testing**: [e.g., pytest (as per constitution)]
**Target Platform**: [e.g., Docker on Linux server with NVIDIA GPUs (CUDA 11.x+)]
**Project Type**: [microservice-based]
**Performance Goals**: [domain-specific, e.g., 1000 req/s, 10k lines/sec, 60 fps or NEEDS CLARIFICATION]
**Constraints**: [domain-specific, e.g., <200ms p95, <100MB memory, offline-capable or NEEDS CLARIFICATION]
**Scale/Scope**: [domain-specific, e.g., 10k users, 1M LOC, 50 screens or NEEDS CLARIFICATION]

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [ ] **I. Service-First Architecture**: Is the feature encapsulated in a single-responsibility, independently deployable service?
- [ ] **II. Contract-Driven Communication**: Are all inter-service interactions defined by versioned, explicit contracts?
- [ ] **III. Strict Test-First Development**: Is Test-Driven Development being followed? Are integration and contract tests planned?
- [ ] **IV. Observability by Design**: Does the service have built-in structured logging, metrics, and tracing?
- [ ] **V. Stateless Work Units**: Is the worker service stateless, with state managed centrally?
- [ ] **VI. Systematic AI Model Management**: Is there a formal process for versioning and deploying the AI models used?
- [ ] **VII. Configuration as Code**: Are all configurations stored in version control, with secrets separated?

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)
<!--
  ACTION REQUIRED: The structure below is based on the project constitution.
  Expand it with real paths for this feature.
-->

```text
services/
├── api_gateway/      # API gateway service
├── workers/          # AI worker services (e.g., faster_whisper, paddleocr)
└── common/           # Shared components and utilities
tests/
├── unit/
├── integration/
└── e2e/
docs/
```

**Structure Decision**: [Document the selected structure and reference the real directories captured above]

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., Principle Name] | [Justification for deviation] | [Explanation of why the simpler, compliant alternative was not chosen] |

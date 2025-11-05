---
description: "Task list template for feature implementation"
---

# Tasks: [FEATURE NAME]

**Input**: Design documents from `/specs/[###-feature-name]/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: The examples below include test tasks. Tests are MANDATORY as per constitution (Principle III: Strict Test-First Development).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- Paths shown below assume the YiVideo microservice structure (`services/workers/[service_name]`, `services/api_gateway`, etc.). Adjust based on plan.md.

<!--
  ============================================================================
  IMPORTANT: The tasks below are SAMPLE TASKS for illustration purposes only.

  The /speckit.tasks command MUST replace these with actual tasks based on the design artifacts.

  DO NOT keep these sample tasks in the generated tasks.md file.
  ============================================================================
-->

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure for the new service/feature.

- [ ] T001 Create service directory structure in `services/workers/[service_name]` per plan.
- [ ] T002 Initialize dependencies (e.g., `requirements.txt`).
- [ ] T003 [P] Configure linting and formatting tools.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T004 Setup database schema/models if needed.
- [ ] T005 Setup service-to-service communication (e.g., Celery task registration).
- [ ] T006 **(Observability)** Configure structured logging infrastructure.
- [ ] T007 **(Observability)** Setup Prometheus metrics endpoint and basic service metrics.
- [ ] T008 **(Observability)** Integrate distributed tracing middleware/decorators.
- [ ] T009 **(AI Models)** Establish AI model storage, versioning, and loading strategy.
- [ ] T010 Configure environment variable handling for the service.

**Checkpoint**: Foundation ready - user story implementation can now begin.

---

## Phase 3: User Story 1 - [Title] (Priority: P1) 🎯 MVP

**Goal**: [Brief description of what this story delivers]
**Independent Test**: [How to verify this story works on its own]

### Tests for User Story 1 (Write these first!) ⚠️

- [ ] T011 [P] [US1] Contract test for endpoint/message in `tests/contract/test_[name].py`.
- [ ] T012 [P] [US1] Integration test for user journey in `tests/integration/test_[name].py`.
- [ ] T013 [P] [US1] Unit tests for business logic in `tests/unit/test_[name].py`.

### Implementation for User Story 1

- [ ] T014 [US1] **(Contracts)** Define/update API contracts in `services/common/contracts/` or OpenAPI spec.
- [ ] T015 [P] [US1] Implement data models/entities.
- [ ] T016 [US1] Implement core service logic (depends on T015).
- [ ] T017 [US1] Implement API endpoint / Celery task consumer.
- [ ] T018 [US1] Add specific structured logging for User Story 1 operations.
- [ ] T019 [US1] **(Observability)** Expose relevant Prometheus metrics for User Story 1 (e.g., processing time, success/error count).

**Checkpoint**: User Story 1 is fully functional, tested, and observable.

---

[Add more user story phases as needed]

---

## Phase N: Polish & Cross-Cutting Concerns

- [ ] TXXX [P] Documentation updates in `docs/`.
- [ ] TXXX Code cleanup and refactoring.
- [ ] TXXX Security hardening (review inputs, permissions).
- [ ] TXXX Run `quickstart.md` validation.

---
## Implementation Strategy

### MVP First (User Story 1 Only)
1. Complete Phase 1 & 2 (Setup & Foundational).
2. Complete all tasks in Phase 3 (User Story 1).
3. **STOP and VALIDATE**: Test User Story 1 independently.

### Incremental Delivery
1. Complete Setup + Foundational.
2. Add User Story 1 → Test → Deploy/Demo.
3. Add User Story 2 → Test → Deploy/Demo.

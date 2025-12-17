<!-- OPENSPEC:START -->
# OpenSpec Instructions

These instructions are for AI assistants working in this project.

Always open `@/openspec/AGENTS.md` when the request:
- Mentions planning or proposals (words like proposal, spec, change, plan)
- Introduces new capabilities, breaking changes, architecture shifts, or big performance/security work
- Sounds ambiguous and you need the authoritative spec before coding

Use `@/openspec/AGENTS.md` to learn:
- How to create and apply change proposals
- Spec format and conventions
- Project structure and guidelines

Keep this managed block so 'openspec update' can refresh the instructions.

<!-- OPENSPEC:END -->

# Repository Guidelines

## Output Language (Mandatory)

-   Always respond in Simplified Chinese for all explanatory text (plans, reasoning, step-by-step guidance, summaries, PR/commit descriptions).
-   Keep code, commands, config keys, file paths, and raw logs/stack traces in their original language (often English), but explain them in Simplified Chinese.
-   Do not switch to English unless the user explicitly requests English.

## MCP Tools Integration (Mandatory)

This project expects the assistant to proactively use MCP services to improve speed, correctness, and output quality. Use the tools below whenever they can reduce guessing, avoid rework, or strengthen evidence.

### Available MCP Services

-   `serena`: Repository-aware code intelligence (search, symbol lookup, dependency tracing, refactor assistance, change impact scanning).
-   `context7`: External documentation and API references (framework/library behavior, edge cases, version notes, best practices).
-   `sequential-thinking`: Structured multi-step reasoning for plans, tradeoffs, debugging strategies, and complex change execution.

### Tool-First Rules

-   Use `serena` before making claims about existing code behavior, file locations, module ownership, queue/task names, or configuration wiring.
-   Use `context7` before implementing or changing anything that depends on third-party libraries (e.g., FastAPI, Celery, Redis, MinIO SDKs, ffmpeg tooling, ML model toolkits) when details matter.
-   Use `sequential-thinking` when a request involves more than one component (gateway + workers + config + docs), any non-trivial migration, or any ambiguous requirement that needs clarification.

### When You Must Use MCP

-   Architecture or behavior changes: run `serena` to identify touchpoints and ensure consistency across gateway/workers/config/docs.
-   Bug diagnosis: use `sequential-thinking` to propose a hypothesis list and a narrowing plan; use `serena` to locate relevant code paths and logs; use `context7` for library-specific failure modes.
-   Security-sensitive work (callbacks, URL validation, auth, credentials handling): use `context7` to confirm secure defaults and recommended patterns; use `serena` to confirm existing safety checks are preserved.

### Evidence and Citations in Responses

-   When you used MCP, briefly state what you checked (e.g., “searched for task name usage across compose + Celery config”) and where it was found (file paths).
-   Do not fabricate file contents. If you cannot access something, say so and propose the next best verification step.

## Project Structure & Modules

-   `services/api_gateway/`: FastAPI entrypoint (`app/main.py`) plus task/callback/minio helpers.
-   `services/workers/`: Celery workers for media/AI tasks (ffmpeg, faster_whisper, paddleocr, audio_separator, pyannote_audio, indextts, gptsovits, inpainting, wservice); each has its own `Dockerfile`.
-   `services/common/`: Shared worker utilities and state helpers.
-   `config.yml` & `config/`: Runtime configuration; keep environment overrides in `.env` rather than editing defaults.
-   `docs/`: Product, API, and technical references; update relevant doc when behavior changes.
-   `tests/`: Placeholder for automated tests; add module-aligned tests here or alongside code when practical.
-   `videos/`, `share/`, `tmp/`, `locks/`: Local storage mounts used by compose services; avoid committing generated assets.

## Build, Test, and Development Commands

-   `docker-compose build`: Build all gateway + worker images from the root compose file.
-   `docker-compose up -d`: Launch the stack; maps gateway to host `8788`.
-   `docker-compose logs -f <service>`: Tail service logs (e.g., `api_gateway`, `ffmpeg_service`).
-   `docker-compose down`: Stop containers while preserving volumes.
-   `pip install -r requirements.txt`: Install shared Python deps for local tooling/scripts.
-   `pytest tests` or `pytest services/api_gateway/app`: Run automated tests; add `-m gpu` for GPU-tagged cases when applicable.

## Coding Style & Naming Conventions

-   Python formatted with Black (line length 100) and linted with Flake8; keep type hints and concise docstrings.
-   Naming: classes `PascalCase`, functions/variables `snake_case`, constants `UPPER_SNAKE_CASE`; modules and files stay lowercase with underscores.
-   Keep workflow/task names consistent with queue names in `docker-compose.yml` and Celery configs.
-   Prefer configuration over hard-coded paths; read settings from `config.yml` or environment variables.

## Testing Guidelines

-   Add unit/functional tests for new endpoints, Celery tasks, and media handlers; mock heavy model downloads where possible.
-   Name tests after behavior (`test_<module>_<behavior>`); include minimal fixtures in `tests/` or module-local `test_*.py`.
-   Before PRs: run `pytest ...` plus targeted manual smoke via `docker-compose up -d` and a sample request to `/v1/tasks/health` or `/v1/files/health`.

## Commit & Pull Request Guidelines

-   Use Conventional Commits: `<type>(<scope>): <subject>` (e.g., `feat(api): add single-task retry guard`).
-   PRs should include: purpose/impact summary, linked issue/task ID, test evidence (commands + results), and screenshots/log snippets for API changes when helpful.
-   Keep PRs scoped: one feature/fix per PR; avoid bundling formatting-only changes with logic changes.
-   Do not commit secrets or local data; rely on `.env` and compose environment variables (`MINIO_*`, `REDIS_*`, `HF_TOKEN`, etc.).

## Security & Configuration Tips

-   Validate external URLs before callbacks (see `app/callback_manager.py`); never disable URL safety checks.
-   GPUs and model caches mount via compose volumes—confirm access before enabling GPU queues.
-   Rotate credentials stored in environment variables and avoid persisting anything sensitive under version control or `share/`.

## Development Principles (Mandatory)

-   DRY (Don't Repeat Yourself): avoid duplicating business rules/logic/flows. The same “piece of knowledge” should have a single, clear, authoritative implementation location. Prefer reuse via abstraction (functions/classes/modules) over copy-paste.
-   SOLID: five object-oriented design principles to control responsibility and dependencies:
    -   S: Single Responsibility
    -   O: Open/Closed
    -   L: Liskov Substitution
    -   I: Interface Segregation
    -   D: Dependency Inversion
-   YAGNI (You Aren't Gonna Need It): do not implement “maybe useful later” features. Add functionality only when the current requirement clearly needs it; prefer minimal viable change to avoid feature creep.
-   KISS (Keep It Simple): prefer the simplest understandable design and implementation. Avoid extra abstractions, complex frameworks, or over-engineering unless there is a clear benefit (performance/security/maintainability/extensibility).

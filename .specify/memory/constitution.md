# YiVideo Constitution
<!--
- Version: 1.0.0 -> 1.1.0
- Modified Principles: None
- Populated Sections: Additional Constraints, Development Workflow
- Removed Sections: None
- Templates Requiring Updates:
  - ⚠ .specify/templates/plan-template.md
  - ⚠ .specify/templates/spec-template.md
  - ⚠ .specify/templates/tasks-template.md
- Follow-up TODOs: None
-->
## Core Principles

### I. Service-First Architecture
Every new feature must be encapsulated in a single-responsibility, independently deployable, self-contained service.

### II. Contract-Driven Communication
All inter-service interactions (both synchronous APIs and asynchronous messages) must be defined by versioned, explicit contracts (e.g., OpenAPI, Pydantic models).

### III. Strict Test-First Development
Test-Driven Development (TDD) is mandatory. Integration and contract testing are highly valued to ensure service reliability.

### IV. Observability by Design
All services must have built-in structured logging, Prometheus metrics, and distributed tracing capabilities to ensure system-wide transparency.

### V. Stateless Work Units
Worker services must be stateless. All state is managed by a central service like Redis or a database.

### VI. Systematic AI Model Management
A formal process for versioning, deploying, and documenting AI models and their resource requirements must be established.

### VII. Configuration as Code
All configurations must be stored in version-controlled files, with strict separation of sensitive information.

## Additional Constraints

### Security
- All sensitive configurations must use environment variables or encrypted storage.
- API interfaces must support JWT authentication and rate limiting.
- Containers must run with non-root users.

### Performance
- GPU locks must be used to avoid resource conflicts.
- Appropriate concurrency and batch sizes must be configured.
- Model caching and quantization should be enabled where applicable.

### Compatibility
- The system must support CUDA 11.x+.
- NVIDIA RTX series GPUs are the recommended hardware.
- The required Python version is 3.8+.

## Development Workflow

### Code Organization
- `services/`: Contains all microservice code, including the API gateway and AI workers.
- `tests/`: Contains all test code, structured according to the testing pyramid (unit, integration, E2E).
- `docs/`: Contains all project documentation.

### Testing Strategy
- **Testing Pyramid**: The project strictly follows the testing pyramid principle.
- **Unit Tests**: Must mock all external dependencies to test business logic in isolation.
- **Integration Tests**: Must use real infrastructure (like databases and message queues) to test service-internal interactions.
- **End-to-End Tests**: Must cover complete business flows to simulate real user scenarios.

### Local Development
- All services are managed via `docker-compose`. Developers should use the standard `build`, `up -d`, `logs`, `restart`, and `down` commands for local environment management.

## Governance

All pull requests and reviews must verify compliance with this constitution. Any complexity must be justified.

**Version**: 1.1.0 | **Ratified**: 2025-11-05 | **Last Amended**: 2025-11-05

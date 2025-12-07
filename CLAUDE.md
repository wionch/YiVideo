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

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**YiVideo** is an AI-powered video processing platform built on a dynamic workflow engine with microservices architecture. The core philosophy is "configuration over coding" - AI processing pipelines are dynamically constructed through workflow configuration files.

### Core Features

-   **Automatic Speech Recognition (ASR)**: High-precision speech-to-text powered by Faster-Whisper
-   **Speaker Diarization**: Multi-speaker identification and separation using Pyannote-audio
-   **Optical Character Recognition (OCR)**: Subtitle region detection and text recognition via PaddleOCR
-   **Audio Processing**: Voice/background separation and audio enhancement
-   **Subtitle Processing**: AI-driven subtitle generation, proofreading, optimization, and merging
-   **Text-to-Speech (TTS)**: Multi-engine high-quality voice synthesis
-   **Video Processing**: FFmpeg-based video editing and format conversion

## Project Structure

```
yivideo/
├── services/                    # Microservices directory
│   ├── api_gateway/             # API Gateway - unified entry point
│   ├── common/                  # Common modules (state management, utilities)
│   └── workers/                 # Celery Worker services
│       ├── faster_whisper_service/   # ASR speech recognition
│       ├── pyannote_audio_service/   # Speaker diarization
│       ├── paddleocr_service/        # OCR text recognition
│       ├── audio_separator_service/  # Audio separation
│       ├── ffmpeg_service/           # Video processing
│       ├── indextts_service/         # TTS voice synthesis
│       ├── gptsovits_service/        # GPT-SoVITS TTS
│       ├── inpainting_service/       # Video inpainting
│       └── wservice/                 # Generic workflow service
├── config/                      # Configuration files
├── config.yml                   # Main configuration file
├── docker-compose.yml           # Container orchestration
├── docs/                        # Project documentation
├── openspec/                    # OpenSpec specifications
├── tests/                       # Test directory
├── share/                       # Inter-service shared storage
└── scripts/                     # Utility scripts
```

## Tech Stack

### Backend Framework & Services

-   **Python 3.8+**: Primary programming language
-   **FastAPI**: HTTP service framework for API Gateway
-   **Celery 5.x**: Distributed task queue and workflow engine
-   **Redis**: Multi-purpose data store (DB0: Broker, DB1: Backend, DB2: Locks, DB3: State)

### AI/ML Models & Libraries

-   **Faster-Whisper**: GPU-accelerated speech recognition
-   **Pyannote-audio**: Speaker diarization and voice-print recognition
-   **PaddleOCR**: Chinese-English OCR recognition
-   **Audio-Separator**: Audio source separation
-   **IndexTTS / GPT-SoVITS**: TTS engines

### Infrastructure

-   **Docker & Docker Compose**: Containerized deployment
-   **FFmpeg**: Audio/video processing
-   **MinIO**: Object storage service
-   **CUDA 11.x+**: GPU acceleration support

## Development Commands

```
# Container management
docker-compose up -d              # Start all services
docker-compose ps                 # Check service status
docker-compose logs -f <service>  # View logs

# Testing
pytest tests/unit/                # Unit tests
pytest tests/integration/         # Integration tests
pytest -m gpu                     # GPU tests
```

## Global Architectural Constraints

**CRITICAL**: You must strictly adhere to these principles for all code generation, refactoring, and design tasks.

### 1. KISS (Keep It Simple, Stupid)

-   **Rule**: Prioritize the simplest implementation path. Avoid over-engineering.
-   **Trigger**: If the code requires complex comments to explain or uses design patterns (like Strategy/Factory) for simple logic.
-   **Directive**: "If a simple `if/else` works, do not use a complex pattern." Keep the cognitive load low.

### 2. DRY (Don't Repeat Yourself)

-   **Rule**: Every piece of logic must have a single, unambiguous representation.
-   **Trigger**: Repeated logic blocks, copy-pasted code, or duplicate magic values.
-   **Directive**: Extract repeated logic into utility functions or constants. _Note: Avoid premature abstraction that hurts readability._

### 3. YAGNI (You Ain't Gonna Need It)

-   **Rule**: Implement ONLY what is explicitly requested in the current Spec/Task.
-   **Trigger**: Adding "hooks" for future features, unused configuration options, or extra interface methods.
-   **Directive**: "Write only the code needed to pass the current tests." Do not speculate on future requirements.

### 4. SOLID (Object-Oriented Design)

-   **SRP**: Single Responsibility Principle (One reason to change).
-   **OCP**: Open/Closed Principle (Extend without modifying).
-   **LSP**: Liskov Substitution Principle (Subtypes must be substitutable).
-   **ISP**: Interface Segregation Principle (No forced dependencies on unused methods).
-   **DIP**: Dependency Inversion Principle (Depend on abstractions).

### Violation Check (Self-Correction)

Before outputting any code, perform this internal check:

1. Is this the simplest way? (KISS)
2. Did I add unused features? (YAGNI)
3. Is logic duplicated? (DRY)
4. Does it violate SOLID?

**Fix any violations immediately before responding.**

## Code Style Guidelines

-   **Formatting**: Black (line-length=100), Flake8
-   **Naming**: Classes `PascalCase`, Functions `snake_case`, Constants `UPPER_SNAKE_CASE`
-   **Documentation**: Google-style docstrings, Python 3.8+ type annotations
-   **Comment Language**: Maintain consistency with existing codebase

## Architecture Patterns

-   **API Gateway Pattern**: Unified entry point for request routing and workflow orchestration
-   **Worker Pattern**: Each AI capability isolated as independent Celery Worker
-   **Shared Storage**: `/share` directory for inter-service file exchange
-   **State Management**: Centralized StateManager

## Git Workflow

Use Conventional Commits: `<type>(<scope>): <subject>`

**Types**: `feat` | `fix` | `refactor` | `docs` | `test` | `chore` | `perf`

**Important**: Do not automatically execute git commit/push operations without explicit user request.

## Assistant Behavior Guidelines

### Response Language Requirements

**CRITICAL**: All responses to user interactions MUST be in Chinese (Simplified Chinese), regardless of the language used in this documentation or the codebase.

-   **Internal Processing**: You may reason and process information in English for optimal performance
-   **Output Format**: Always present the final response to the user in Chinese
-   **Code Comments**: Use Chinese (Simplified) for all code comments, docstrings, and inline documentation to maintain consistency with the project's localization standards
-   **Exception**: Only respond in English if the user explicitly requests English responses

### MCP Services Integration

1. **Always Default to MCP Services**: When faced with complex reasoning, context-heavy tasks, or ambiguous requirements, your first action should be to engage the relevant MCP services.

2. **Service Selection**:

    - Use **serena** for general context management and conversation continuity
    - Use **context7** for deep context processing and analysis
    - Use **sequentialthinking** for structured problem-solving and step-by-step reasoning

3. **Transparent Usage**: When using MCP services, briefly indicate in your response which services were engaged and how they informed your approach.

4. **Fallback Protocol**: If MCP services are unavailable for technical reasons, explicitly state this limitation and proceed with native reasoning while noting the reduced capability.

**CRITICAL REMINDER**: These MCP services are core project infrastructure. Not using them when appropriate violates project conventions and reduces effectiveness.

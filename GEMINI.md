# Gemini Development Guidelines for YiVideo

## Project Overview

**YiVideo** is a one-stop, modular AI video processing and localization platform. Its primary goal is to automate the process of translating video content into multiple languages, including subtitle extraction, translation, and dubbing, to help content creators reach a global audience.

The system is designed as a **dynamic, configurable AI video processing workflow engine**. Instead of hardcoded pipelines, it uses a "configuration over coding" philosophy. Users can define and execute complex processing chains by submitting a `workflow_config` to the main API, allowing for flexible and extensible combination of various AI capabilities.

### Core Technologies & Architecture

*   **Architecture**: Microservices architecture orchestrated with `docker-compose`.
*   **Backend**: Python, FastAPI for the API Gateway.
*   **Task Queuing**: Celery with a Redis broker for asynchronous task management between services.
*   **State Management**: A central Redis store is used to track the state and progress of each workflow.
*   **AI Services**: The project is composed of several independent AI worker services, each running in its own Docker container:
    *   `api_gateway`: The "brain" of the system. It receives user requests, interprets the `workflow_config`, and dynamically constructs and dispatches the Celery task chain.
    *   `ffmpeg_service`: Handles fundamental video operations like decoding and frame extraction.
    *   `paddleocr_service`: Performs Optical Character Recognition (OCR) to extract hardcoded subtitles from video frames.
    *   `faster_whisper_service`: Provides Automatic Speech Recognition (ASR) to transcribe audio into subtitles.
    *   `pyannote_audio_service`: Performs speaker diarization to identify who is speaking and when.
    *   `llm_service`: Interacts with Large Language Models (e.g., Gemini, DeepSeek) for translation and subtitle refinement.
    *   `inpainting_service`: (Future) Removes original hardcoded subtitles from the video.
    *   `indextts_service` / `gptsovits_service`: (Future) Text-to-Speech (TTS) engines for generating dubbed audio.
*   **Data Sharing**: Services share files (videos, frames, subtitles) via shared Docker volumes mounted to a common path (e.g., `/share`).

## Building and Running

The entire environment is managed by Docker. An NVIDIA GPU is required for the AI-powered worker services.

### Prerequisites

*   Docker
*   Docker Compose
*   NVIDIA Container Toolkit (for GPU support)

### Running the System

To build and run all services in detached mode, use the following command from the project root directory:

```bash
docker-compose up -d --build
```

This command will:
1.  Build the Docker images for all services defined in `docker-compose.yml`.
2.  Start the containers in the background.
3.  Mount the necessary local directories (`./services`, `./videos`, `./share`, etc.) as volumes into the containers.

To stop the services:

```bash
docker-compose down
```

## Development Conventions

### Workflow Execution

1.  A user sends a `POST` request to the `api_gateway` at `/v1/workflows`.
2.  The request body contains the `video_path` and a `workflow_config` JSON object that defines the sequence of operations.
3.  The `api_gateway` creates a unique `workflow_id`, sets up a shared directory under `/share/workflows/<workflow_id>`, and initializes the workflow's state in Redis.
4.  The `workflow_factory` module within the gateway parses the `workflow_config` and constructs a Celery `chain` of tasks.
5.  The task chain is executed asynchronously. Each task takes a `WorkflowContext` object as input, performs its function (e.g., runs OCR), updates the state in Redis, and passes the updated context to the next task in the chain.
6.  The status of the workflow can be monitored by querying `GET /v1/workflows/status/<workflow_id>`.

### Adding a New AI Service

1.  Create a new directory for your service under `services/workers/`.
2.  Add a `Dockerfile` that inherits from the base image and installs any specific dependencies.
3.  Implement the core logic as a Celery task, ensuring it follows the `standard_task_interface(self: Task, context: dict) -> dict` signature.
4.  Add the new service definition to the root `docker-compose.yml` file, ensuring volumes and environment variables are correctly configured.
5.  Update the `workflow_factory` in the `api_gateway` to recognize the new capability and add it to task chains when requested in a `workflow_config`.

### Code Style

The project uses Python. While no specific linter is enforced in the provided files, it is recommended to use standard tools like `black` for formatting and `ruff` or `flake8` for linting to maintain code consistency.

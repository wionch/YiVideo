# Implementation Plan: Refactor ffmpeg_worker to ffmpeg_service

## Stage 1: Modify file contents
**Goal**: Update all occurrences of `ffmpeg_worker` to `ffmpeg_service` within the project files.
**Deliverable Files**:
- `D:/WSL2/docker/YiVideo/docker-compose.yml`
- `D:/WSL2/docker/YiVideo/services/workers/ffmpeg_worker/Dockerfile`
- `D:/WSL2/docker/YiVideo/services/workers/ffmpeg_worker/app/celery_app.py`
- `D:/WSL2/docker/YiVideo/services/workers/ffmpeg_worker/test_decoder_core.py`
**Justification**: This stage prepares the codebase for the directory rename. Modifying files first ensures that we are working with valid paths. This corresponds to the user's request to perform the renaming.
**Success Criteria**: A `git diff` will show that all instances of `ffmpeg_worker` in the specified files have been replaced with `ffmpeg_service`.
**Status**: Complete

## Stage 2: Rename directory
**Goal**: Rename the `ffmpeg_worker` directory to `ffmpeg_service`.
**Deliverable Files**: N/A (Directory rename)
**Justification**: This completes the renaming process by updating the file system structure. This corresponds to the user's request to perform the renaming.
**Success Criteria**: The directory `D:/WSL2/docker/YiVideo/services/workers/ffmpeg_worker` will no longer exist, and `D:/WSL2/docker/YiVideo/services/workers/ffmpeg_service` will exist.
**Status**: Complete

## Stage 3: Final Verification
**Goal**: Verify that the refactoring is complete by searching for any remaining occurrences of the old name.
**Deliverable Files**: N/A
**Justification**: This step ensures that no occurrences of the old name have been missed, ensuring the refactoring is complete and correct.
**Success Criteria**: Searching for `ffmpeg_worker` in the project should yield no results.
**Status**: Complete

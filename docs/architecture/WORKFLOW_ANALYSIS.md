# YiVideo 服务组件与工作流分析报告

本报告旨在详细阐述 `services/workers` 目录下各个微服务组件的功能，并基于代码审查，分析系统当前的工作流架构、能力和局限性。

## 1. 核心组件功能概述

系统采用微服务架构，每个 `worker` 服务都是一个独立的、可执行特定原子任务的“积木块”。

*   **`ffmpeg_service` (音视频基础工具)**
    *   **功能**: 提供所有基础的音视频处理能力，是整个系统的基石。负责执行如**提取音频**、**抽取视频帧**、**裁剪图片**、**分割音频片段**及最终的**音视频合成**等原子操作。
    *   **技术**: 封装了强大的 `FFmpeg` 命令行工具。

*   **`audio_separator_service` (音频分离服务)**
    *   **功能**: 将混合音轨分离成独立的**人声**和**背景声**。这是实现保留原背景音乐、替换配音的关键步骤。
    *   **技术**: 基于 `audio-separator` 库，支持 `Demucs`, `MDX-Net` 等多种音源分离模型。

*   **`faster_whisper_service` (语音识别服务 - ASR)**
    *   **功能**: 负责进行**语音转录 (ASR)**，将音频文件（通常是分离出的人声）转换成带精确时间戳的文本字幕。
    *   **技术**: 基于 `Faster-Whisper`，一个性能优化的 Whisper 模型实现。

*   **`pyannote_audio_service` (说话人识别服务)**
    *   **功能**: 识别一段音频中的**不同说话人**，并将语音片段归属到具体的说话人，用于生成区分角色的对话字幕。
    *   **技术**: 基于 `pyannote.audio` 库。

*   **`paddleocr_service` (硬字幕识别服务)**
    *   **功能**: 从视频画面中**检测和识别内嵌的硬字幕**。它负责定位字幕区域，并通过 OCR 提取文字内容和时间信息。
    *   **技术**: 基于 `PaddleOCR` 工具库。

*   **`inpainting_service` (视频修复服务)**
    *   **功能**: 对视频帧进行**图像修复 (Inpainting)**，核心应用是**去除原始的硬字幕**，生成干净的视频背景。
    *   **技术**: 基于计算机视觉中的 Inpainting 算法。

*   **`indextts_service` / `gptsovits_service` (语音合成/配音服务)**
    *   **功能**: 负责**文本转语音 (TTS)**，根据提供的文本和参考音频（用于克隆音色），生成新的语音，用于视频的**自动配音**。
    *   **技术**: 分别基于 `IndexTTS2` 和 `GPT-SoVITS` 等先进的语音克隆模型。

## 2. 工作流架构分析

根据对 `services/api_gateway/app/workflow_factory.py` 的代码审查，系统的核心工作流机制是**动态的、线性的任务链**。

*   **线性执行**: 系统通过 Celery 的 `chain` 功能，将 `workflow_chain` 列表中定义的任务**按顺序串联**起来。前一个任务的输出会自动成为后一个任务的输入。
*   **不支持并行分支**: 当前架构**不支持**通过单次API调用来执行包含并行分支再合并的复杂工作流（如 Celery 的 `group` 或 `chord`）。
*   **结论**: 系统提供了一系列强大的**原子服务**，但复杂的、多分支的端到端流程（如硬字幕翻译配音）需要通过**多次API调用**进行**外部手动编排**。

## 3. 预定义工作流分析

`config/examples/workflow_examples.yml` 文件中定义的示例工作流，如 `basic_subtitle_workflow` 和 `full_subtitle_workflow`，均**围绕一个核心场景**：**从视频的原始音轨生成字幕（ASR流程）**。

这些预定义流程验证了系统处理音频、进行语音识别和说话人识别的能力，但**并未包含**处理视频硬字幕、翻译及重新配音的端到端实现。

## 4. 硬字幕翻译配音流程（手动编排方案）

要实现完整的硬字幕翻译配音，需要一个外部客户端（或编排器）按以下步骤，通过多次调用 API 来手动驱动整个流程：

1.  **步骤一：提取硬字幕文本**
    *   **API 调用**: 提交一个包含硬字幕识别任务链的工作流。
    *   **`workflow_chain`**: `["ffmpeg.extract_keyframes", "paddleocr.detect_subtitle_area", "ffmpeg.crop_subtitle_images", "paddleocr.create_stitched_images", "paddleocr.perform_ocr", "paddleocr.postprocess_and_finalize"]`
    *   **产出**: 包含时间码和文本的原始硬字幕文件 (`.srt` 或 `.json`)。

2.  **步骤二：分离原始音源**
    *   **API 调用**: 提交一个音源分离的工作流。
    *   **`workflow_chain`**: `["ffmpeg.extract_audio", "audio_separator.separate_vocals"]`
    *   **产出**: ① 分离后的人声音频（用于音色克隆）；② 分离后的背景声音频。

3.  **步骤三：视频去字幕**
    *   **API 调用**: 提交一个视频修复的工作流。
    *   **`workflow_chain`**: `["inpainting_service.remove_hard_subs"]` (注：任务名需根据实际定义)
    *   **输入**: 原始视频路径和步骤一中检测到的字幕区域坐标。
    *   **产出**: 去除了硬字幕的干净视频文件。

4.  **步骤四：客户端处理与生成新配音**
    *   **客户端逻辑**: 对步骤一产出的字幕文本进行**翻译**。
    *   **API 调用**: 提交一个语音合成任务。
    *   **`workflow_chain`**: `["indextts.generate_speech"]`
    *   **输入**: 翻译后的文本和步骤二产出的人声音频（作为音色参考）。
    *   **产出**: 新的目标语言配音文件。

5.  **步骤五：最终合成**
    *   **API 调用**: 提交一个最终合成的工作流。
    *   **`workflow_chain`**: `["ffmpeg.combine_video_audio"]` (注：任务名需根据实际定义)
    *   **输入**: ① 步骤三产出的去字幕视频；② 步骤四产出的新配音；③ 步骤二产出的背景声。
    *   **产出**: 最终完成翻译和配音的视频文件。

## 5. 综合工作流程图（手动编排视角）

```mermaid
graph TD
    subgraph "外部客户端/编排器"
        direction TB
        
        subgraph "第1次 API 调用: 获取硬字幕"
            A[输入视频] --> WF1_Chain("ffmpeg.extract_keyframes\n...\npaddleocr.postprocess_and_finalize");
            WF1_Chain --> R1[硬字幕文本 & 字幕区域];
        end

        subgraph "第2次 API 调用: 分离音源"
            A --> WF2_Chain("ffmpeg.extract_audio\n...\naudio_separator.separate_vocals");
            WF2_Chain --> R2_Vocal[人声音频 (参考)];
            WF2_Chain --> R2_BG[背景声音频];
        end

        subgraph "第3次 API 调用: 视频去字幕"
            A & R1 --> WF3_Chain("inpainting_service.remove_hard_subs");
            WF3_Chain --> R3[去字幕视频];
        end

        subgraph "第4次 API 调用: 生成新配音"
            R1 -- 客户端翻译 --> T[翻译后文本];
            T & R2_Vocal --> WF4_Chain("indextts.generate_speech");
            WF4_Chain --> R4[新配音];
        end

        subgraph "第5次 API 调用: 最终合成"
            R3 & R4 & R2_BG --> WF5_Chain("ffmpeg.combine_video_audio");
            WF5_Chain --> Z[最终输出视频];
        end
    end

    style A fill:#f9f,stroke:#333,stroke-width:2px
    style Z fill:#9f9,stroke:#333,stroke-width:2px
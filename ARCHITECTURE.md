# AI Harness Architecture

## Overview

The AI Harness is an autonomous software-engineering agent designed to resolve issues in code repositories. It uses text-only language models to understand issues, analyze repositories, apply fixes, and verify them through test suites.

## System Components

The system is composed of several key modules:

1.  **Entry Point (`backend/app/run_harness.py`)**:
    *   Provides the Command Line Interface (CLI) for the harness.
    *   Parses input arguments (Task, Repository, Constraints).
    *   Initializes the orchestrator loop and outputs the final result (console or JSON).

2.  **Orchestrator (`backend/app/orchestrator.py`)**:
    *   The core brain of the harness.
    *   Maintains the `AgentState` including the conversation history, token budget, and iteration limits.
    *   Implements the REPL (Read-Eval-Print-Loop) interaction with the Language Model (LLM).
    *   Features intelligent context trimming (`_trim_messages`) to prevent token exhaustion over long tasks.
    *   Executes a verification step (via tests) after the LLM claims completion, and feeds failures back into the loop.

3.  **LLM Provider (`backend/app/llm_provider.py`)**:
    *   An abstract interface (`LLMProvider`) to standardise interactions with different AI models.
    *   `GroqProvider` implements this interface, communicating with the Groq API (or any OpenAI-compatible endpoint).
    *   Reads the `AI_API_KEY` standard credential at runtime.
    *   Handles tool-call serialization and deserialization.

4.  **Tools Toolkit (`backend/app/tools.py`)**:
    *   Exposes a restricted set of capabilities to the LLM:
        *   `list_files`: Scans a directory structure to discover the codebase.
        *   `read_file`: Reads specific files for analysis.
        *   `write_file`: Overwrites file content completely (prioritized for robust, conflict-free fixes).
        *   `apply_patch`: Applies unified diffs (used selectively).
        *   `run_tests`: Automatically detects (`pytest` or `unittest`) and executes the test suite, heavily truncating output to prevent context overflow.

## Workflow Execution

1.  **Initialization**: The LLM is initialized with a robust System Prompt outlining the steps (Read -> Edit -> Run Tests).
2.  **Analysis Phase**: The agent uses `list_files` and `read_file` to understand the codebase and the issue.
3.  **Coding Phase**: The agent uses `write_file` to implement fixes.
4.  **Verification Phase**: `run_tests` is executed. If tests pass, the harness reports `VERIFIED`. If tests fail, the output is fed back to the agent for another iteration, up to a maximum limit.

## Model Configuration

*   **Constraint**: Text-only models.
*   **Modality**: Code analysis and modification.
*   **Configuration**: Defaults to `openai/gpt-oss-120b` (or similar high-capability models). The `AI_API_KEY` is securely injected via the environment at runtime, conforming to Hackathon evaluation standards. No credentials are stored in code.

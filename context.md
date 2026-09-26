# AI Harness - Project Context & Model Handoff

## 1. Project Overview
**AI_Harness** is an autonomous AI coding agent system designed to understand codebases, plan solutions, apply unified diff patches, execute test suites in a controlled environment, and automatically fix failures through an iterative feedback loop.

## 2. Architecture & Design Principles
- **Separation of Concerns**:
  - `types.py`: Strictly data models and type definitions. No business logic, file I/O, or tool execution.
  - `tools.py`: Strictly the execution toolbox. No LLM prompts, orchestration, or agent state decisions.
  - `context_manager.py`: (Pending) Manages context window, file selection, prompt assembly, and token pruning.
  - `llm_provider.py`: (Pending) Interfaces with LLMs (e.g. OpenAI, Anthropic, Gemini).
  - `verifier.py`: (Pending) Analyzes test outputs, validates fixes, checks diffs.
  - `orchestrator.py`: (Pending) State machine driving the agent loop (`ANALYZING` -> `PLANNING` -> `CODING` -> `VERIFYING` -> `FIXING` -> `COMPLETED`/`FAILED`).
  - `run_harness.py` / `main.py`: CLI and API entry points (FastAPI backend).

- **Execution Flow**:
  ```text
  Task
   ↓
  Orchestrator
   ↓
  Context Manager & LLM Provider
   ↓
  Tool Request
   ↓
  tools.py (reads repo, applies unified diff, runs pytest)
   ↓
  Verifier (evaluates test outcome)
   ↓
  Orchestrator (repeats or completes)
  ```

## 3. Current Implementation Status

### Completed Modules
1. **`backend/app/types.py`**:
   - `Status` enum (`ANALYZING`, `PLANNING`, `CODING`, `VERIFYING`, `FIXING`, `COMPLETED`, `FAILED`).
   - `AgentState`: Core state tracking task, status, file list, context files, plan, unified diff patch, test output, error log, iteration count, and budget checks.
   - `ToolCall` and `ToolResult`: Standardized tool interaction models.
   - `Message`, `LLMResponse`, `HarnessConfig`: Communication and runtime config definitions.

2. **`backend/app/tools.py`**:
   - `list_files(repo_path)`: Scans repository recursively; filters `.git`, `node_modules`, `__pycache__`, `.venv`, etc.; returns sorted relative POSIX paths.
   - `search_code(repo_path, query)`: Case-sensitive substring search; skips binary and un-decodable files; returns `file_path`, `line_number`, and matching line content.
   - `read_file(repo_path, file_path)`: Reads text file contents; strictly blocks path traversal (`../../`); raises `FileNotFoundError`, `IsADirectoryError`, or `ValueError` for binaries.
   - `apply_patch(repo_path, patch)`: Validates unified diff headers; blocks path traversal in patch headers; strips markdown fences; atomically applies patch via `git apply --whitespace=nowarn` (`-p1` with `-p0` fallback).
   - `run_tests(repo_path, test_command=None, timeout=60)`: Executes pytest (or custom command) with repo working directory; captures `stdout`, `stderr`, and `exit_code`; never raises exception on test failure; enforces timeout.
   - `git_diff(repo_path)`: Read-only diff retrieval against `HEAD` (or plain `git diff`); returns `""` if clean or not a git repo.
   - `AVAILABLE_TOOLS`: Registry mapping tool names to functions.

### Pending / Next Components to Build
- `backend/app/context_manager.py`: Relevant file selection, prompt construction, and context budget management.
- `backend/app/llm_provider.py`: Standardized LLM client integration (tool calling, streaming, token tracking).
- `backend/app/verifier.py`: Verification logic parsing test outputs, exit codes, and diff quality.
- `backend/app/orchestrator.py`: Lifecycle coordinator executing the loop until success or budget exhaustion.
- `backend/app/main.py`: FastAPI server for frontend interaction.
- `backend/app/run_harness.py`: CLI harness runner.
- `frontend/`: Interactive UI (HTML/CSS/JS) to monitor agent actions and diffs.

## 4. Key Rules & Constraints for Future Models
- **Standard Library Priority**: Keep dependencies minimal; use standard library where possible.
- **Strict Architecture Boundaries**: Do not put LLM or agent orchestration logic in `tools.py` or `types.py`.
- **Patch Format**: Always use unified diff (`diff -u` / `git diff`).
- **File Safety**: Never allow path traversal outside the target repository.
- **Test Execution**: Always return test results as structured objects, never unhandled exceptions.

"""Application entry module for the AI Coding Agent Harness.

This module provides a unified top-level entry point that delegates to
`run_harness.py` for CLI execution, or exposes a direct programmatic invocation
interface without duplicating orchestration, argument parsing, or tool logic.
"""

from __future__ import annotations

import sys
from typing import Sequence

try:
    from .orchestrator import run_harness_loop
    from .run_harness import main as run_harness_main
    from .types import AgentState
except ImportError:
    try:
        from backend.app.orchestrator import run_harness_loop
        from backend.app.run_harness import main as run_harness_main
        from backend.app.types import AgentState
    except ImportError:
        from orchestrator import run_harness_loop  # type: ignore[no-redef]
        from run_harness import main as run_harness_main  # type: ignore[no-redef]
        from types import AgentState  # type: ignore[no-redef]


def run(task: str, repo_path: str, max_iterations: int = 5) -> AgentState:
    """Programmatic entry point to run the harness on a task and target repository.

    Delegates directly to orchestrator.run_harness_loop without duplicating logic.

    Args:
        task: The task description or issue prompt.
        repo_path: Path to the target repository.
        max_iterations: Maximum allowed feedback/fixing iterations.

    Returns:
        AgentState instance containing final execution details and status.
    """
    return run_harness_loop(task=task, repo_path=repo_path, max_iterations=max_iterations)


def main(args: Sequence[str] | None = None) -> None:
    """CLI application entry point.

    Delegates to run_harness.main() to preserve argument parsing,
    output formatting, and exit code handling without code duplication.

    Args:
        args: Optional list of CLI arguments (defaults to sys.argv[1:]).
    """
    if args is not None:
        sys.argv = [sys.argv[0]] + list(args)
    run_harness_main()


if __name__ == "__main__":
    main()

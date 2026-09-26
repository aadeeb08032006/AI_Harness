"""Verification module for the AI Coding Agent Harness.

This module determines whether code changes in a target repository successfully
pass verification by executing repository tests via tools.run_tests and analyzing
the outcome.

This module does NOT generate patches, make LLM calls, explore repositories,
or perform retry loops. It strictly evaluates verification status and returns
structured results for orchestrator consumption.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    from . import tools
    from .types import AgentState, Status
except ImportError:
    try:
        from backend.app import tools
        from backend.app.types import AgentState, Status
    except ImportError:
        import tools  # type: ignore[no-redef]
        from types import AgentState, Status  # type: ignore[no-redef]


@dataclass
class VerificationResult:
    """Structured outcome of a verification run.

    Attributes:
        verified: True if all tests passed and verification succeeded.
        success: Boolean flag equivalent to verified for interface compatibility.
        exit_code: Process exit code returned by the test runner (0 indicates success).
        output: Combined standard output and error captured from test execution.
        stdout: Raw standard output captured during test execution.
        stderr: Raw standard error captured during test execution.
        error: Detailed error or failure explanation, or None on success.
        execution_error: True if the test runner itself failed to run (e.g. runner missing,
                         syntax error in test setup, timeout, invalid repo directory).
    """

    verified: bool
    success: bool
    exit_code: int
    output: str
    stdout: str = ""
    stderr: str = ""
    error: str | None = None
    execution_error: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert the verification result into a plain dictionary."""
        return {
            "verified": self.verified,
            "success": self.success,
            "exit_code": self.exit_code,
            "output": self.output,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "error": self.error,
            "execution_error": self.execution_error,
        }

    def __getitem__(self, key: str) -> Any:
        """Allow dictionary-style access for orchestrator compatibility."""
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        """Safe dictionary-style getter."""
        return getattr(self, key, default)

    def __bool__(self) -> bool:
        """Truthiness evaluates directly to verified status."""
        return self.verified


def _is_execution_error(exit_code: int, stderr: str, output: str) -> bool:
    """Determine if a non-zero exit code represents a runner/environment execution error.

    Distinguishes operational failures (runner missing, command timeout, invalid directory)
    from normal test assertion failures.
    """
    if exit_code in (124, 127):
        return True

    # Pytest exit codes: 2 (interrupted), 3 (internal error), 4 (usage error), 5 (no tests collected)
    if exit_code in (2, 3, 4, 5):
        return True

    combined = f"{stderr}\n{output}".lower()
    indicators = (
        "no module named pytest",
        "repository directory not found",
        "test runner executable not found",
        "test execution timed out",
        "unexpected error during test execution",
        "command not found",
        "usage: pytest",
        "no tests were found",
        "no tests collected",
    )
    return any(indicator in combined for indicator in indicators)


def verify(
    repo_path: str,
    test_command: str | list[str] | None = None,
    timeout: int = 60,
) -> VerificationResult:
    """Verify repository test suite status using tools.run_tests.

    Args:
        repo_path: Path to the target repository directory.
        test_command: Optional custom test command string or list of arguments.
                      Defaults to pytest.
        timeout: Maximum execution time in seconds (default 60).

    Returns:
        VerificationResult with structured verification outcome and test details.
    """
    raw = tools.run_tests(str(repo_path), test_command=test_command, timeout=timeout)

    success: bool = bool(raw.get("success", False))
    exit_code: int = int(raw.get("exit_code", 1))
    stdout: str = str(raw.get("stdout", ""))
    stderr: str = str(raw.get("stderr", ""))
    output: str = str(raw.get("output", ""))

    if success and exit_code == 0:
        return VerificationResult(
            verified=True,
            success=True,
            exit_code=exit_code,
            output=output,
            stdout=stdout,
            stderr=stderr,
            error=None,
            execution_error=False,
        )

    # If verification did not pass, classify the failure
    exec_err = _is_execution_error(exit_code, stderr, output)
    if exec_err:
        err_msg = (
            stderr.strip()
            or output.strip()
            or f"Test execution error (exit code {exit_code})."
        )
        return VerificationResult(
            verified=False,
            success=False,
            exit_code=exit_code,
            output=output,
            stdout=stdout,
            stderr=stderr,
            error=err_msg,
            execution_error=True,
        )

    err_msg = (
        output.strip()
        or stderr.strip()
        or f"Tests failed with exit code {exit_code}."
    )
    return VerificationResult(
        verified=False,
        success=False,
        exit_code=exit_code,
        output=output,
        stdout=stdout,
        stderr=stderr,
        error=err_msg,
        execution_error=False,
    )


def verify_state(
    state: AgentState,
    test_command: str | list[str] | None = None,
    timeout: int = 60,
) -> VerificationResult:
    """Verify an AgentState instance and synchronize its status and test fields.

    Convenience helper for orchestrator integration.

    Args:
        state: The active AgentState being verified.
        test_command: Optional custom test command string or list.
        timeout: Maximum execution time in seconds.

    Returns:
        VerificationResult instance.
    """
    state.status = Status.VERIFYING
    result = verify(state.repo_path, test_command=test_command, timeout=timeout)
    state.test_output = result.output
    state.tests_passed = result.verified

    if not result.verified and result.error:
        state.add_error(result.error)

    return result

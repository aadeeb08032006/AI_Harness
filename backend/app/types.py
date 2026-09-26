"""Data models and type definitions for the AI Coding Agent Harness.

This module defines the foundational data models, statuses, and lightweight
structures for the agent harness. No business logic, LLM calls, file I/O, or
tool execution resides here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class Status(str, Enum):
    """Execution status for the coding agent lifecycle."""

    ANALYZING = "ANALYZING"
    PLANNING = "PLANNING"
    CODING = "CODING"
    VERIFYING = "VERIFYING"
    FIXING = "FIXING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class AgentState:
    """Core state object tracking an agent's lifecycle across a task execution.

    Attributes:
        task: The task description or issue prompt.
        repo_path: Path to the target repository.
        status: Current Status enum value.
        files: All files seen in repo.
        relevant_files: Files selected as context.
        plan: Agent's generated plan.
        patch: Current/last applied unified diff.
        test_output: Raw or parsed test execution output.
        errors: List of error messages encountered.
        iteration: Current iteration count.
        max_iterations: Maximum allowed iterations.
        result: Final execution result payload.
    """

    task: str
    repo_path: str
    status: Status = Status.ANALYZING
    files: list[str] = field(default_factory=list)  # all files seen in repo
    relevant_files: list[str] = field(default_factory=list)  # files selected as context
    plan: str | None = None
    patch: str | None = None  # current/last applied diff
    test_output: str | None = None
    errors: list[str] = field(default_factory=list)
    iteration: int = 0
    max_iterations: int = 10
    result: dict[str, Any] | None = None
    file_contents: dict[str, str] = field(default_factory=dict)
    messages: list[dict[str, Any]] = field(default_factory=list)

    def budget_exhausted(self) -> bool:
        """Check if iteration count has reached or exceeded max iterations."""
        return self.iteration >= self.max_iterations

    def to_dict(self) -> dict[str, Any]:
        """Convert state to a serializable dictionary."""
        data = asdict(self)
        data["status"] = self.status.value
        return data


def budget_exhausted(state: AgentState) -> bool:
    """Helper function to check if state iteration budget is exhausted.

    Args:
        state: AgentState instance to check.

    Returns:
        True if state.iteration >= state.max_iterations, False otherwise.
    """
    return state.budget_exhausted()


# Supporting lightweight data models for harness communication


@dataclass
class ToolCall:
    """Representation of a tool call requested by the model."""

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    """Outcome of executing a tool call."""

    tool_call_id: str
    output: str
    error: str | None = None
    success: bool = True


@dataclass
class Message:
    """A single message turn in the conversation/history."""

    role: str  # "system", "user", "assistant", or "tool"
    content: str
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass
class LLMResponse:
    """Standardized response from an LLM call."""

    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    finish_reason: str | None = None


@dataclass
class HarnessConfig:
    """Runtime configuration for the coding harness."""

    model: str = "gpt-4o"
    temperature: float = 0.0
    max_iterations: int = 10
    max_tokens: int = 4096
    timeout_seconds: int = 300
    verbose: bool = True

# Added for orchestrator phase 5a
AgentState.file_contents = {}

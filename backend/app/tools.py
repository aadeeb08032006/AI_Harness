"""Tool implementations for the AI Coding Agent Harness.

This module provides the core tool functions that the agent harness can execute
against a target repository: listing files, searching code, reading files,
applying unified diff patches, running test suites, and extracting git diffs.

This module is strictly the toolbox: it performs requested operations and returns
results. It contains no LLM calls, prompt engineering, or orchestration logic.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    from .types import ToolCall, ToolResult
except ImportError:
    try:
        from backend.app.types import ToolCall, ToolResult
    except ImportError:
        ToolCall = Any  # type: ignore[misc, assignment]
        ToolResult = Any  # type: ignore[misc, assignment]


# Directories ignored by repository scanners
DEFAULT_IGNORE_DIRS: set[str] = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".coverage",
    "build",
    "dist",
    ".idea",
    ".vscode",
}

# File names ignored by repository scanners
DEFAULT_IGNORE_FILES: set[str] = {
    ".DS_Store",
    "Thumbs.db",
}

# File extensions skipped by search/read operations as binary
BINARY_EXTENSIONS: set[str] = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".so",
    ".dylib",
    ".dll",
    ".exe",
    ".bin",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".7z",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
}


def _is_binary_file(path: Path) -> bool:
    """Check if a file appears to be binary based on extension and initial bytes."""
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return True
    try:
        with open(path, "rb") as f:
            chunk = f.read(1024)
            return b"\x00" in chunk
    except OSError:
        return True


def list_files(repo_path: str) -> list[str]:
    """Recursively list all file paths inside the repository.

    Args:
        repo_path: Absolute or relative path to the repository directory.

    Returns:
        Sorted list of relative file paths using POSIX forward slashes.
        Returns an empty list if repo_path is invalid or not a directory.
    """
    repo = Path(repo_path).resolve()
    if not repo.is_dir():
        return []

    collected_files: list[str] = []

    for root, dirnames, filenames in os.walk(repo):
        # Prune ignored directories in-place to avoid descending into them
        dirnames[:] = [
            d
            for d in dirnames
            if d not in DEFAULT_IGNORE_DIRS and not d.endswith(".egg-info")
        ]

        for filename in filenames:
            if filename in DEFAULT_IGNORE_FILES:
                continue
            if any(filename.endswith(ext) for ext in (".pyc", ".pyo", ".pyd")):
                continue

            full_path = Path(root) / filename
            try:
                rel_path = full_path.relative_to(repo).as_posix()
                collected_files.append(rel_path)
            except ValueError:
                continue

    return sorted(collected_files)


def search_code(repo_path: str, query: str) -> list[dict[str, Any]]:
    """Search repository source files for matching query text.

    Args:
        repo_path: Path to the repository directory.
        query: Substring text to find in files.

    Returns:
        List of match dictionaries containing:
        - "file_path": Relative file path.
        - "line_number": 1-indexed line number.
        - "line": Matching line content.
        Returns empty list if query is empty, repo is invalid, or no matches found.
    """
    if not query or not query.strip():
        return []

    repo = Path(repo_path).resolve()
    if not repo.is_dir():
        return []

    results: list[dict[str, Any]] = []
    candidate_files = list_files(str(repo))

    for rel_path in candidate_files:
        full_path = repo / rel_path
        if _is_binary_file(full_path):
            continue

        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                for line_num, line in enumerate(f, start=1):
                    if query in line:
                        results.append(
                            {
                                "file_path": rel_path,
                                "line_number": line_num,
                                "line": line.rstrip("\r\n"),
                            }
                        )
        except (OSError, UnicodeError):
            continue

    return results


def read_file(repo_path: str, file_path: str) -> str:
    """Read and return the text contents of a file inside the repository.

    Prevents path traversal attacks and validates file accessibility.

    Args:
        repo_path: Path to the repository root directory.
        file_path: Relative path to the target file.

    Returns:
        The content of the file as a string.

    Raises:
        ValueError: If file_path resolves outside repo_path or target is binary.
        FileNotFoundError: If the file does not exist.
        IsADirectoryError: If the target is a directory rather than a file.
        IOError: If reading the file fails due to OS or permission errors.
    """
    repo = Path(repo_path).resolve()
    if not repo.is_dir():
        raise ValueError(f"Repository directory does not exist: {repo_path}")

    target = Path(file_path)
    resolved_target = (repo / target).resolve() if not target.is_absolute() else target.resolve()

    try:
        resolved_target.relative_to(repo)
    except ValueError:
        raise ValueError(
            f"Path traversal detected: '{file_path}' resolves outside repository root."
        )

    if not resolved_target.exists():
        raise FileNotFoundError(f"File not found: '{file_path}'")

    if resolved_target.is_dir():
        raise IsADirectoryError(f"Target path is a directory, not a file: '{file_path}'")

    if _is_binary_file(resolved_target):
        raise ValueError(f"Cannot read binary or non-text file: '{file_path}'")

    try:
        with open(resolved_target, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        try:
            with open(resolved_target, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except OSError as e:
            raise IOError(f"Could not read file '{file_path}': {e}") from e
    except OSError as e:
        raise IOError(f"Could not read file '{file_path}': {e}") from e


def _clean_patch_text(patch: str) -> str:
    """Strip markdown code fence wrappers from patch text if present."""
    text = patch.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _extract_patch_files(patch: str) -> list[str]:
    """Extract list of target file paths from a unified diff patch."""
    target_files: set[str] = set()
    for line in patch.splitlines():
        if line.startswith("--- ") or line.startswith("+++ "):
            parts = line[4:].strip().split()
            if not parts:
                continue
            raw_path = parts[0]
            if raw_path == "/dev/null":
                continue
            if raw_path.startswith("a/") or raw_path.startswith("b/"):
                raw_path = raw_path[2:]
            clean = raw_path.strip("\"'")
            if clean and clean != "/dev/null":
                target_files.add(clean)
    return sorted(target_files)


def apply_patch(repo_path: str, patch: str) -> dict[str, Any]:
    """Apply a unified diff patch to files in the repository.

    Validates patch safety, rejects path traversal attempts, and atomically applies
    the patch using git apply.

    Args:
        repo_path: Path to the target repository directory.
        patch: Unified diff string (can be wrapped in markdown code fences).

    Returns:
        Dictionary containing:
        - "success": bool indicating whether patch application succeeded.
        - "files_changed": list of relative file paths affected.
        - "output": descriptive output message or stderr.
        - "error": error message if failed, None if successful.
    """
    repo = Path(repo_path).resolve()
    if not repo.is_dir():
        return {
            "success": False,
            "files_changed": [],
            "output": f"Repository directory not found: {repo_path}",
            "error": f"Repository directory not found: {repo_path}",
        }

    clean_patch = _clean_patch_text(patch)
    if not clean_patch:
        return {
            "success": False,
            "files_changed": [],
            "output": "Empty patch provided.",
            "error": "Empty patch provided.",
        }

    # Ensure it contains unified diff indicators
    has_headers = any(
        line.startswith(("--- ", "+++ ", "@@ ", "diff --git "))
        for line in clean_patch.splitlines()
    )
    if not has_headers:
        return {
            "success": False,
            "files_changed": [],
            "output": "Invalid patch: no unified diff headers found.",
            "error": "Invalid patch: no unified diff headers found.",
        }

    # Security check: ensure no target path escapes repo_path
    target_files = _extract_patch_files(clean_patch)
    for target in target_files:
        p = Path(target)
        resolved_file = (repo / p).resolve() if not p.is_absolute() else p.resolve()
        try:
            resolved_file.relative_to(repo)
        except ValueError:
            return {
                "success": False,
                "files_changed": [],
                "output": f"Security error: patch targets file outside repository: '{target}'",
                "error": f"Security error: patch targets file outside repository: '{target}'",
            }

    # Ensure patch ends with a newline
    if not clean_patch.endswith("\n"):
        clean_patch += "\n"

    # Try applying with git apply (-p1 then -p0)
    git_bin = shutil.which("git")
    if git_bin:
        for p_flag in ["-p1", "-p0"]:
            proc = subprocess.run(
                [git_bin, "apply", "--whitespace=nowarn", p_flag],
                input=clean_patch,
                cwd=str(repo),
                capture_output=True,
                text=True,
            )
            if proc.returncode == 0:
                return {
                    "success": True,
                    "files_changed": target_files,
                    "output": f"Successfully applied patch to {len(target_files)} file(s).",
                    "error": None,
                }
        error_msg = proc.stderr.strip() or proc.stdout.strip() or "git apply failed."
    else:
        # Fall back to patch utility if git is unavailable
        patch_bin = shutil.which("patch")
        if patch_bin:
            for p_flag in ["-p1", "-p0"]:
                proc = subprocess.run(
                    [patch_bin, p_flag, "--batch", "--forward"],
                    input=clean_patch,
                    cwd=str(repo),
                    capture_output=True,
                    text=True,
                )
                if proc.returncode == 0:
                    return {
                        "success": True,
                        "files_changed": target_files,
                        "output": f"Successfully applied patch to {len(target_files)} file(s).",
                        "error": None,
                    }
            error_msg = proc.stderr.strip() or "patch utility failed."
        else:
            error_msg = "Neither git nor patch command found on system to apply patch."

    # Custom fallback for LLM-generated malformed patches (e.g. without line numbers)
    # Tries to do a simple string replace for each file
    if target_files:
        try:
            for target in target_files:
                target_path = repo / target
                if not target_path.exists():
                    continue
                
                with open(target_path, "r", encoding="utf-8") as f:
                    original_content = f.read()

                # Extract the old text and new text from the patch by hunks
                lines = clean_patch.splitlines()
                hunks = []
                current_hunk = {"old": [], "new": []}
                in_hunk = False
                
                for line in lines:
                    if line.startswith("@@"):
                        if in_hunk and (current_hunk["old"] or current_hunk["new"]):
                            hunks.append(current_hunk)
                        current_hunk = {"old": [], "new": []}
                        in_hunk = True
                        continue
                    if in_hunk:
                        if line.startswith("-"):
                            current_hunk["old"].append(line[1:])
                        elif line.startswith("+"):
                            current_hunk["new"].append(line[1:])
                        elif line.startswith(" ") or line == "":
                            line_content = line[1:] if line else ""
                            current_hunk["old"].append(line_content)
                            current_hunk["new"].append(line_content)
                        elif line.startswith("\\ No newline"):
                            continue

                if in_hunk and (current_hunk["old"] or current_hunk["new"]):
                    hunks.append(current_hunk)

                updated_content = original_content
                success_hunks = 0
                for hunk in hunks:
                    old_text = "\n".join(hunk["old"]) + "\n"
                    new_text = "\n".join(hunk["new"]) + "\n"
                    # Also try without trailing newline if exact match fails
                    if old_text not in updated_content:
                        old_text = "\n".join(hunk["old"])
                        new_text = "\n".join(hunk["new"])
                        
                    if old_text in updated_content:
                        updated_content = updated_content.replace(old_text, new_text, 1)
                        success_hunks += 1

                if success_hunks > 0:
                    with open(target_path, "w", encoding="utf-8") as f:
                        f.write(updated_content)
                    return {
                        "success": True,
                        "files_changed": [target],
                        "output": f"Successfully applied {success_hunks}/{len(hunks)} hunks via simple string replacement.",
                        "error": None if success_hunks == len(hunks) else "Some hunks failed to apply.",
                    }
        except Exception as e:
            error_msg += f"\nCustom replace fallback also failed: {e}"

    return {
        "success": False,
        "files_changed": [],
        "output": error_msg,
        "error": error_msg,
    }


def run_tests(
    repo_path: str,
    test_command: str | list[str] | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    """Run project test suite and capture output and status.

    Initially supports pytest for Python projects. Test failures are returned as a
    result structure, never raised as Python exceptions.

    Args:
        repo_path: Path to the repository directory.
        test_command: Optional custom test command string or argument list.
                      Defaults to pytest.
        timeout: Maximum execution time in seconds (default 60).

    Returns:
        Dictionary containing:
        - "success": bool (True if all tests passed, exit_code 0).
        - "exit_code": int exit code from the test runner.
        - "stdout": captured standard output.
        - "stderr": captured standard error.
        - "output": combined human-readable test output.
    """
    repo = Path(repo_path).resolve()
    if not repo.is_dir():
        return {
            "success": False,
            "exit_code": 1,
            "stdout": "",
            "stderr": f"Repository directory not found: {repo_path}",
            "output": f"Repository directory not found: {repo_path}",
        }

    # Determine command to execute
    if test_command:
        if isinstance(test_command, str):
            cmd = shlex.split(test_command)
        else:
            cmd = list(test_command)
    else:
        # Try pytest first, fall back to unittest discover
        if shutil.which("pytest"):
            cmd = ["pytest", "-v", "--tb=short"]
        else:
            # Check if there's a pytest in the current python env
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pytest", "--version"],
                    capture_output=True, timeout=5
                )
                if result.returncode == 0:
                    cmd = [sys.executable, "-m", "pytest", "-v", "--tb=short"]
                else:
                    cmd = [sys.executable, "-m", "unittest", "discover", "-v"]
            except Exception:
                cmd = [sys.executable, "-m", "unittest", "discover", "-v"]

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        exit_code = proc.returncode
        success = (exit_code == 0)
        output = stdout if not stderr else (f"{stdout}\n{stderr}" if stdout else stderr)
        # Cap output to keep LLM context lean (last 3000 chars is enough)
        output_trimmed = output.strip()
        if len(output_trimmed) > 3000:
            output_trimmed = "...\n" + output_trimmed[-3000:]

        return {
            "success": success,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "output": output_trimmed,
        }
    except subprocess.TimeoutExpired as e:
        stdout = (e.stdout or "") if isinstance(e.stdout, str) else ""
        stderr = f"Test execution timed out after {timeout} seconds."
        return {
            "success": False,
            "exit_code": 124,
            "stdout": stdout,
            "stderr": stderr,
            "output": (f"{stdout}\n{stderr}" if len(stdout) > 0 else stderr).strip(),
        }
    except FileNotFoundError as e:
        err = f"Test runner executable not found: {e}"
        return {
            "success": False,
            "exit_code": 127,
            "stdout": "",
            "stderr": err,
            "output": err,
        }
    except Exception as e:
        err = f"Unexpected error during test execution: {e}"
        return {
            "success": False,
            "exit_code": 1,
            "stdout": "",
            "stderr": err,
            "output": err,
        }


def git_diff(repo_path: str) -> str:
    """Return the current Git diff in the repository.

    Executes the equivalent of git diff without modifying repository state.
    Gracefully handles non-git repositories and clean states.

    Args:
        repo_path: Path to the target repository directory.

    Returns:
        Unified git diff string, or empty string if clean or not a git repository.
    """
    repo = Path(repo_path).resolve()
    if not repo.is_dir():
        return ""

    git_bin = shutil.which("git")
    if not git_bin:
        return ""

    try:
        # Validate that repo_path is inside a git working tree
        verify = subprocess.run(
            [git_bin, "rev-parse", "--is-inside-work-tree"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if verify.returncode != 0:
            return ""

        # Check diff against HEAD (captures both staged and unstaged changes)
        proc = subprocess.run(
            [git_bin, "diff", "HEAD"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=15,
        )
        if proc.returncode == 0:
            return proc.stdout

        # Fallback to plain git diff if HEAD has not yet been committed
        fallback = subprocess.run(
            [git_bin, "diff"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=15,
        )
        if fallback.returncode == 0:
            return fallback.stdout

        return ""
    except (subprocess.SubprocessError, OSError):
        return ""


def run_command(repo_path: str, command: str, timeout: int = 15) -> str:
    """Execute a local shell command safely within the repository root.

    Args:
        repo_path: Path to the target repository directory.
        command: The shell command to execute.
        timeout: Execution timeout in seconds.

    Returns:
        String containing exit code and combined stdout/stderr.
    """
    repo = Path(repo_path).resolve()
    if not repo.is_dir():
        return f"Error: Repository directory not found: {repo_path}"

    # Basic static analysis to block dangerous commands
    dangerous_tokens = {"shutdown", "reboot", "mkfs", "dd", "nc", "ncat"}
    dangerous_substrings = ["rm -rf", "rm -f", "wget", "curl", "> /dev/"]
    
    cmd_lower = command.lower()
    for sub in dangerous_substrings:
        if sub in cmd_lower:
            return f"Error: Command blocked by security policy (dangerous pattern '{sub}' detected)."
            
    tokens = cmd_lower.split()
    if any(token in dangerous_tokens for token in tokens):
        return f"Error: Command blocked by security policy (dangerous command detected)."
        
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = proc.stdout.strip()
        err = proc.stderr.strip()
        result = f"Exit code: {proc.returncode}\n"
        if out:
            result += f"Stdout:\n{out}\n"
        if err:
            result += f"Stderr:\n{err}\n"
        return result
    except subprocess.TimeoutExpired:
        return f"Error: Command execution timed out after {timeout} seconds."
    except Exception as e:
        return f"Error: Unexpected error executing command: {e}"


def write_file(repo_path: str, file_path: str, content: str) -> dict[str, Any]:
    """Write (overwrite) a file inside the repository with new content.

    A simpler alternative to apply_patch — useful when the model wants to
    rewrite an entire file rather than produce a diff.

    Args:
        repo_path: Path to the repository root directory.
        file_path: Relative path to the target file.
        content: Full new content to write to the file.

    Returns:
        Dictionary with 'success', 'files_changed', 'output', 'error'.
    """
    repo = Path(repo_path).resolve()
    if not repo.is_dir():
        return {
            "success": False,
            "files_changed": [],
            "output": f"Repository directory not found: {repo_path}",
            "error": f"Repository directory not found: {repo_path}",
        }

    target = Path(file_path)
    resolved = (repo / target).resolve() if not target.is_absolute() else target.resolve()

    try:
        resolved.relative_to(repo)
    except ValueError:
        return {
            "success": False,
            "files_changed": [],
            "output": f"Security error: path '{file_path}' resolves outside repository.",
            "error": f"Security error: path '{file_path}' resolves outside repository.",
        }

    resolved.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(resolved, "w", encoding="utf-8") as f:
            f.write(content)
        return {
            "success": True,
            "files_changed": [file_path],
            "output": f"Successfully wrote {len(content)} bytes to '{file_path}'.",
            "error": None,
        }
    except OSError as e:
        return {
            "success": False,
            "files_changed": [],
            "output": f"Failed to write file: {e}",
            "error": str(e),
        }


# Convenience map of all available tools for orchestrators
AVAILABLE_TOOLS: dict[str, Any] = {
    "list_files": list_files,
    "search_code": search_code,
    "read_file": read_file,
    "write_file": write_file,
    "apply_patch": apply_patch,
    "run_tests": run_tests,
    "git_diff": git_diff,
    "run_command": run_command,
}

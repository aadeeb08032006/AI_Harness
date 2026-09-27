try:
    from .types import AgentState, Status
    from .llm_provider import get_provider
    from .context_manager import build_context
    from .verifier import verify
    from . import tools
except ImportError:
    try:
        from backend.app.types import AgentState, Status
        from backend.app.llm_provider import get_provider
        from backend.app.context_manager import build_context
        from backend.app.verifier import verify
        from backend.app import tools
    except ImportError:
        from types import AgentState, Status  # type: ignore[no-redef]
        from llm_provider import get_provider  # type: ignore[no-redef]
        from context_manager import build_context  # type: ignore[no-redef]
        from verifier import verify  # type: ignore[no-redef]
        import tools  # type: ignore[no-redef]

SYSTEM_PROMPT = """\
You are an autonomous software-engineering agent. Your ONLY goal is to make the test suite pass.

WORKFLOW (follow exactly):
1. Call list_files to see the repo.
2. Call read_file on each relevant source and test file.
3. Call run_tests to see the current failures.
4. Call write_file with the COMPLETE corrected file content to fix ALL bugs at once.
5. Call run_tests again to verify. If still failing, repeat from step 4.

RULES:
- NEVER invent file contents. Always read first.
- PREFER write_file over apply_patch — write the entire corrected file content.
- run_tests uses: python -m pytest, or python -m unittest discover if pytest is unavailable.
- Fix ALL bugs in a SINGLE write_file call. Do not fix one bug at a time.
- You have a limited number of iterations. Be decisive — fix everything at once.
"""

DOC_SYSTEM_PROMPT = """\
You are an autonomous software-engineering agent making documentation changes.

WORKFLOW (follow exactly):
1. Call list_files to find the relevant documentation file.
2. Call read_file to read its current content.
3. Call write_file with the COMPLETE updated file content including your changes.
4. You are DONE after a successful write_file call.

RULES:
- NEVER invent file contents. Always read before writing.
- Use write_file to overwrite the file with the complete updated content.
- Make only the minimal necessary change described in the task.
- Be decisive — read once, write once. Do not loop.
- You have very few iterations. Act immediately after reading the file.
"""

TOOLS = [
    {
        "name": "list_files",
        "description": "List all files in the repository",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "search_code",
        "description": "Search repository code for a query string",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "read_file",
        "description": "Read the full contents of a file",
        "input_schema": {
            "type": "object",
            "properties": {"file_path": {"type": "string"}},
            "required": ["file_path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write (overwrite) a file in the repository with new content. PREFERRED over apply_patch for fixing bugs — just supply the complete corrected file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Relative path to the file to write"},
                "content": {"type": "string", "description": "Complete new file content"}
            },
            "required": ["file_path", "content"],
        },
    },
    {
        "name": "apply_patch",
        "description": "Apply a unified diff patch to a file. The patch must be a valid unified diff starting with --- and +++ headers.",
        "input_schema": {
            "type": "object",
            "properties": {"patch": {"type": "string"}},
            "required": ["patch"],
        },
    },
    {
        "name": "run_tests",
        "description": "Run the repository test suite",
        "input_schema": {
            "type": "object",
            "properties": {
                "test_command": {
                    "type": ["string", "array", "null"],
                    "description": "Optional custom test command"
                }
            },
            "required": [],
        },
    },
    {
        "name": "git_diff",
        "description": "Get the current git diff of the repository",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "run_command",
        "description": "Execute a safe shell command within the repository root",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The command to run"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default 15)"}
            },
            "required": ["command"],
        },
    }
]

def execute_tool(name: str, tool_input: dict, repo_path: str, state: AgentState) -> tuple[str, bool]:
    """Returns (result_text, is_error)."""
    try:
        if name == "list_files":
            result = tools.list_files(repo_path)
            return (str(result), False)
        elif name == "search_code":
            result = tools.search_code(repo_path, tool_input["query"])
            return (str(result), False)
        elif name == "read_file":
            try:
                result = tools.read_file(repo_path, tool_input["file_path"])
                return (str(result), False)
            except (FileNotFoundError, IsADirectoryError, ValueError, IOError) as e:
                return (f"Error: {e}", True)
        elif name == "write_file":
            result = tools.write_file(repo_path, tool_input["file_path"], tool_input["content"])
            if result.get("success"):
                for changed_file in result.get("files_changed", []):
                    if changed_file not in state.files_changed:
                        state.files_changed.append(changed_file)
                return (result.get("output", "Success"), False)
            else:
                return (f"write_file failed: {result.get('error', 'Unknown error')}", True)
        elif name == "apply_patch":
            result = tools.apply_patch(repo_path, tool_input["patch"])
            if result.get("success"):
                for changed_file in result.get("files_changed", []):
                    if changed_file not in state.files_changed:
                        state.files_changed.append(changed_file)
                return (result.get("output", "Success"), False)
            else:
                return (f"Patch failed: {result.get('error', 'Unknown error')}", True)
        elif name == "run_tests":
            result = tools.run_tests(repo_path, test_command=tool_input.get("test_command"))
            if result.get("success"):
                return (result.get("output", "Tests passed"), False)
            else:
                return (result.get("output", "Tests failed"), True)
        elif name == "git_diff":
            result = tools.git_diff(repo_path)
            return (result if result else "(no changes)", False)
        elif name == "run_command":
            result = tools.run_command(repo_path, tool_input["command"], timeout=tool_input.get("timeout", 15))
            is_error = result.startswith("Error:")
            return (result, is_error)
        else:
            return (f"Unknown tool: {name}", True)
    except KeyError as e:
        return (f"Missing required argument: {e}", True)
    except Exception as e:
        return (f"Tool execution failed: {type(e).__name__}: {e}", True)

from typing import Callable, Any


def _trim_messages(state: "AgentState", keep_last: int = 6) -> None:
    """Trim the conversation history to keep context lean.
    
    Keeps the first user message (task context) and the last `keep_last`
    messages to prevent context bloat across fixing iterations.
    """
    if len(state.messages) <= keep_last + 1:
        return
    # Always keep the first message (original task + file hint)
    first = state.messages[:1]
    tail = state.messages[-(keep_last):]
    state.messages = first + tail


def run_harness_loop(task: str, repo_path: str, max_iterations: int = 5, no_verify: bool = False) -> AgentState:
    state = AgentState(task=task, repo_path=repo_path, max_iterations=max_iterations)
    system = DOC_SYSTEM_PROMPT if no_verify else SYSTEM_PROMPT
    try:
        state.status = Status.ANALYZING

        context = build_context(repo_path, task)
        state.files = context["all_files"]
        state.relevant_files = context["relevant_files"]
        state.file_contents = context["file_contents"]

        # Token-efficient: don't dump all file contents upfront.
        # Let the model discover files via tool calls (read_file).
        # Only include a compact file listing as a hint.
        relevant_hint = ", ".join(context["relevant_files"]) if context["relevant_files"] else "(none detected)"
        initial_message = (
            f"Task: {task}\n\n"
            f"Repository path: {repo_path}\n"
            f"Likely relevant files: {relevant_hint}\n\n"
            "Start by calling list_files, then read_file on each relevant file, "
            "then run_tests to see current failures, then apply_patch to fix them all at once."
        )
        state.messages = [{"role": "user", "content": initial_message}]

        state.status = Status.CODING
        llm = get_provider()
    
        while not state.budget_exhausted():
            response = llm.generate(state.messages, system=system, tools=TOOLS)

            if response.stop_reason == "error":
                state.add_error(f"LLM call failed: {response.raw}")
                state.status = Status.FAILED
                return state

            state.messages.append(llm.format_assistant_message(response))

            if response.tool_calls:
                for call in response.tool_calls:
                    result_text, is_error = execute_tool(call["name"], call["input"], repo_path, state)
                    state.messages.append(llm.format_tool_result(call["id"], result_text, is_error))
                    if call["name"] == "apply_patch" and not is_error:
                        state.patch = call["input"].get("patch")
                state.iteration += 1
                continue
            else:
                state.plan = response.text
                break   # model stopped requesting tools — ready for verification

        # If no_verify is set (e.g. doc-only task), skip test verification entirely.
        # Treat a successful write as completion.
        if no_verify:
            if state.files_changed:
                state.status = Status.COMPLETED
                state.tests_passed = True
                state.test_output = "Verification skipped (--no-verify). Files were modified successfully."
            else:
                state.status = Status.FAILED
                state.add_error("No files were changed. Task may not have been completed.")
            return state

        state.status = Status.VERIFYING
        verification = verify(repo_path)
        state.test_output = verification.output
        state.tests_passed = verification.verified
        
        if not verification.verified and verification.error:
            state.add_error(verification.error)

        while not state.tests_passed and not state.budget_exhausted():
            state.status = Status.FIXING
            
            # Trim oldest tool result messages to keep context lean.
            # Keep system + first user message + last N exchanges.
            _trim_messages(state, keep_last=6)
            
            state.messages.append({
                "role": "user",
                "content": (
                    f"Tests STILL failing (iteration {state.iteration}/{state.max_iterations}).\n"
                    f"Output:\n{state.test_output}\n\n"
                    "Re-read the file you modified, understand what went wrong, and apply a COMPLETE corrected patch."
                )
            })
            response = llm.generate(state.messages, system=system, tools=TOOLS)
            if response.stop_reason == "error":
                state.add_error(f"LLM call failed during recovery: {response.raw}")
                state.status = Status.FAILED
                return state
                
            state.messages.append(llm.format_assistant_message(response))

            if response.tool_calls:
                for call in response.tool_calls:
                    result_text, is_error = execute_tool(call["name"], call["input"], repo_path, state)
                    state.messages.append(llm.format_tool_result(call["id"], result_text, is_error))
                    if call["name"] == "apply_patch" and not is_error:
                        state.patch = call["input"].get("patch")

            state.status = Status.VERIFYING
            verification = verify(repo_path)
            state.test_output = verification.output
            state.tests_passed = verification.verified
            
            if not verification.verified and verification.error:
                state.add_error(verification.error)
            state.iteration += 1

        if state.tests_passed:
            state.status = Status.COMPLETED
        else:
            state.status = Status.FAILED
            state.add_error("max iterations reached without passing tests")

        return state
    except Exception as e:
        state.status = Status.FAILED
        state.add_error(f"Unhandled exception: {type(e).__name__}: {e}")
        return state

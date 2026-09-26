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
You are an autonomous software-engineering agent working inside a harness.
Rules:
- Inspect before modifying.
- Use tools to gather evidence; never invent file contents.
- Make minimal necessary changes.
- Follow existing project conventions.
- Treat test failures as feedback, not final outcomes.
- Do not claim success without verification. The harness alone determines success.
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
        "name": "apply_patch",
        "description": "Apply a code patch to a file",
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
        else:
            return (f"Unknown tool: {name}", True)
    except KeyError as e:
        return (f"Missing required argument: {e}", True)
    except Exception as e:
        return (f"Tool execution failed: {type(e).__name__}: {e}", True)

def run_harness_loop(task: str, repo_path: str, max_iterations: int = 5) -> AgentState:
    state = AgentState(task=task, repo_path=repo_path, max_iterations=max_iterations)
    try:
        state.status = Status.ANALYZING

        context = build_context(repo_path, task)
        state.files = context["all_files"]
        state.relevant_files = context["relevant_files"]
        state.file_contents = context["file_contents"]

        context_text = "\n\n".join(
            f"=== {path} ===\n{content}" for path, content in context["file_contents"].items()
        )
        initial_message = (
            f"Task: {task}\n\nRelevant repository files:\n{context_text}"
        )
        state.messages = [{"role": "user", "content": initial_message}]

        state.status = Status.CODING
        llm = get_provider()
    
        while not state.budget_exhausted():
            response = llm.generate(state.messages, system=SYSTEM_PROMPT, tools=TOOLS)

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

        state.status = Status.VERIFYING
        verification = verify(repo_path)
        state.test_output = verification.output
        state.tests_passed = verification.verified
        if not verification.verified and verification.error:
            state.add_error(verification.error)

        while not state.tests_passed and not state.budget_exhausted():
            state.status = Status.FIXING
            state.messages.append({
                "role": "user",
                "content": (
                    f"Tests failed. Output:\n{state.test_output}\n\n"
                    "Diagnose the failure and apply a corrected patch. "
                    "Do not claim success — the harness will re-run tests to verify."
                )
            })
            response = llm.generate(state.messages, system=SYSTEM_PROMPT, tools=TOOLS)
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
            # files_changed is already populated by execute_tool's apply_patch
            # branch (from result["files_changed"]) — do NOT re-derive it by
            # parsing git_diff text here, that logic no longer belongs in this block
        else:
            state.status = Status.FAILED
            state.add_error("max iterations reached without passing tests")

        return state
    except Exception as e:
        state.status = Status.FAILED
        state.add_error(f"Unhandled exception: {type(e).__name__}: {e}")
        return state

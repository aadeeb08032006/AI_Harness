from .types import AgentState, Status
from .llm_provider import AnthropicProvider, format_assistant_message
from .context_manager import build_context

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

def run_harness_loop(task: str, repo_path: str, max_iterations: int = 5) -> AgentState:
    state = AgentState(task=task, repo_path=repo_path, max_iterations=max_iterations)
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

    state.status = Status.PLANNING
    llm = AnthropicProvider()
    response = llm.generate(state.messages, system=SYSTEM_PROMPT)
    state.plan = response.text
    state.status = Status.COMPLETED
    return state

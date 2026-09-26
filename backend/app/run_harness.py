import argparse
import json
import os
import sys
from typing import Sequence
from dotenv import load_dotenv

load_dotenv()

try:
    from .orchestrator import run_harness_loop
except ImportError:
    try:
        from backend.app.orchestrator import run_harness_loop
    except ImportError:
        from orchestrator import run_harness_loop  # type: ignore[no-redef]


def main(args_list: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the AI Coding Agent Harness on a repository task.")
    parser.add_argument("--repo", required=True, help="Path to the target repository.")
    parser.add_argument("--task", required=True, help="Task description or issue prompt.")
    parser.add_argument("--max-iterations", type=int, default=5, help="Maximum allowed iterations.")
    args = parser.parse_args(args_list)

    state = run_harness_loop(args.task, args.repo, args.max_iterations)
    result = state.to_result_dict()

    os.makedirs("outputs", exist_ok=True)
    with open("outputs/result.json", "w") as f:
        json.dump(result, f, indent=2)

    print(json.dumps(result, indent=2))

    exit_code = 0 if result["status"] == "COMPLETED" else 1
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()

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
    parser.add_argument("task", help="Task description or issue prompt.")
    parser.add_argument("--repo", default="./sample_repo", help="Path to the target repository (default: ./sample_repo).")
    parser.add_argument("--max-steps", type=int, default=8, help="Maximum allowed iterations/steps.")
    parser.add_argument("--max-tool-calls", type=int, default=30, help="Maximum tool invocations.")
    parser.add_argument("--trace", action="store_true", help="Show full execution trace.")
    parser.add_argument("--json", action="store_true", help="Return machine-readable JSON.")
    parser.add_argument("--findings", action="store_true", help="Show raw tool findings.")
    parser.add_argument("--no-color", action="store_true", help="Disable terminal colors.")
    parser.add_argument("--dry-run", action="store_true", help="Do not modify files.")
    parser.add_argument("--allow-write", action="store_true", help="Allow code modification tools.")
    parser.add_argument("--run-tests", action="store_true", help="Force verification/test execution.")
    parser.add_argument("--auto-approve", action="store_true", help="Skip interactive approval for safe local write operations.")
    args = parser.parse_args(args_list)

    if not args.json:
        if not args.no_color:
            print("\033[1m========================================\033[0m")
            print("\033[1m         AI CODING HARNESS\033[0m")
            print("\033[1m========================================\033[0m")
            print(f"\n\033[1mTask:\033[0m\n{args.task}\n")
            print(f"\033[1mRepository:\033[0m\n{args.repo}\n")
            print("\033[1m----------------------------------------\033[0m")
            print("\033[1mPIPELINE\033[0m")
            print("\033[1m----------------------------------------\033[0m")
        else:
            print("========================================")
            print("         AI CODING HARNESS")
            print("========================================")
            print(f"\nTask:\n{args.task}\n")
            print(f"Repository:\n{args.repo}\n")
            print("----------------------------------------")
            print("PIPELINE")
            print("----------------------------------------")

    # In a full implementation, we'd pass config down to restrict writes, etc.
    # Currently passing max_steps via max_iterations argument for backward compatibility
    state = run_harness_loop(args.task, args.repo, args.max_steps)
    result = state.to_result_dict()

    os.makedirs("outputs", exist_ok=True)
    with open("outputs/result.json", "w") as f:
        json.dump(result, f, indent=2)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if not args.no_color:
            print("\n\033[1m----------------------------------------\033[0m")
            print("\033[1mVERIFICATION\033[0m")
            print("\033[1m----------------------------------------\033[0m\n")
            if state.tests_passed:
                print(f"STATUS: \033[32mVERIFIED ✓\033[0m")
            else:
                print(f"STATUS: \033[31mFAILED ✗\033[0m")
            print(f"\nFiles changed:  {len(state.files_changed)}")
            print(f"Iterations:     {state.iteration}")
            
            print("\n\033[1m----------------------------------------\033[0m")
            print("\033[1mCHANGES\033[0m")
            print("\033[1m----------------------------------------\033[0m")
            for f in state.files_changed:
                print(f)
            print("\n\033[1m========================================\033[0m")
        else:
            print("\n----------------------------------------")
            print("VERIFICATION")
            print("----------------------------------------\n")
            if state.tests_passed:
                print("STATUS: VERIFIED ✓")
            else:
                print("STATUS: FAILED ✗")
            print(f"\nFiles changed:  {len(state.files_changed)}")
            print(f"Iterations:     {state.iteration}")
            
            print("\n----------------------------------------")
            print("CHANGES")
            print("----------------------------------------")
            for f in state.files_changed:
                print(f)
            print("\n========================================")

    exit_code = 0 if result["status"] == "COMPLETED" else 1
    raise SystemExit(exit_code)

if __name__ == "__main__":
    main()

import argparse, json, os
from dotenv import load_dotenv
load_dotenv()
from .orchestrator import run_harness_loop

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--max-iterations", type=int, default=5)
    args = parser.parse_args()

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

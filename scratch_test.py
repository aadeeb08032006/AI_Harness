import os
import sys

# Set a dummy API key so the initialization doesn't fail
os.environ["ANTHROPIC_API_KEY"] = "sk-ant-api03-dummy-key"

# Add current dir to python path
sys.path.insert(0, os.path.abspath("."))

from backend.app.orchestrator import run_harness_loop

def test():
    print("Running test harness loop...")
    try:
        state = run_harness_loop(task="Implement a basic orchestrator loop", repo_path=".", max_iterations=1)
        print("--- HARNESS LOOP FINISHED ---")
        print(f"Status: {state.status}")
        print(f"Plan generated:\n{state.plan}")
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test()

import os
import sys

sys.path.insert(0, os.path.abspath("."))
from backend.app.orchestrator import run_harness_loop

def test_missing_key():
    print("TEST 1: Missing API Key")
    if "GROQ_API_KEY" in os.environ:
        del os.environ["GROQ_API_KEY"]
    state = run_harness_loop("test", ".")
    print(f"Type: {type(state).__name__}")
    print(f"Status: {state.status.value}")
    print(f"Errors: {state.errors}")
    print("-" * 20)

def test_bad_repo():
    print("TEST 2: Invalid Repo Path with a dummy key")
    os.environ["GROQ_API_KEY"] = "sk-ant-dummy-key"
    state = run_harness_loop("test", "/path/that/does/not/exist/12345")
    print(f"Type: {type(state).__name__}")
    print(f"Status: {state.status.value}")
    print(f"Errors: {state.errors}")
    print("-" * 20)

if __name__ == "__main__":
    test_missing_key()
    test_bad_repo()

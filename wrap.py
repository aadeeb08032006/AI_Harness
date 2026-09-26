import sys

with open("backend/app/orchestrator.py", "r") as f:
    lines = f.readlines()

new_lines = []
in_func = False
for line in lines:
    if line.startswith("def run_harness_loop("):
        new_lines.append(line)
        in_func = True
        continue
    
    if in_func:
        if line.strip() == "state = AgentState(task=task, repo_path=repo_path, max_iterations=max_iterations)":
            new_lines.append(line)
            new_lines.append("    try:\n")
        else:
            if line.strip() == "":
                new_lines.append(line)
            else:
                new_lines.append("    " + line)
    else:
        new_lines.append(line)

new_lines.append("    except Exception as e:\n")
new_lines.append("        state.status = Status.FAILED\n")
new_lines.append("        state.errors.append(f\"Unhandled exception: {type(e).__name__}: {e}\")\n")
new_lines.append("        return state\n")

with open("backend/app/orchestrator.py", "w") as f:
    f.writelines(new_lines)

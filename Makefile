.PHONY: setup run test clean

# Hackathon standard variables
TASK ?= "Please provide a task description via TASK='...'"
REPO ?= "/tmp/flask_test"

setup:
	@echo "Setting up environment..."
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements.txt

run:
	@echo "Starting AI Harness..."
	# Ensure AI_API_KEY is available, or at least let the python script handle the missing key
	.venv/bin/python -m backend.app.run_harness "$(TASK)" --repo "$(REPO)"

test:
	@echo "Running tests..."
	.venv/bin/pytest tests/ || echo "No tests available yet."

clean:
	@echo "Cleaning up generated artifacts..."
	rm -rf .venv
	find . -type d -name "__pycache__" -exec rm -r {} +
	find . -type d -name ".pytest_cache" -exec rm -r {} +

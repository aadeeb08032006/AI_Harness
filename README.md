# AI Coding Harness

A local, CLI-first AI coding agent harness for hackathons and rapid iteration.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Running the CLI

The CLI is the primary way to interact with the harness.

```bash
./scripts/harness "Find the authentication bug." --repo ./sample_repo
```

To view a detailed execution trace:
```bash
./scripts/harness "Find the authentication bug." --repo ./sample_repo --trace
```

To output machine-readable JSON:
```bash
./scripts/harness "Find the authentication bug." --repo ./sample_repo --json
```

## Testing

Run the internal test suite:
```bash
python3 -m pytest -q
```

Run the demo cases script:
```bash
./scripts/demo_cases.sh
```

## Run Web Backend
(If using the FastAPI implementation)
```bash
uvicorn backend.app.main:app --reload
```

"""Syncs the deployed ApiUrl into the repo-root .env after a `cdk deploy --outputs-file`.

The frontend build bakes in VITE_API_BASE_URL at build time, but on a stack's first-ever
deploy that value doesn't exist yet in .env - it's only known once `cdk deploy` finishes and
prints it. This script closes that loop: read the ApiUrl CDK just wrote to a JSON outputs
file, and write it into .env so a second `cdk deploy` rebuilds the frontend against the real
backend URL (see `make deploy` in the repo-root Makefile).
"""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUTS_FILE = REPO_ROOT / "infra" / "cdk-outputs.json"
ENV_FILE = REPO_ROOT / ".env"
STACK_NAME = "CanIEatThisStack"


def main() -> None:
    """Reads ApiUrl from the CDK outputs file and writes it into .env as VITE_API_BASE_URL."""
    outputs = json.loads(OUTPUTS_FILE.read_text())[STACK_NAME]
    api_url = outputs["ApiUrl"]

    lines = ENV_FILE.read_text().splitlines() if ENV_FILE.exists() else []
    lines = [line for line in lines if not line.startswith("VITE_API_BASE_URL=")]
    lines.append(f"VITE_API_BASE_URL={api_url}")
    ENV_FILE.write_text("\n".join(lines) + "\n")

    print(f"Set VITE_API_BASE_URL={api_url} in {ENV_FILE}")


if __name__ == "__main__":
    main()

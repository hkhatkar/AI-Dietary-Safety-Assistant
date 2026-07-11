.PHONY: deploy destroy backend-dev frontend-dev

# One-command deploy: creates/updates all AWS infra, syncs the real ApiUrl into .env, then
# redeploys so the frontend build picks it up. The second `cdk deploy` is a no-op for the
# infra itself (nothing about it changed) - it only rebuilds and re-uploads the frontend.
#
# Uses --require-approval never so this can run start-to-finish without an interactive
# prompt. That skips CDK's normal pause-for-review on IAM/security-group changes - fine for
# this project's own single-account use, but drop the flag (or run `cd infra && npx cdk
# deploy` by hand) if you'd rather review a diff before it applies.
deploy:
	cd infra && npm install
	cd infra && npx cdk bootstrap
	cd infra && npx cdk deploy --require-approval never --outputs-file cdk-outputs.json
	python3 infra/scripts/sync_api_url.py
	cd infra && npx cdk deploy --require-approval never

# Tears down all deployed AWS resources (see infra/README.md for what's removed).
destroy:
	cd infra && npx cdk destroy --force

# Runs the backend locally with hot reload. Needs the AWS stack already deployed at least
# once (DynamoDB/OpenSearch must exist) - see backend/README.md.
backend-dev:
	cd backend && . .venv/bin/activate && uvicorn app.main:app --reload --port 8000

# Runs the frontend locally with hot reload, against whatever VITE_API_BASE_URL is set to.
frontend-dev:
	cd frontend && npm run dev

# Infra

AWS CDK (TypeScript) app that deploys the whole thing:

- **Backend**: a plain Lambda function (Python 3.12, zip deployment - no Docker/container
  image needed) behind an API Gateway HTTP API.
- **Frontend**: a static Vite/React build on S3, served through CloudFront (HTTPS, global CDN,
  no server to run).
- **Menu data**: a single DynamoDB table holding both menus - `data/starter_menu.json` (the
  messy brief menu) and `data/clean_menu.json` (a complete, unambiguous 50-dish menu) - each row
  tagged with a `dataset` attribute (`"messy"` | `"clean"`) so the backend can scope a query to
  one or the other. Seeded at deploy time via `AwsCustomResource`, split across several
  (`SeedDishesTable0`, `SeedDishesTable1`, ...) because `batchWriteItem` caps at 25 items per
  call and the combined menus exceed that.
- **Kitchen notes data**: an OpenSearch Serverless collection (vector/k-NN search), with its
  index defined in CDK (`AWS::OpenSearchServerless::CollectionIndex`) but its documents seeded
  lazily by the Lambda on first real query (embedding them needs a live Bedrock call).

## Prerequisites

- AWS credentials configured (`aws configure` or `aws sso login`) for an IAM user/role with
  sufficient permissions (CloudFormation, Lambda, IAM role creation, S3, CloudFront, DynamoDB,
  OpenSearch Serverless).
- Bedrock model access enabled for `amazon.titan-embed-text-v2:0` in the target region (used
  for the RAG layer's embeddings) - check the Bedrock console's "Model access" page. Titan
  models are first-party AWS models and are typically enabled by default, unlike some
  third-party models.
- `ANTHROPIC_API_KEY` set in the repo-root `.env` (read at synth time and set as a plaintext
  Lambda environment variable - fine for a prototype demo; a production version should pull
  this from AWS Secrets Manager instead).
- The backend's local venv set up at least once (`cd ../backend && python3.11 -m venv .venv
  && source .venv/bin/activate && pip install -r requirements.txt`) - deploy uses that venv's
  `pip` to download the Lambda's dependencies, since it's a known-good, modern pip (this
  machine's ambient `pip3` on PATH turned out to be a broken old system Python 3.9 install).
- Node.js available on PATH (deploy runs `npm install && npm run build` in `frontend/` as
  part of bundling the site).
- `DEPLOYER_IAM_PRINCIPAL_ARN` set in the repo-root `.env` to your own IAM user/role ARN (find
  it with `aws sts get-caller-identity`) - the OpenSearch data access policy grants this
  principal direct data-plane access to the collection, so local dev (`uvicorn`) can query/seed
  it too. Optional: falls back to the account root principal if left unset.

## One-time setup

```bash
npm install
npx cdk bootstrap   # once per AWS account/region
```

## Deploy

The easiest path is `make deploy` from the repo root (see the root README) - it wraps the
manual steps below into one command, including the two-pass `cdk deploy` and copying the
`ApiUrl` into `.env` automatically via `infra/scripts/sync_api_url.py`. That script reads the
`ApiUrl` from `cdk deploy --outputs-file cdk-outputs.json`'s output and rewrites (or appends)
the `VITE_API_BASE_URL` line in the repo-root `.env`. Note that `make deploy` passes
`--require-approval never` to both `cdk deploy` calls so the whole thing can run
start-to-finish without an interactive prompt - that skips CDK's normal pause-for-review on
IAM/security-group changes, which is fine for this project's own single-account use but worth
knowing if you'd rather review a diff first (use the manual steps below instead in that case).

Doing it by hand, one step at a time:

```bash
npx cdk deploy
```

Prints an `ApiUrl` (backend), `SiteUrl` (frontend), `DishesTableName` (DynamoDB), and
`OpenSearchEndpoint`. The frontend build bakes in whatever `VITE_API_BASE_URL` is set to in the
repo-root `.env` at the moment `cdk deploy` runs - on a first-ever deploy that's usually still
blank, so copy the printed `ApiUrl` into `.env` and run `cdk deploy` a second time to rebuild
the site against the real backend URL. On every deploy after that, both stay in sync
automatically as long as `.env` has the right value.

**On a genuinely fresh deploy** (an AWS account/region that's never had this stack before), the
first deploy has, in practice, succeeded cleanly (tested via a full `cdk destroy` + `cdk deploy`
cycle) — a full stack deploy takes long enough end-to-end that by the time CloudFormation
reaches `NotesIndex`, the access policy it depends on has usually had time to propagate. It's
still possible in principle to see it fail with `AccessDenied: Access denied to get index` if
the timing is unlucky; if that happens, just wait about a minute and run `npx cdk deploy` again -
CloudFormation resumes from where it left off. Don't work around this by making the index
resource conditional on an env var flag - that was tried and is worse: forgetting to pass the
flag on a later deploy makes CDK see the resource as removed and **delete the index** (and all
its documents) even though nothing else changed.

## Tear down

```bash
npx cdk destroy
```

Removes the Lambda, the API Gateway, the S3 bucket, the CloudFront distribution, the DynamoDB
table, and the OpenSearch collection/index/policies. The CDK bootstrap stack (a separate S3
bucket used for asset staging) is left behind — safe to leave, or remove separately if you want
a fully clean account.

**Do this promptly after you're done testing/demoing** — unlike everything else here,
OpenSearch Serverless has a real minimum cost floor from the moment the collection is created,
regardless of usage. It's cheap for a few hours (well under the "couple of pounds" this project
budgeted for), but isn't meant to be left running indefinitely the way the rest of this stack
safely can be.

## Useful commands

- `npx cdk diff` — compare deployed stack with current code
- `npx cdk synth` — emit the CloudFormation template without deploying

## Why API Gateway, not a Lambda Function URL

This project actually used a Function URL for a while, not API Gateway. API Gateway (both REST
and HTTP APIs) hard-caps request/integration time at ~30 seconds with no way to raise it, and
during an earlier phase - when embeddings ran on a local `sentence-transformers` model instead
of Bedrock - cold starts genuinely blew past that on the first request. A Function URL respects
the Lambda's own (longer) configured timeout instead, which is what got that unblocked.

Once embeddings moved to Bedrock and the heavy local model was dropped, cold starts became fast
enough (a few seconds) that the 30s cap was no longer a real constraint - so the stack moved
back to API Gateway. It's worth the switch back: a Function URL only supports `AWS_IAM` or
`NONE` auth (this stack uses `NONE`, i.e. fully public, no rate limiting beyond Lambda's own
concurrency limit, and AWS WAF cannot attach to a Function URL directly). API Gateway restores
request throttling/usage plans, request validation before invocation, and the option to add
WAF, an API key, or a Cognito/IAM authorizer later if this ever became more than a prototype.

## How the frontend build gets deployed

CDK's asset bundling normally builds inside Docker for reproducibility, but since this project
already moved away from Docker for the backend, the frontend uses the same `local.tryBundle`
approach: it runs `npm install && npm run build` directly on whatever machine runs `cdk deploy`,
then uploads the resulting `frontend/dist` to S3 and invalidates the CloudFront cache. No Docker
involved anywhere in this project.

The asset hash is forced to a fresh value (`Date.now()`) on every synth, rather than left at
CDK's default of hashing `frontend/`'s source files. Reason: `VITE_API_BASE_URL` is baked into
the build from an env var, not from any file under `frontend/`, so CDK's default hashing doesn't
see a `.env`-only change as a reason to rebuild - it would silently redeploy a stale bundle with
the old backend URL still baked in. Confirmed with a real test: changing only `.env` and
redeploying reused the previous build (same output filename, old URL) until this fix was added.

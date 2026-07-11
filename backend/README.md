# Backend

FastAPI service implementing the three-step routing pipeline described in the root README:
intent classification → structured (DynamoDB/PartiQL) / semantic (OpenSearch/k-NN) retrieval →
structured output generation.

Generation calls the Anthropic API directly. Menu data lives in **DynamoDB**, queried via
PartiQL (the LLM writes the query itself, same idea as SQL). Kitchen policy notes live in
**OpenSearch Serverless**, searched via real vector/k-NN search - embeddings come from AWS
Bedrock's Titan model. None of this is read from local files at request time; `data/` only
seeds these stores (DynamoDB at deploy time via CDK, OpenSearch lazily on first real query).

This means local dev needs the CDK stack already deployed once (see `../infra/README.md`) -
it's no longer self-contained. Credentials needed: `ANTHROPIC_API_KEY` and AWS credentials
configured locally (`aws configure` or `aws sso login`).

## Setup

```bash
cd backend
python3.11 -m venv .venv   # needs 3.10+; macOS's bundled python3 may be older
source .venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` at the repo root to `.env` and set `ANTHROPIC_API_KEY` (get one at
console.anthropic.com). Set `DYNAMODB_TABLE_NAME`, `OPENSEARCH_ENDPOINT`, and `OPENSEARCH_INDEX`
to match the CDK stack's outputs. Make sure AWS credentials are configured too, with Bedrock
model access enabled for `amazon.titan-embed-text-v2:0` (see `../infra/README.md`).

## Run locally

```bash
uvicorn app.main:app --reload --port 8000
```

## Endpoints

- `GET /api/health`
- `POST /api/query` — body:
  `{"query": "...", "allergy_or_diet": "peanuts", "dataset": "messy"}`
  `dataset` is optional (`"messy"` | `"clean"`, defaults to `"messy"`) and picks which of the
  two seeded menus the query is scoped to - see the root README for what each one demonstrates.

## Lambda

`app/lambda_handler.py` wraps the FastAPI app with Mangum for deployment (see `../infra/`).
Set `DATA_DIR=/var/task/data` in the Lambda environment, since the deployed package's layout
is flatter than local dev's (`app/` and `data/` land as siblings under `/var/task` instead of
nested under `backend/`).

## Notable implementation details

- **`app/db.py`** queries DynamoDB via `execute_statement` (PartiQL). PartiQL for DynamoDB has
  no `LIKE` or `LOWER()`, so name matching uses `contains("name_lower", ...)` against a
  lowercased shadow field seeded alongside the display-cased `name` - see the comment in
  `infra/lib/infra-stack.ts` where it's seeded.
- **`app/opensearch_client.py`** signs requests to OpenSearch Serverless's data-plane API
  directly with `botocore` (no `opensearch-py`/`requests` dependency needed). Two non-obvious
  requirements it handles: OpenSearch Serverless rejects body-bearing requests with a generic
  403 unless `X-Amz-Content-SHA256` is explicitly computed and signed (botocore's generic
  `SigV4Auth` doesn't add this automatically the way S3-specific auth does), and vector-search
  collections reject client-specified document IDs, so documents are indexed with
  auto-generated IDs and looked up by their own `id` field instead.
- **`app/notes_index.py`** seeds the 6 kitchen notes into OpenSearch lazily, on first real
  query, since embedding them needs a live Bedrock call. It checks document *count*, not index
  existence, to decide whether seeding is needed - the index itself already exists empty from
  the CDK deploy, so existence alone doesn't mean "already seeded". After seeding, it waits
  ~1.5s before the first search: OpenSearch Serverless has **no manual `_refresh` API** (unlike
  classic OpenSearch/Elasticsearch - it manages refresh internally), so newly-indexed documents
  aren't immediately searchable, and a query run in the same request as the seed would otherwise
  see 0 hits. This only ever runs once per deployment, on the very first real semantic query.

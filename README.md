# Can I Eat This?

It's 12:40 in a busy dining hall. You're third in the queue, you have a nut allergy, the menu
board just says "may contain traces??", and you've got about thirty seconds to decide if lunch
is safe.

**Can I Eat This?** is a small AI assistant for exactly that moment. Ask it a question in plain
English — "Can I eat the flapjack?", "Show me what contains nuts", "Recommend something under
£5 with no wheat" — and it looks up the real menu data, reasons about it conservatively (if the
notes are ambiguous, it says "ask staff" rather than guessing), and answers with a clear verdict,
an allergen breakdown, a ranked recommendation list, or a plain answer, whichever fits the
question.

Built for the Compass Group UK & Ireland Graduate AI Engineer pre-task brief.

## How it works

Every question goes through three steps:

1. **What kind of question is this?** An LLM call tags it as a safety check, an allergen
   comparison, a recommendation request, and/or a general question.
2. **Where's the answer?** Specific dish facts (name, price, allergen notes) are fetched by
   having the LLM write a query itself (PartiQL) against a **DynamoDB** table. Fuzzier questions
   (like "what does 'may contain traces' mean?") are answered using real vector/k-NN search (via
   Bedrock embeddings) over a set of kitchen policy notes stored in **OpenSearch Serverless** —
   both real managed cloud data stores, not local files, so this scales the same way past 10
   dishes or 6 notes.
3. **Answer it.** A final LLM call combines what was retrieved with the original question and
   returns a structured answer, which the UI renders as a safety verdict, an allergen matrix
   table, a recommendation list, or plain text.

There are two menus to try it against, switchable live in the UI (no redeploy needed):

- **Messy** — the deliberately imperfect starter menu from the brief ("peanuts??", "see chef",
  "ask counter" and all). The whole point is handling real, ambiguous data rather than a clean
  demo dataset: the assistant should say "ask staff" rather than guess when the notes don't give
  it enough to go on.
- **Clean** — a separate 50-dish menu with complete, unambiguous allergen data for every dish,
  showing the same assistant giving confident, specific answers once the underlying data is
  actually good.

Both menus live in one DynamoDB table (tagged with a `dataset` attribute) — the toggle just
scopes a query to one or the other.

## Try it

Not currently deployed (destroyed after the last demo/test to avoid ongoing cost — see
"Deploy to AWS yourself" below to bring it back up).

## Setup

The backend isn't self-contained with local files — it queries a real DynamoDB table and a
real OpenSearch Serverless collection, so there's no way to run any part of this (even locally)
without deploying the AWS stack at least once first. Before deploying:

1. Copy `.env.example` to `.env`: `cp .env.example .env`
2. Set `ANTHROPIC_API_KEY` in `.env` (get one at [console.anthropic.com](https://console.anthropic.com))
3. Configure AWS credentials (`aws configure` or `aws sso login`) for an account with
   permissions to create the resources listed below
4. Check Bedrock model access for `amazon.titan-embed-text-v2:0` (used for the RAG layer's
   embeddings) - many accounts already have first-party Titan models enabled by default, so
   check before assuming you need to request it:

   ```bash
   aws bedrock-runtime invoke-model --region eu-west-1 \
     --model-id amazon.titan-embed-text-v2:0 --body '{"inputText":"test"}' \
     --cli-binary-format raw-in-base64-out /tmp/bedrock-test.json && cat /tmp/bedrock-test.json
   ```

   If that prints an embedding vector, you're already set. If it fails with
   `AccessDeniedException`, request access once in the AWS Console: go to **Amazon Bedrock**,
   confirm the region selector (top right) matches `AWS_REGION` in `.env`, open **Model access**
   in the left sidebar, click **Modify model access** (or **Enable specific models**), tick
   **Titan Text Embeddings V2**, and submit - usually granted within a minute or two for a
   first-party model like this.

Everything else in `.env` already has a sensible default for a first deploy.

## Deploy to AWS yourself

Everything deploys and tears down with one command each via AWS CDK — the backend as a Lambda
function behind an API Gateway HTTP API, the frontend as a static build on S3 served through
CloudFront, the menu data in DynamoDB, and the kitchen notes in OpenSearch Serverless (real
vector/k-NN search). No servers to manage.

```bash
make deploy
```

This runs the whole thing end-to-end: installs infra dependencies, bootstraps CDK if needed,
deploys the stack, copies the freshly-printed `ApiUrl` into `.env`, then deploys a second time
so the frontend build picks it up — no manual copy-pasting. Prints a `SiteUrl` at the end;
open that in a browser, nothing else needed.

```bash
make destroy
```

Tears everything down, so nothing keeps costing money afterward. One exception: **OpenSearch
Serverless has a real minimum cost floor even sitting completely idle**, unlike everything else
in this stack (Lambda/DynamoDB/S3/CloudFront are all genuinely free when unused) — don't leave
a deployed stack running for extended periods for this reason.

See [infra/README.md](infra/README.md) for what `make deploy` does under the hood, first-deploy
quirks worth knowing about, and how to run the individual `cdk deploy`/`cdk destroy` steps by
hand instead if you'd rather review each one. Once the stack is deployed, [backend/README.md](backend/README.md)
and [frontend/README.md](frontend/README.md) cover running either half locally with hot reload
against the deployed data stores, if you want to iterate on the code rather than just use the
deployed site.

## Project structure

- `frontend/` — the React UI (the form you type questions into, and the results view)
- `backend/` — the API and the three-step LLM pipeline described above
- `data/` — the messy starter menu (`starter_menu.json`), the clean 50-dish menu
  (`clean_menu.json`), and the kitchen policy notes (`kitchen_notes.json`), used only to *seed*
  DynamoDB (at deploy time) and OpenSearch (lazily, on first real query) - not read directly at
  request time
- `infra/` — the AWS CDK app for deploying the backend, frontend, and data stores
- `docs/` — the pitch deck (`CanIEatThis_Pitch.pdf` / `.pptx`, with speaker notes) - **note:**
  slides 6, 8, and 9 still describe the previous local-SQLite/in-memory-comparison
  architecture, not this one; worth a revisit before presenting
- `Makefile` — one-command deploy/destroy (`make deploy` / `make destroy`); see "Deploy to AWS
  yourself" above
- `CODING_STANDARDS.md` — the Google-style Python/TypeScript conventions this codebase follows

## Notes

- Only synthetic data is used — the starter menu from the brief, no real people or real
  allergy/health data anywhere.
- Every step in the pipeline has a safe fallback: if a generated SQL query is invalid, if the
  LLM call fails, or if the data is missing, the answer degrades to "ask a member of staff"
  rather than crashing or guessing.

# Can I Eat This?

An AI-powered dining safety assistant. Given a dish question and an allergy/dietary need, it returns a clear safety verdict (Safe / Caution / Not safe / Unknown — ask staff) and an allergen breakdown, grounded in menu data rather than hallucinated.

Built for the Compass Group UK & Ireland Graduate AI Engineer pre-task brief ("Can I eat this?").

## Architecture

1. **Intent classification** — LLM tags the query as one or more of: safety check, allergen comparison, recommendation, general question.
2. **Retrieval routing** — structured/factual retrieval (SQL over a dish/allergen database) and/or semantic retrieval (RAG over messy free-text notes like "see chef", "ask counter", "peanuts??").
3. **Output formatting** — traffic-light safety verdict, allergen matrix, ranked recommendations, or plain-text answer.

## Structure

- `frontend/` — React + Vite + TypeScript UI
- `backend/` — API + LLM orchestration
- `data/` — starter menu and seed data
- `docs/` — pitch materials, notes
- `infra/` — AWS deployment config

## Local development

See `frontend/README.md` and `backend/README.md` (once added) for setup instructions. Copy `.env.example` to `.env` and fill in values.

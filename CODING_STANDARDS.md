# Coding Standards

This project follows the Google style guides for its two languages — the
[Google Python Style Guide](https://google.github.io/styleguide/pyguide.html) for `backend/`,
and the [Google TypeScript Style Guide](https://google.github.io/styleguide/tsguide.html) for
`frontend/` and `infra/` — adapted to this codebase's scale. It's a small, single-purpose
prototype, not a multi-team production service, so the rules below are the subset that actually
pays for itself here: consistent naming, a docstring/JSDoc contract on every public function, and
comments that explain *why*, never *what*.

## General principles

- **Comments explain why, not what.** Well-named functions and variables already say what the
  code does. A comment earns its place only when it captures something the code can't: a hidden
  constraint, a workaround for a specific external quirk, or a non-obvious tradeoff. If deleting
  a comment wouldn't confuse the next reader, delete it.
- **Every public function, class, and module has a docstring/JSDoc block** describing its
  contract (what it does, its parameters, its return value, and any exceptions/errors it can
  surface) — this is documentation of the interface, distinct from inline comments, and is not
  optional even when the implementation is short.
- **Type everything at the boundary.** Every function signature has full type hints (Python) or
  explicit types (TypeScript) on its parameters and return value. Internal local variables can
  rely on inference.
- **Small, single-purpose functions.** A function does one thing; if a docstring needs "and" to
  describe what it does, it should probably be two functions.
- **No bare `except:` / untyped `catch`.** Catch `Exception` (Python) when a step's failure
  needs to degrade to a safe fallback (this project's core safety pattern — see `backend/app/
  engine.py`), but always log it first via the module logger so failures are diagnosable, never
  silent.
- **Consistent formatting over personal preference.** Formatting is mechanical, not a matter of
  taste — see "Tooling" below for the formatters this project is written to be compatible with.

## Python (`backend/`)

- **Naming**: `snake_case` for functions/variables/modules, `PascalCase` for classes,
  `UPPER_SNAKE_CASE` for module-level constants (see `backend/app/config.py`).
- **Imports**: standard library, then third-party, then local (`from . import ...`), each group
  separated by a blank line, alphabetized within a group.
- **Docstrings**: Google-style, triple-quoted, with `Args:`, `Returns:`, and `Raises:` sections
  whenever the function takes parameters, returns a value, or can raise on purpose. One-line
  docstrings are fine for trivial functions with no parameters and an obvious return.

  ```python
  def retrieve_structured(
      query: str, allergy_or_diet: str | None, dataset: str
  ) -> tuple[list[dict], str | None]:
      """Fetches dish rows via an LLM-generated PartiQL query, scoped to one dataset.

      Args:
          query: The user's natural-language question.
          allergy_or_diet: The user's declared allergy/diet, if any.
          dataset: Which seeded menu to scope the query to ("messy" or "clean").

      Returns:
          A tuple of (matched dish rows, the sanitized PartiQL statement used), or
          (all rows in the dataset, None) if query generation or execution failed.
      """
  ```

- **Type hints**: required on every function signature (parameters and return type), using
  modern syntax (`str | None`, not `Optional[str]`, per this project's Python 3.12 baseline).
- **f-strings** for all string interpolation; no `%`-formatting or `.format()`.
- **Exceptions**: catch the narrowest exception type the call site can actually raise, except at
  a designed fallback boundary (external API calls, LLM output parsing) where catching
  `Exception` broadly and logging via `logger.exception(...)` is the intentional, documented
  pattern — not a shortcut to silence errors.

## TypeScript / React (`frontend/`, `infra/`)

- **Naming**: `camelCase` for variables/functions, `PascalCase` for components/types/interfaces,
  `UPPER_SNAKE_CASE` for module-level constants.
- **Explicit types over `any`.** Every exported function and component has an explicit parameter
  and return type; component props are defined as a named `interface` or `type`, never inferred
  from usage.
- **JSDoc on every exported function/component** describing its contract, using `@param` and
  `@returns` where relevant — the TypeScript equivalent of the Python docstring rule above.

  ```typescript
  /**
   * Sends a query to the backend and returns the structured response.
   *
   * @param query - The user's natural-language question.
   * @param allergyOrDiet - The user's declared allergy/diet, if any.
   * @param dataset - Which seeded menu to scope the query to.
   * @returns The parsed QueryResponse from the backend.
   */
  export async function runQuery(
    query: string,
    allergyOrDiet: string | null,
    dataset: Dataset,
  ): Promise<QueryResponse> { ... }
  ```

- **Named exports** for utilities, types, and non-default components (`api.ts`,
  `components/*.tsx`); a default export is reserved for the app's root component (`App.tsx`),
  matching common React/Vite convention.
- **Function components with typed props**, not `React.FC` (per current React/TypeScript
  guidance — `React.FC` implicitly adds `children` even when a component doesn't accept any).

## Infra (`infra/`, CDK)

Same TypeScript rules as above, plus:

- Every non-obvious CDK resource choice (why this construct, why this prop value) gets a comment
  at the point of decision — see `infra/lib/infra-stack.ts` for the existing standard (e.g. the
  `assetHash: Date.now()` comment, the OpenSearch access-policy propagation note). Don't restate
  what a construct does if its name and AWS docs already make that obvious.

## Tooling

No formatter/linter is currently pinned in `backend/requirements.txt`. If this project grows
past prototype stage, wire in `ruff` (lint + format, replaces `black`+`flake8`+`isort` in one
tool) for `backend/`, and rely on the ESLint config already in `frontend/eslint.config.js` for
the frontend. Until then, match the style already in the codebase by hand.

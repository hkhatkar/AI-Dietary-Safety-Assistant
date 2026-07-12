"""The three-step query pipeline: classify -> retrieve -> generate.

Every step has a safe fallback - a failed LLM call or malformed output degrades to a
conservative default rather than raising past `run()`, so a single flaky step never turns into
an unhandled 500 (see `run()`'s two nested try/except blocks for where that guarantee is
enforced end-to-end).
"""

import logging

from . import db, llm, notes_index
from .config import DYNAMODB_TABLE_NAME
from .schemas import QueryResponse
from .sql_guard import sanitize_select

logger = logging.getLogger("engine")

INTENT_SYSTEM = """You are a query router for a dining-hall allergen safety assistant.
Classify the user's query. Respond with ONLY a JSON object, no prose:
{
  "intents": array of any of ["safety_check", "allergen_comparison", "recommendation", "general_question"],
  "retrieval": array of any of ["structured", "semantic"]
}
Rules:
- "safety_check" = asking if they personally can eat a specific dish given an allergy/diet.
- "allergen_comparison" = asking to see allergen info across one or more dishes without a personal safety question.
- "recommendation" = asking what they should eat / for suggestions.
- "general_question" = asking what a menu term/policy means, or anything not about a specific dish's allergens.
- "structured" retrieval is needed whenever specific dishes, prices, or kcal must be looked up.
- "semantic" retrieval is needed whenever the answer may depend on kitchen policy, ambiguous notes
  (e.g. "see chef", "ask counter", "may contain"), or a general explanation.
- Most safety_check and allergen_comparison queries need BOTH structured and semantic retrieval.
"""

SQL_SYSTEM = f"""You write a single read-only PartiQL SELECT statement (Amazon DynamoDB dialect)
for this schema:
{db.SCHEMA_DESCRIPTION}
Respond with ONLY the PartiQL statement, no explanation, no markdown fences.
Always match against "name_lower" with an all-lowercase substring, never "name" - PartiQL for
DynamoDB has no LIKE or LOWER() function, so case-insensitive matching only works this way.
Always select all columns with "SELECT *" - never select a subset of columns, even if the
query only seems to need a few of them. Quote the table name, e.g.
SELECT * FROM "{DYNAMODB_TABLE_NAME}" WHERE contains("name_lower", 'flapjack').
If the user's query does not clearly name specific dishes (e.g. they want a comparison or
recommendation across the whole menu), select all rows with no WHERE clause.
"""

OUTPUT_SYSTEM = """You are a dining-hall allergen safety assistant. Be conservative: if the
allergen notes for a dish are ambiguous, informal, or say things like "see chef", "ask counter",
"may contain", or are missing, you must NOT assume the dish is safe. Use "Unknown - ask staff"
rather than guessing whenever there is real ambiguity.

You are given: the user's query, their declared allergy/dietary need (if any), rows retrieved
from the dish database (name, allergen_notes_raw, kcal_raw, price_gbp), any relevant kitchen
policy notes, and a list of required fields you must populate (decided ahead of time from the
query's classified intent - not your choice to make). Respond with ONLY a JSON object, no
prose, matching this contract:

{
  "safety": null OR {
    "overall_verdict": one of "Safe" | "Caution" | "Not safe" | "Unknown - ask staff",
    "dishes": [
      {
        "name": string,
        "verdict": one of "Safe" | "Caution" | "Not safe" | "Unknown - ask staff",
        "allergens": { "<allergen name>": one of "contains" | "may_contain" | "not_listed" | "unknown", ... },
        "reasoning": short string explaining the verdict, citing the raw note text or policy note used
      }, ...
    ]
  },
  "recommendations": null OR [ { "name": string, "reason": string }, ... ],
  "answer": null OR a single plain-language string (never an object or array)
}

Populate every field listed as required, even if the result set is large (keep each dish's
"reasoning" brief rather than dropping dishes or leaving the field null). Leave any field not
listed as required set to null, unless "answer" is useful as a short summary alongside the
required fields regardless.
"""

# Deterministic mapping from a classified intent to the output type shown in the response.
# The final generation call used to decide this for itself (from the query text alone,
# independent of what classify() had already decided), which meant the same intents could
# produce different populated fields depending on how large the retrieved result set was -
# this fixes that by deciding output_types in code, from the intent, and telling the model
# which fields it's required to fill in rather than leaving it to guess.
INTENT_TO_OUTPUT_TYPE = {
    "safety_check": "safety_check",
    "allergen_comparison": "allergen_matrix",
    "recommendation": "recommendation",
    "general_question": "general_answer",
}

# Which JSON field each output type actually populates (safety_check and allergen_matrix both
# populate "safety" - they differ only in why the query was classified that way).
OUTPUT_TYPE_TO_FIELD = {
    "safety_check": "safety",
    "allergen_matrix": "safety",
    "recommendation": "recommendations",
    "general_answer": "answer",
}


def output_types_for(intents: list[str]) -> list[str]:
    """Deterministically derives which output types a response must populate.

    Args:
        intents: The classified intents from `classify()`.

    Returns:
        The output types to populate, in the order their intents first appeared, deduplicated.
        Falls back to `["general_answer"]` if no intent maps to a known output type.
    """
    output_types = []
    for intent in intents:
        output_type = INTENT_TO_OUTPUT_TYPE.get(intent)
        if output_type and output_type not in output_types:
            output_types.append(output_type)
    return output_types or ["general_answer"]


def classify(query: str, allergy_or_diet: str | None) -> dict:
    """Classifies a query's intent(s) and which retrieval step(s) it needs.

    Args:
        query: The user's natural-language question.
        allergy_or_diet: The user's declared allergy/diet, if any.

    Returns:
        A dict with "intents" (list[str]) and "retrieval" (list[str]). Defaults to
        `{"intents": ["safety_check"], "retrieval": ["structured", "semantic"]}` - the most
        conservative classification - if the LLM call fails or omits either key.
    """
    user = f"Query: {query}\nDeclared allergy/diet: {allergy_or_diet or 'none stated'}"
    try:
        result = llm.chat_json(INTENT_SYSTEM, user, max_tokens=256)
    except Exception:
        logger.exception("Intent classification failed, defaulting to safety_check")
        return {"intents": ["safety_check"], "retrieval": ["structured", "semantic"]}
    result.setdefault("intents", ["safety_check"])
    result.setdefault("retrieval", ["structured", "semantic"])
    return result


def retrieve_structured(
    query: str, allergy_or_diet: str | None, dataset: str
) -> tuple[list[dict], str | None]:
    """Fetches dish rows via an LLM-generated PartiQL query, scoped to one dataset.

    Args:
        query: The user's natural-language question.
        allergy_or_diet: The user's declared allergy/diet, if any.
        dataset: Which seeded menu to scope the query to ("messy" or "clean").

    Returns:
        A tuple of (matched dish rows, the sanitized PartiQL statement used). Falls back to
        (every row in the dataset, None) if the LLM's generated SQL fails validation or
        execution.
    """
    user = f"Query: {query}\nDeclared allergy/diet: {allergy_or_diet or 'none stated'}"
    try:
        raw_sql = llm.chat(SQL_SYSTEM, user, max_tokens=200)
        sql = sanitize_select(raw_sql)
        rows = db.run_read_only_query(sql, dataset)
        return rows, sql
    except Exception:
        logger.exception("Text-to-SQL failed, falling back to full table scan")
        return db.get_all_dishes(dataset), None


def retrieve_semantic(query: str) -> list[dict]:
    """Fetches the kitchen policy notes most relevant to a query, via vector search.

    Args:
        query: The user's natural-language question.

    Returns:
        Up to 3 matching notes, or an empty list if semantic search fails.
    """
    try:
        return notes_index.search(query, k=3)
    except Exception:
        logger.exception("Semantic note retrieval failed")
        return []


def generate_output(
    query: str,
    allergy_or_diet: str | None,
    dishes: list[dict],
    notes: list[dict],
    required_fields: list[str],
) -> dict:
    """Generates the final structured answer from the query and retrieved context.

    Args:
        query: The user's natural-language question.
        allergy_or_diet: The user's declared allergy/diet, if any.
        dishes: Retrieved dish rows (from `retrieve_structured`), if any.
        notes: Retrieved kitchen policy notes (from `retrieve_semantic`), if any.
        required_fields: Which of "safety"/"recommendations"/"answer" this response must
            populate, deterministically derived from the classified intents (see
            `output_types_for`) - not left to the model to decide.

    Returns:
        The parsed JSON object matching the `OUTPUT_SYSTEM` contract (whichever of
        `safety`/`recommendations`/`answer` were required, populated).

    Raises:
        ValueError: If the model's response contained no JSON object.
        json.JSONDecodeError: If the JSON was malformed or truncated (e.g. the response
            exceeded `max_tokens`). Callers are expected to catch this and fall back.
    """
    user = (
        f"User query: {query}\n"
        f"Declared allergy/diet: {allergy_or_diet or 'none stated'}\n"
        f"Dish rows: {dishes}\n"
        f"Kitchen policy notes: {[{'title': n['title'], 'text': n['text']} for n in notes]}\n"
        f"Required fields (populate every one of these, never leave them null): {required_fields}\n"
    )
    return llm.chat_json(OUTPUT_SYSTEM, user, max_tokens=4096)


def run(query: str, allergy_or_diet: str | None, dataset: str = "messy") -> QueryResponse:
    """Runs the full classify -> retrieve -> generate pipeline for one query.

    Args:
        query: The user's natural-language question.
        allergy_or_diet: The user's declared allergy/diet, if any.
        dataset: Which seeded menu to scope structured retrieval to ("messy" or "clean").

    Returns:
        The structured pipeline result. Always a valid QueryResponse, even if generation or
        response construction failed along the way - see the module docstring.
    """
    classification = classify(query, allergy_or_diet)
    intents = classification["intents"]
    retrieval = classification["retrieval"]
    output_types = output_types_for(intents)
    required_fields = sorted({OUTPUT_TYPE_TO_FIELD[ot] for ot in output_types})

    dishes: list[dict] = []
    generated_sql: str | None = None
    if "structured" in retrieval:
        dishes, generated_sql = retrieve_structured(query, allergy_or_diet, dataset)

    notes: list[dict] = []
    if "semantic" in retrieval:
        notes = retrieve_semantic(query)

    fallback_output = {
        "answer": (
            "Something went wrong working out a safety answer. "
            "Please ask a member of staff to confirm before eating this."
        ),
    }

    try:
        output = generate_output(query, allergy_or_diet, dishes, notes, required_fields)
    except Exception:
        logger.exception("Output generation failed")
        output = fallback_output
        output_types = ["general_answer"]

    # generate_output() is *told* which fields are required, but nothing stops the model
    # from also populating one it wasn't asked for (observed in practice: a recommendation-only
    # query still coming back with a populated "safety" block). Since the frontend renders
    # whichever fields are non-null - not output_types - anything not stripped here would still
    # display, silently breaking the "intent determines what's displayed" guarantee. "answer" is
    # deliberately exempt: the prompt allows it as an optional summary alongside required fields.
    try:
        return QueryResponse(
            dataset=dataset,
            intents=intents,
            retrieval_used=retrieval,
            generated_sql=generated_sql,
            retrieved_notes=notes,
            output_types=output_types,
            safety=output.get("safety") if "safety" in required_fields else None,
            recommendations=output.get("recommendations") if "recommendations" in required_fields else None,
            answer=output.get("answer"),
        )
    except Exception:
        # The model is asked for a plain string "answer" but can still return a
        # malformed shape (e.g. a nested object). Every other step in this pipeline
        # degrades to a safe fallback on failure - this construction must too, rather
        # than propagating as an unhandled 500 with no response returned at all.
        logger.exception("Response validation failed, falling back to safe message")
        return QueryResponse(
            dataset=dataset,
            intents=intents,
            retrieval_used=retrieval,
            generated_sql=generated_sql,
            retrieved_notes=notes,
            output_types=["general_answer"],
            safety=None,
            recommendations=None,
            answer=fallback_output["answer"],
        )

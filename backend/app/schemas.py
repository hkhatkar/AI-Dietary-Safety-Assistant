"""Pydantic request/response models for the `/api/query` endpoint."""

from typing import Literal, Optional

from pydantic import BaseModel

Verdict = Literal["Safe", "Caution", "Not safe", "Unknown - ask staff"]


class QueryRequest(BaseModel):
    """The incoming request body for POST /api/query."""

    query: str
    allergy_or_diet: Optional[str] = None
    dataset: Literal["messy", "clean"] = "messy"


class DishSafety(BaseModel):
    """The safety assessment for a single dish."""

    name: str
    verdict: Verdict
    allergens: dict[str, str]
    reasoning: str


class SafetyResult(BaseModel):
    """The safety assessment across one or more dishes, with an overall verdict."""

    overall_verdict: Verdict
    dishes: list[DishSafety]


class Recommendation(BaseModel):
    """A single recommended dish and why it was recommended."""

    name: str
    reason: str


class QueryResponse(BaseModel):
    """The response body for POST /api/query, combining pipeline metadata (useful for the
    UI's "under the hood" debug panel) with whichever output fields the query's intent(s)
    populated."""

    dataset: str
    intents: list[str]
    retrieval_used: list[str]
    generated_sql: Optional[str] = None
    retrieved_notes: list[dict] = []
    output_types: list[str]
    safety: Optional[SafetyResult] = None
    recommendations: Optional[list[Recommendation]] = None
    answer: Optional[str] = None

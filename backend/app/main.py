"""FastAPI app: the HTTP surface over the three-step query pipeline in `engine.py`."""

import logging
import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import engine
from .schemas import QueryRequest, QueryResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api")

app = FastAPI(title="Can I Eat This? API")

# When deployed, API Gateway already adds CORS headers at the platform level (see
# infra/lib/infra-stack.ts). Adding CORSMiddleware here too would give every response two
# conflicting Access-Control-Allow-Origin headers, which browsers reject outright - so only
# add it for local dev (plain uvicorn), where nothing else is handling CORS.
if not os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catches any exception FastAPI's routing didn't already handle.

    Registered explicitly so CORS headers still get attached to error responses - letting
    exceptions bubble past FastAPI's handler map skips CORSMiddleware entirely, which the
    browser then reports as an opaque network failure rather than a 500.

    Args:
        request: The incoming request.
        exc: The unhandled exception.

    Returns:
        A generic 500 JSON response (the real error is logged, not exposed to the client).
    """
    logger.exception("Unhandled exception on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/api/health")
def health() -> dict:
    """Liveness check.

    Returns:
        A static status payload.
    """
    return {"status": "ok"}


@app.options("/{full_path:path}")
def preflight(full_path: str) -> dict:
    """Handles CORS preflight requests for every path.

    API Gateway's corsPreflight config attaches the right CORS headers to whatever the Lambda
    returns (confirmed on real POST responses), but with a catch-all $default route it doesn't
    short-circuit OPTIONS requests before they reach the Lambda the way it does for
    explicitly-modeled routes - without this handler, FastAPI 405s on OPTIONS (no route
    registered for that method), which the browser reports as a failed CORS preflight.

    Args:
        full_path: The requested path (unused; this handler matches every path).

    Returns:
        An empty body; API Gateway attaches the actual CORS headers.
    """
    return {}


@app.post("/api/query", response_model=QueryResponse)
def query(request: QueryRequest) -> QueryResponse:
    """Runs the three-step query pipeline for a single question.

    Args:
        request: The query, optional declared allergy/diet, and which dataset to scope to.

    Returns:
        The structured pipeline result.

    Raises:
        HTTPException: 400 if `query` is empty or whitespace-only.
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty")
    return engine.run(request.query, request.allergy_or_diet, request.dataset)

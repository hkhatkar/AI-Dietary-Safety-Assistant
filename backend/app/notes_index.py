"""Semantic (k-NN) search over kitchen policy notes, backed by OpenSearch Serverless."""

import json
import time

from . import opensearch_client
from .config import DATA_DIR, OPENSEARCH_INDEX
from .embeddings import embed

_seeded = False


def _ensure_seeded() -> None:
    """Seeds the kitchen notes index on first use, if it isn't already populated.

    The index itself is created by the CDK stack (`AWS::OpenSearchServerless::CollectionIndex`)
    and exists empty from the start, so its mere existence can't signal "already seeded" - this
    checks the document count instead, and seeds the notes into it lazily, since embedding them
    requires a live Bedrock call rather than static data.
    """
    global _seeded
    if _seeded:
        return
    if opensearch_client.count(OPENSEARCH_INDEX) > 0:
        _seeded = True
        return
    notes = json.loads((DATA_DIR / "kitchen_notes.json").read_text())
    for note in notes:
        vector = embed(f"{note['title']}. {note['text']}")
        opensearch_client.index_document(OPENSEARCH_INDEX, {**note, "embedding": vector})
    # OpenSearch Serverless has no manual _refresh API (unlike classic OpenSearch/Elasticsearch -
    # it manages refresh internally), so newly-indexed documents just take a moment to become
    # searchable. This only ever runs once, on the very first real query after a fresh deploy.
    time.sleep(1.5)
    _seeded = True


def search(query: str, k: int = 3) -> list[dict]:
    """Returns the top-k kitchen notes most semantically similar to the query.

    Args:
        query: The user's natural-language question.
        k: How many notes to return.

    Returns:
        Up to k note documents, each including a similarity `score`.
    """
    _ensure_seeded()
    query_vec = embed(query)
    return opensearch_client.search(OPENSEARCH_INDEX, query_vec, k)

"""Minimal SigV4-signed HTTP client for the OpenSearch Serverless data-plane API.

Talks to OpenSearch Serverless's REST API directly over HTTPS rather than depending on
`opensearch-py`/`requests` - `botocore` (already required by `boto3`) has everything SigV4
signing needs, which keeps the Lambda package smaller.
"""

import hashlib
import json

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.httpsession import URLLib3Session

from .config import AWS_REGION, OPENSEARCH_ENDPOINT

_SERVICE = "aoss"  # OpenSearch Serverless's SigV4 service name (not "es", which is for managed domains)
_http = URLLib3Session()


def _signed_request(method: str, path: str, body: dict | None = None) -> dict:
    """Sends a SigV4-signed request to the OpenSearch Serverless data-plane API.

    Uses botocore's own prepare+send pipeline end-to-end (rather than signing a request built
    by another HTTP library) so the signed bytes are exactly what's transmitted.

    Args:
        method: The HTTP method.
        path: The request path, e.g. "/kitchen-notes/_search".
        body: The JSON request body, if any.

    Returns:
        The parsed JSON response body.

    Raises:
        RuntimeError: If the response status is 400 or above.
    """
    credentials = boto3.Session().get_credentials()
    url = f"{OPENSEARCH_ENDPOINT}{path}"
    data = json.dumps(body).encode() if body is not None else b""
    # OpenSearch Serverless rejects body-bearing requests with a generic 403 unless
    # X-Amz-Content-SHA256 is present and included in SignedHeaders - botocore's generic
    # SigV4Auth doesn't add this automatically (only service-specific auth classes like S3's
    # do), so it has to be computed and set explicitly here before signing.
    headers = {
        "Content-Type": "application/json",
        "X-Amz-Content-SHA256": hashlib.sha256(data).hexdigest(),
    }
    request = AWSRequest(method=method, url=url, data=data, headers=headers)
    SigV4Auth(credentials, _SERVICE, AWS_REGION).add_auth(request)
    response = _http.send(request.prepare())
    if response.status_code >= 400:
        raise RuntimeError(f"OpenSearch request failed: {response.status_code} {response.text}")
    return json.loads(response.content)


def search(index: str, vector: list[float], k: int = 3) -> list[dict]:
    """Runs a k-NN vector search against an index.

    Args:
        index: The index name.
        vector: The query embedding vector.
        k: How many nearest neighbors to return.

    Returns:
        Each hit's stored fields (excluding the raw embedding vector, which there's no reason
        to send over the wire) plus its similarity `score`.
    """
    body = {
        "size": k,
        "query": {"knn": {"embedding": {"vector": vector, "k": k}}},
        "_source": {"excludes": ["embedding"]},
    }
    response = _signed_request("POST", f"/{index}/_search", body)
    hits = response.get("hits", {}).get("hits", [])
    return [{**hit["_source"], "score": hit.get("_score", 0.0)} for hit in hits]


def count(index: str) -> int:
    """Returns the number of documents currently in an index.

    Args:
        index: The index name.

    Returns:
        The document count.
    """
    return _signed_request("GET", f"/{index}/_count").get("count", 0)


def index_document(index: str, document: dict) -> None:
    """Indexes a single document with an auto-generated ID.

    Args:
        index: The index name.
        document: The document body to index. OpenSearch Serverless vector-search collections
            reject client-specified document IDs ("Document ID is not supported in
            create/index operation request"), so the document's own `id` field (already
            present in the data) is what callers look it up by afterward, not the
            auto-generated OpenSearch document ID.
    """
    _signed_request("POST", f"/{index}/_doc", document)

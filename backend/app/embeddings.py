"""Text embedding via AWS Bedrock's Titan model.

A remote API call rather than a locally-run model, which keeps Lambda cold starts fast and
avoids bundling a heavy ML runtime for a corpus this small (a handful of kitchen policy notes).
"""

import json

import boto3

from .config import AWS_REGION, BEDROCK_EMBED_MODEL_ID

_bedrock = boto3.client("bedrock-runtime", region_name=AWS_REGION)


def embed(text: str) -> list[float]:
    """Embeds a string via Bedrock's Titan embedding model.

    Args:
        text: The text to embed.

    Returns:
        The embedding vector as a list of floats.
    """
    body = json.dumps({"inputText": text})
    response = _bedrock.invoke_model(modelId=BEDROCK_EMBED_MODEL_ID, body=body)
    payload = json.loads(response["body"].read())
    return payload["embedding"]

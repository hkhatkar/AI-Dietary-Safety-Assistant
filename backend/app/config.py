"""Environment-derived configuration shared across the backend.

Every setting here is read once at import time from the process environment (populated by
`.env` locally, or by the Lambda's configured environment variables when deployed).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BACKEND_DIR = Path(__file__).resolve().parent.parent
# Overridable because the deployed Lambda's zip package copies app/ and data/ in flat as
# siblings under /var/task, one level shallower than local dev's backend/app + repo-root/data.
DATA_DIR = Path(os.getenv("DATA_DIR", str(BACKEND_DIR.parent / "data")))

AWS_REGION = os.getenv("AWS_REGION", "eu-west-1")  # also used for the Bedrock embeddings call

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
BEDROCK_EMBED_MODEL_ID = os.getenv("BEDROCK_EMBED_MODEL_ID", "amazon.titan-embed-text-v2:0")

BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8000"))

# Structured menu data (DynamoDB, queried via PartiQL) and semantic notes data (OpenSearch
# Serverless, k-NN vector search) - set by the CDK stack's outputs after `cdk deploy`.
DYNAMODB_TABLE_NAME = os.getenv("DYNAMODB_TABLE_NAME", "can-i-eat-this-dishes")
OPENSEARCH_ENDPOINT = os.getenv("OPENSEARCH_ENDPOINT", "")
OPENSEARCH_INDEX = os.getenv("OPENSEARCH_INDEX", "kitchen-notes")

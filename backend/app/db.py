"""DynamoDB access for the dishes table, queried via PartiQL (`execute_statement`).

Both the messy and clean menus live in one table, distinguished by a `dataset` attribute;
filtering by dataset happens here in Python rather than in the generated PartiQL, since the
SQL-generation prompt is never taught about that attribute.
"""

import boto3
from boto3.dynamodb.types import TypeDeserializer

from .config import AWS_REGION, DYNAMODB_TABLE_NAME

_dynamodb = boto3.client("dynamodb", region_name=AWS_REGION)
_deserializer = TypeDeserializer()

SCHEMA_DESCRIPTION = (
    f'Table "{DYNAMODB_TABLE_NAME}" (Amazon DynamoDB, queried via PartiQL) with attributes: '
    "id (Number), name (String, original casing, for display), name_lower (String, lowercased "
    "copy of name - always match against this one), allergen_notes_raw (String), kcal_raw "
    "(String), price_gbp (Number). "
    "allergen_notes_raw is messy free text exactly as printed on the menu board, e.g. "
    "'WHEAT, MILK', 'see chef', 'peanuts??', 'may contain traces of nuts', 'none', 'null'. "
    "kcal_raw is text because some entries are missing or non-numeric (e.g. '700+'). "
    "PartiQL for DynamoDB does not support LIKE or LOWER() - use "
    "contains(\"name_lower\", 'lowercase substring') for name matching, never contains(\"name\", ...)."
)


def _deserialize(item: dict) -> dict:
    """Converts a raw DynamoDB item (AttributeValue-typed) into a plain JSON-friendly dict.

    Args:
        item: A single item as returned by `execute_statement`, with each value still
            wrapped in its DynamoDB AttributeValue type descriptor.

    Returns:
        The item with native Python types, the internal `name_lower` shadow field dropped,
        and `id`/`price_gbp` coerced to their proper numeric types.
    """
    result = {k: _deserializer.deserialize(v) for k, v in item.items()}
    result.pop("name_lower", None)
    if "id" in result:
        result["id"] = int(result["id"])
    if "price_gbp" in result:
        result["price_gbp"] = float(result["price_gbp"])
    return result


def run_read_only_query(statement: str, dataset: str) -> list[dict]:
    """Executes a PartiQL SELECT and returns rows scoped to one menu dataset.

    Args:
        statement: A validated, read-only PartiQL SELECT statement (see `sql_guard.py`).
        dataset: Which seeded menu to scope results to ("messy" or "clean").

    Returns:
        Deserialized rows whose `dataset` attribute matches, with that attribute stripped
        out of each row (it's an internal filtering detail, not part of the dish's data).
    """
    response = _dynamodb.execute_statement(Statement=statement)
    rows = [_deserialize(item) for item in response.get("Items", [])]
    return [{k: v for k, v in row.items() if k != "dataset"} for row in rows if row.get("dataset") == dataset]


def get_all_dishes(dataset: str) -> list[dict]:
    """Returns every dish row in the given dataset (used as the fallback when SQL generation
    or execution fails, and when a query doesn't clearly name specific dishes).

    Args:
        dataset: Which seeded menu to return ("messy" or "clean").

    Returns:
        All dish rows belonging to that dataset.
    """
    return run_read_only_query(f'SELECT * FROM "{DYNAMODB_TABLE_NAME}"', dataset)

"""Thin wrapper around the Anthropic Messages API used by every LLM call in the pipeline."""

import json
import re

import anthropic

from .config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def chat(system: str, user: str, max_tokens: int = 1024) -> str:
    """Runs a one-shot text completion via the Anthropic Messages API.

    Args:
        system: The system prompt.
        user: The user message.
        max_tokens: Maximum tokens to generate.

    Returns:
        The model's text response.
    """
    response = _client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=max_tokens,
        temperature=0.1,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return response.content[0].text


def chat_json(system: str, user: str, max_tokens: int = 1024) -> dict:
    """Runs a chat completion that expects a JSON object back, tolerating minor formatting
    slop (e.g. stray prose or markdown fences around the JSON block).

    Args:
        system: The system prompt.
        user: The user message.
        max_tokens: Maximum tokens to generate.

    Returns:
        The parsed JSON object.

    Raises:
        ValueError: If no JSON object could be found in the model's output.
        json.JSONDecodeError: If a JSON-looking block was found but failed to parse (e.g.
            truncated because the response exceeded max_tokens).
    """
    raw = chat(system, user, max_tokens=max_tokens)
    match = _JSON_BLOCK.search(raw)
    if not match:
        raise ValueError(f"No JSON object found in model output: {raw!r}")
    return json.loads(match.group(0))

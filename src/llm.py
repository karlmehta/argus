"""Anthropic Messages API client for Argus v2.

One prompt in, one JSON object out — the model never uses tools to explore. Output
is forced into a JSON schema via a single required tool call (Anthropic validates the
shape). The stable prefix is cached (1h TTL) so back-to-back PRs/pushes in a repo reuse
it. Every call returns a usage dict for cost accounting.
"""
from __future__ import annotations

import json
import os

import anthropic

_PRICING = json.load(open(os.path.join(os.path.dirname(__file__), "pricing.json")))
_CACHE_BETA = "extended-cache-ttl-2025-04-11"


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def price(model: str) -> dict:
    if model not in _PRICING:
        raise RuntimeError(f"no pricing for model '{model}' in pricing.json — refusing to run blind")
    return _PRICING[model]


def cost_usd(model: str, usage: dict) -> float:
    p = price(model)
    return round(
        usage.get("input_tokens", 0) / 1e6 * p["input"]
        + usage.get("output_tokens", 0) / 1e6 * p["output"]
        + usage.get("cache_creation_input_tokens", 0) / 1e6 * p["cache_write"]
        + usage.get("cache_read_input_tokens", 0) / 1e6 * p["cache_read"],
        6,
    )


def _usage_dict(u) -> dict:
    return {
        "input_tokens": getattr(u, "input_tokens", 0) or 0,
        "output_tokens": getattr(u, "output_tokens", 0) or 0,
        "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0,
        "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0) or 0,
    }


def call_json(model: str, stable_prefix: str, variable_suffix: str, instruction: str,
              schema: dict, schema_name: str, max_tokens: int) -> tuple[dict, dict]:
    """Return (parsed_object, usage). Forces the model to emit `schema_name` once.
    One schema-repair retry on malformed output; raises on a second failure."""
    client = _client()
    system = [{
        "type": "text",
        "text": stable_prefix,
        "cache_control": {"type": "ephemeral", "ttl": "1h"},
    }]
    tool = {"name": schema_name, "description": f"Return the {schema_name} result.", "input_schema": schema}

    def once(extra_user: str | None) -> tuple[dict, dict]:
        content = f"{variable_suffix}\n\n{instruction}"
        if extra_user:
            content += f"\n\n{extra_user}"
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            tools=[tool],
            tool_choice={"type": "tool", "name": schema_name},
            messages=[{"role": "user", "content": content}],
            extra_headers={"anthropic-beta": _CACHE_BETA},
        )
        usage = _usage_dict(resp.usage)
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use" and block.name == schema_name:
                return dict(block.input), usage
        raise ValueError("model did not return the required tool call")

    try:
        return once(None)
    except Exception as e:  # noqa: BLE001 — one repair attempt
        obj, usage2 = once(f"Your previous response was invalid ({e}). Return ONLY a valid {schema_name} tool call.")
        return obj, usage2


def count_input_tokens(model: str, stable_prefix: str, variable_suffix: str, instruction: str) -> int:
    """Pre-call token count for budget enforcement (cheap; no generation)."""
    try:
        r = _client().messages.count_tokens(
            model=model,
            system=[{"type": "text", "text": stable_prefix}],
            messages=[{"role": "user", "content": f"{variable_suffix}\n\n{instruction}"}],
        )
        return r.input_tokens
    except Exception:
        return (len(stable_prefix) + len(variable_suffix) + len(instruction)) // 4

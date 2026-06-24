python
// src/bedrock_client.py
"""AWS Bedrock client for asynchronous LLM invocations.

This module wraps the synchronous boto3 Bedrock Runtime client and runs
inference on the default executor so it can be awaited from async code.

Configuration is read from environment variables:
    AWS_BEDROCK_REGION    - AWS region (default: AWS_REGION env or "us-east-1")
    BEDROCK_MODEL_ID       - default model id to invoke
    AWS_ACCESS_KEY_ID      - standard boto3 credential chain
    AWS_SECRET_ACCESS_KEY  - standard boto3 credential chain
    AWS_PROFILE            - standard boto3 profile chain

No credentials, regions, or model ids are hardcoded beyond safe defaults.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict, Optional

import boto3
from botocore.config import Config

logger = logging.getLogger(__name__)

DEFAULT_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-sonnet-20240229-v1:0")
DEFAULT_REGION = os.getenv("AWS_BEDROCK_REGION") or os.getenv("AWS_REGION") or "us-east-1"

# Maximum payload size accepted by Bedrock invoke_model (6 MB).
_MAX_BODY_BYTES = 6 * 1024 * 1024


def _build_client():
    """Construct a configured Bedrock Runtime client.

    Uses an adaptive retry policy so transient throttling is handled
    by the SDK before our own retry logic kicks in.
    """
    config = Config(
        region_name=DEFAULT_REGION,
        retries={"max_attempts": 5, "mode": "adaptive"},
        connect_timeout=10,
        read_timeout=120,
    )
    return boto3.client("bedrock-runtime", config=config)


def _resolve_model_id(model_id: Optional[str]) -> str:
    """Return the requested model id, falling back to the env-configured default."""
    return model_id or os.getenv("BEDROCK_MODEL_ID") or DEFAULT_MODEL_ID


def _extract_text(payload: Dict[str, Any]) -> str:
    """Normalize Bedrock responses across model families.

    Anthropic Claude returns ``{"content": [{"type": "text", "text": "..."}, ...]}``.
    Amazon Titan returns ``{"results": [{"outputText": "..."}]}``.
    AI21 Jamba returns ``{"choices": [{"message": {"content": "..."}}]}``.
    Meta Llama returns ``{"generation": "..."}``.
    """
    content = payload.get("content")
    if isinstance(content, list):
        parts = [
            str(item.get("text", ""))
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        ]
        if parts:
            return "\n".join(parts).strip()

    results = payload.get("results")
    if isinstance(results, list) and results:
        first = results[0]
        if isinstance(first, dict):
            return str(first.get("outputText") or first.get("output_text") or "").strip()

    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message") or {}
            if isinstance(message, dict) and message.get("content"):
                return str(message["content"]).strip()
            return str(first.get("text") or "").strip()

    for key in ("generation", "completion", "output_text"):
        if payload.get(key):
            return str(payload[key]).strip()

    logger.warning("Unrecognized Bedrock response shape: keys=%s", list(payload.keys()))
    return ""


async def invoke_bedrock(
    prompt: str,
    model_id: Optional[str] = None,
    max_tokens: int = 4096,
    temperature: float = 0.0,
    system: Optional[str] = None,
    top_p: float = 0.999,
) -> str:
    """Invoke a Bedrock foundation model asynchronously.

    Args:
        prompt: User message to send to the model.
        model_id: Optional override; defaults to ``BEDROCK_MODEL_ID`` env var.
        max_tokens: Maximum tokens to generate (clamped to [1, 8192]).
        temperature: Sampling temperature in [0, 1].
        system: Optional system prompt (Anthropic-style).
        top_p: Nucleus sampling cutoff.

    Returns:
        The model's text response as a single string.

    Raises:
        RuntimeError: If the model invocation fails after retries.
        ValueError: If the prompt is empty or parameters are out of range.
    """
    if not prompt or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")
    if not (0.0 <= temperature <= 1.0):
        raise ValueError("temperature must be between 0.0 and 1.0")
    if not (1 <= max_tokens <= 8192):
        raise ValueError("max_tokens must be between 1 and 8192")

    chosen_model = _resolve_model_id(model_id)
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": top_p,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        body["system"] = system

    encoded = json.dumps(body).encode("utf-8")
    if len(encoded) > _MAX_BODY_BYTES:
        raise ValueError(
            f"Request body exceeds Bedrock limit ({len(encoded)} > {_MAX_BODY_BYTES} bytes); "
            "truncate the input text."
        )

    def _invoke() -> str:
        client = _build_client()
        try:
            response = client.invoke_model(
                modelId=chosen_model,
                contentType="application/json",
                accept="application/json",
                body=encoded,
            )
        except client.exceptions.AccessDeniedException as exc:
            logger.error("Bedrock access denied for model %s: %s", chosen_model, exc)
            raise RuntimeError(f"Bedrock access denied for model {chosen_model}") from exc
        except client.exceptions.ThrottlingException as exc:
            logger.warning("Bedrock throttling on model %s: %s", chosen_model, exc)
            raise RuntimeError(f"Bedrock throttling on model {chosen_model}") from exc
        except client.exceptions.ValidationException as exc:
            logger.error("Bedrock validation error on model %s: %s", chosen_model, exc)
            raise RuntimeError(f"Bedrock validation error on model {chosen_model}") from exc
        except Exception as exc:  # pragma: no cover - boto3 surface area
            logger.exception("Unexpected Bedrock error on model %s", chosen_model)
            raise RuntimeError(f"Bedrock invocation failed: {exc}") from exc

        raw = response.get("body")
        if raw is None:
            return ""
        payload_bytes = raw.read() if hasattr(raw, "read") else raw
        try:
            payload = json.loads(payload_bytes)
        except json.JSONDecodeError as exc:
            logger.error("Failed to decode Bedrock response: %s", exc)
            raise RuntimeError("Bedrock returned non-JSON response") from exc
        return _extract_text(payload)

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _invoke)


async def invoke_bedrock_json(
    prompt: str,
    model_id: Optional[str] = None,
    max_tokens: int = 4096,
    temperature: float = 0.0,
    system: Optional[str] = None,
) -> Dict[str, Any]:
    """Invoke Bedrock and parse the response as a JSON object.

    Strips common markdown fences and preamble text before loading. Raises
    ``ValueError`` if the response cannot be parsed as a JSON object.
    """
    raw = await invoke_bedrock(
        prompt,
        model_id=model_id,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
    )
    return _parse_json_object(raw)


def _parse_json_object(raw: str) -> Dict[str, Any]:
    """Tolerantly parse a JSON object from a model response string."""
    text = (raw or "").strip()
    if not text:
        raise ValueError("Empty response from model")

    # Strip 
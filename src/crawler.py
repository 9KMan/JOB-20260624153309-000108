python
// src/crawler.py
"""Web crawler built on Crawl4Ai with proxy rotation and per-source rate limiting.

The crawler reads a YAML configuration of sources and yields normalized
document dicts of the form::

    {
        "id": "<source-name>:<timestamp-ms>",
        "source_name": "...",
        "source_url": "...",
        "kind": "html" | "rss" | ...,
        "html": "...",        # raw HTML (may be empty if markdown-only)
        "text": "...",        # markdown/text content (primary input to extraction)
        "fetched_at": 1719240000.123,
    }

The crawl4ai import is performed lazily inside :func:`crawl_sources` so
that importing this module never fails if crawl4ai is missing.
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator, Dict, List, Optional, Union

import yaml

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class Source:
    """Configuration for a single crawlable source."""

    name: str
    url: str
    kind: str = "html"
    rate_limit: float = 1.0
    proxy_pool: List[str] = field(default_factory=list)
    headers: Dict[str, str] = field(default_factory=dict)
    timeout_seconds: float = 60.0


def parse_sources(yaml_text: str) -> List[Source]:
    """Parse a sources.yaml document into a list of :class:`Source` objects."""
    if not yaml_text or not yaml_text.strip():
        return []
    try:
        data = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        logger.error("Failed to parse sources YAML: %s", exc)
        return []
    if not isinstance(data, dict):
        logger.error("sources.yaml top-level must be a mapping; got %s", type(data).__name__)
        return []

    items = data.get("sources") or []
    if not isinstance(items, list):
        logger.error("'sources' must be a list; got %s", type(items).__name__)
        return []

    sources: List[Source] = []
    for idx, raw in enumerate(items):
        if not isinstance(raw, dict):
            logger.warning("Skipping non-mapping source at index %d: %r", idx, raw)
            continue
        url = raw.get("url")
        if not url:
            logger.warning("Skipping source at index %d: missing 'url'", idx)
            continue
        name = raw.get("name") or url
        try:
            sources.append(
                Source(
                    name=str(name),
                    url=str(url),
                    kind=str(raw.get("kind", "html")).lower(),
                    rate_limit=float(raw.get("rate_limit", 1.0)),
                    proxy_pool=list(raw.get("proxy_pool") or []),
                    headers=dict(raw.get("headers") or {}),
                    timeout_seconds=float(raw.get("timeout_seconds", 60.0)),
                )
            )
        except (TypeError, ValueError) as exc:
            logger.warning("Skipping malformed source at index %d (%s): %s", idx, raw, exc)
    return sources


# ---------------------------------------------------------------------------
# Rate limiting & proxy selection
# ---------------------------------------------------------------------------


@dataclass
class _RateLimiter:
    """Simple token-bucket-ish limiter; sleeps so average rate <= ``rate`` rps."""

    rate: float
    _last: float = field(default=0.0, init=False)

    async def wait(self) -> None:
        if self.rate <= 0:
            return
        now = time.monotonic()
        elapsed = now - self._last
        delay = (1.0 / self.rate) - elapsed
        if delay > 0:
            await asyncio.sleep(delay)
        self._last = time.monotonic()


def _select_proxy(pool: List[str]) -> Optional[str]:
    """Pick a proxy from the per-source pool, falling back to env vars."""
    if pool:
        return random.choice(pool)
    for env_var in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        value = os.getenv(env_var)
        if value:
            return value
    return None


# ---------------------------------------------------------------------------
# Crawl helpers
# ---------------------------------------------------------------------------


def _extract_text_from_result(result: Any) -> str:
    """Pull a usable text body out of a crawl4ai result object."""
    if result is None:
        return ""
    markdown = getattr(result, "markdown", None)
    if markdown is None:
        cleaned = getattr(result, "cleaned_html", "") or ""
        return _html_to_text(cleaned)
    if isinstance(markdown, str):
        return markdown
    # crawl4ai >= 0.2 returns a MarkdownGenerationResult-like object.
    for attr in ("raw_markdown", "fit_markdown", "markdown_text"):
        value = getattr(markdown, attr, None)
        if isinstance(value, str) and value.strip():
            return value
    return ""


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_HTML_ENTITY_RE = re.compile(r"&(amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);")


def _html_to_text(html: str) -> str:
    """Best-effort HTML to text fallback if no markdown is available."""
    if not html:
        return ""
    text = _HTML_TAG_RE.sub(" ", html)
    text = _HTML_ENTITY_RE.sub(
        lambda m: {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'"}.get(
            m.group(1), ""
        ),
        text,
    )
    return re.sub(r"\s+", " ", text).strip()


def _extract_html_from_result(result: Any) -> str:
    if result is None:
        return ""
    for attr in ("html", "cleaned_html"):
        value = getattr(result, attr, None)
        if isinstance(value, str):
            return value
    return ""


async def _crawl_one(crawler: Any, source: Source, limiter: _RateLimiter) -> Optional[Dict]:
    """Crawl a single source, returning a normalized document or None."""
    await limiter.wait()
    proxy = _select_proxy(source.proxy_pool)
    try:
        result = await crawler.arun(
            url=source.url,
            proxy=proxy,
            headers=source.headers or None,
            timeout=int(source.timeout_seconds),
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.error("Crawl failed for %s (%s): %s", source.name, source.url, exc)
        return None

    success = getattr(result, "success", False)
    if not success:
        status = getattr(result, "status_code", None)
        logger.warning("Crawl unsuccessful for %s (status=%s)", source.url, status)
        return None

    html = _extract_html_from_result(result)
    text = _extract_text_from_result(result)

    if not text and not html:
        logger.warning("Crawl for %s produced empty content", source.url)
        return None

    timestamp_ms = int(time.time() * 1000)
    return {
        "id": f"{source.name}:{timestamp_ms}",
        "source_name": source.name,
        "source_url": source.url,
        "kind": source.kind,
        "html": html,
        "text": text or _html_to_text(html),
        "fetched_at": time.time(),
        "proxy": proxy,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def crawl_sources(sources_yaml: str) -> AsyncIterator[Dict]:
    """Yield normalized documents from the configured sources.

    Each document is a dict; see module docstring for the shape.
    """
    # Lazy import so the module can be imported without crawl4ai installed.
    from crawl4ai import AsyncWebCrawler

    sources = parse_sources(sources_yaml)
    if not sources:
        logger.info("No sources configured; nothing to crawl")
        return

    logger.info("Starting crawl of %d source(s)", len(sources))
    async with AsyncWebCrawler() as crawler:
        for source in sources:
            limiter = _RateLimiter(rate=source.rate_limit)
            try:
                document = await _crawl_one(crawler, source, limiter)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("Unexpected error crawling %s: %s", source.name, exc)
                continue
            if document is not None:
                yield document


async def crawl_sources_from_path(path: Union[str, Path]) -> AsyncIterator[Dict]:
    """Read a sources YAML file from disk and yield crawled documents."""
    file_path = Path(path)
    if not file_path.exists():
        logger.error("Sources config not found: %s", file_path)
        return
    text = file_path.read_text(encoding="utf-8")
    async for document in crawl_sources(text):
        yield document


async def crawl_single(url: str, **kwargs: Any) -> Optional[Dict]:
    """Convenience wrapper for ad-hoc single-URL crawls (used in tests)."""
    from crawl4ai import AsyncWebCrawler

    proxy = kwargs.pop("proxy", None)
    headers = kwargs.pop("headers", None) or {}
    rate_limit = float(kwargs.pop("rate_limit", 1.0))
    timeout = float(kwargs.pop("timeout_seconds", 60.0))
    name = kwargs.pop("name", url)
    if kwargs:
        logger.warning("crawl_single: ignoring extra kwargs: %s", list(kwargs.keys()))

    source = Source(
        name=name,
        url=url,
        proxy_pool=[proxy] if proxy else [],
        headers=headers,
        rate_limit=rate_limit,
        timeout_seconds=timeout,
    )
    limiter = _RateLimiter(rate=source.rate_limit)
    async with AsyncWebCrawler() as crawler:
        return await _crawl_one(crawler, source, limiter)


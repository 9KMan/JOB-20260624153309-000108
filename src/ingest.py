python
// src/ingest.py
"""Document ingestion entry point.

Runs the full pipeline::

    sources.yaml  ->  crawl_sources  ->  run_extraction_pipeline  ->  write_to_graph

Usage::

    python -m src.ingest
    python -m src.ingest --config path/to/sources.yaml --limit 10
    python -m src.ingest --log-level DEBUG

Configuration is read from environment variables where applicable
(``NEO4J_*``, ``AWS_BEDROCK_REGION``, ``BEDROCK_MODEL_ID``, ``LOG_LEVEL``).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
from pathlib import Path
from typing import List, Optional, Sequence

from src.crawler import crawl_sources_from_path
from src.extractor import ExtractionResult, run_extraction_pipeline
from src.graph_writer import GraphWriter, close_default_writer, write_to_graph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CLI plumbing
# ---------------------------------------------------------------------------


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    # Quiet down noisy libraries unless the user explicitly asks for DEBUG.
    if level.upper() != "DEBUG":
        for noisy in ("botocore", "boto3", "urllib3", "asyncio"):
            logging.getLogger(noisy).setLevel(logging.WARNING)


def _default_config_path() -> Path:
    env_path = os.getenv("INGEST_CONFIG_PATH")
    return Path(env_path) if env_path else Path("config/sources.yaml")


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the document ingestion pipeline.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to sources.yaml (default: $INGEST_CONFIG_PATH or config/sources.yaml)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of documents to process (default: unbounded)",
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("LOG_LEVEL", "INFO"),
        help="Logging level (DEBUG, INFO, WARNING, ERROR)",
    )
    parser.add_argument(
        "--skip-graph",
        action="store_true",
        help="Run crawl + extract only; do not write to the graph database",
    )
    parser.add_argument(
        "--ensure-constraints",
        action="store_true",
        help="Create Neo4j uniqueness constraints before ingesting",
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class _CancellationFlag:
    """Tiny SIGINT/SIGTERM-aware flag so the pipeline can shut down cleanly."""

    def __init__(self) -> None:
        self._stop = asyncio.Event()

    def request(self) -> None:
        self._stop.set()

    def requested(self) -> bool:
        return self._stop.is_set()

    async def wait(self) -> None:
        await self._stop.wait()


async def _process_document(
    doc: dict,
    writer: Optional[GraphWriter],
    skip_graph: bool,
) -> bool:
    """Run extraction on a single document and (optionally) write to the graph.

    Returns True on success, False on failure.
    """
    doc_id = doc.get("id") or doc.get("source_url") or "<unknown>"
    logger.info("Processing document %s from %s", doc_id, doc.get("source_url"))

    try:
        result: ExtractionResult = await run_extraction_pipeline(doc)
    except Exception as exc:
        logger.exception("Extraction failed for %s: %s", doc_id, exc)
        return False

    if skip_graph:
        logger.info(
            "Skipping graph write for %s (entities=%d events=%d relationships=%d)",
            doc_id,
            len(result.entities),
            len(result.events),
            len(result.relationships),
        )
        return True

    try:
        if writer is not None:
            await writer.write_to_graph(result)
        else:
            await write_to_graph(result)
    except Exception as exc:
        logger.exception("Graph write failed for %s: %s", doc_id, exc)
        return False
    return True


async def _run_pipeline(
    config_path: Path,
    limit: Optional[int],
    skip_graph: bool,
    ensure_constraints: bool,
    cancel: _CancellationFlag,
) -> int:
    """Top-level coroutine. Returns a shell-style exit code."""
    if not config_path.exists():
        logger.error("Config file not found: %s", config_path)
        return 2

    processed = 0
    succeeded = 0
    failed = 0

    writer: Optional[GraphWriter] = None
    try:
        if not skip_graph:
            writer = GraphWriter()
            if ensure_constraints:
                await writer.ensure_constraints()
            await writer.__aenter__()

        async for doc in crawl_sources_from_path(config_path):
            if cancel.requested():
                logger.warning("Cancellation requested; stopping after %d docs", processed)
                break

            ok = await _process_document(doc, writer, skip_graph)
            processed += 1
            if ok:
                succeeded += 1
            else:
                failed += 1

            if limit is not None and processed >= limit:
                logger.info("Reached limit of %d documents; stopping", limit)
                break
    finally:
        if writer is not None:
            try:
                await writer.close()
            except Exception as exc:  # pragma: no cover
                logger.warning("Error closing graph writer: %s", exc)
        # Close the default writer too in case it was used.
        await close_default_writer()

    logger.info(
        "Ingestion complete: processed=%d succeeded=%d failed=%d",
        processed, succeeded, failed,
    )
    return 0 if failed == 0 else 1


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


async def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    _setup_logging(args.log_level)

    config_path = args.config or _default_config_path()
    cancel = _CancellationFlag()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, cancel.request)
        except NotImplementedError:  # pragma: no cover - Windows
            signal.signal(sig, lambda *_: cancel.request())

    try:
        return await _run_pipeline(
            config_path=config_path,
            limit=args.limit,
            skip_graph=args.skip_graph,
            ensure_constraints=args.ensure_constraints,
            cancel=cancel,
        )
    except asyncio.CancelledError:
        logger.warning("Pipeline cancelled")
        return 130


def ingest(argv: Optional[Sequence[str]] = None) -> int:
    """Synchronous entry point used by ``python -m src.ingest`` and tests."""
    try:
        return asyncio.run(main(argv))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(ingest())


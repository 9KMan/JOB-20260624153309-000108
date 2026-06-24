python
// src/graph_writer.py
"""Graph persistence layer for extracted entities, events, and relationships.

Targets Neo4j via the official async driver. AWS Neptune is supported by
pointing ``NEO4J_URI`` at a Neptune Bolt endpoint and providing appropriate
auth credentials via environment variables.

Configuration is read from environment variables:
    NEO4J_URI         - Bolt URI, e.g. bolt://localhost:7687 or bolt+s://...
    NEO4J_USER        - Database user (default: "neo4j")
    NEO4J_PASSWORD    - Database password (required; not hardcoded)
    NEO4J_DATABASE    - Database name (default: "neo4j")
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any, Dict, List, Optional, Sequence

from neo4j import AsyncDriver, AsyncGraphDatabase, AsyncSession

from src.extractor import Entity, Event, ExtractionResult, Relationship

logger = logging.getLogger(__name__)


_REL_TYPE_SAFE_RE = re.compile(r"[^A-Za-z0-9_]")


def _sanitize_rel_type(value: str) -> str:
    """Coerce an arbitrary relation type into a valid Cypher token."""
    sanitized = _REL_TYPE_SAFE_RE.sub("_", (value or "").strip()).strip("_")
    if not sanitized:
        return "RELATED_TO"
    if sanitized[0].isdigit():
        sanitized = "R_" + sanitized
    return sanitized.upper()


def _neo4j_password() -> str:
    pwd = os.getenv("NEO4J_PASSWORD")
    if not pwd:
        raise RuntimeError("NEO4J_PASSWORD environment variable is required")
    return pwd


def build_driver(
    uri: Optional[str] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
) -> AsyncDriver:
    """Construct a configured async Neo4j driver from env vars or overrides."""
    resolved_uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
    resolved_user = user or os.getenv("NEO4J_USER", "neo4j")
    resolved_password = password if password is not None else _neo4j_password()
    return AsyncGraphDatabase.driver(
        resolved_uri,
        auth=(resolved_user, resolved_password),
        max_connection_pool_size=int(os.getenv("NEO4J_POOL_SIZE", "50")),
        connection_acquisition_timeout=float(os.getenv("NEO4J_ACQ_TIMEOUT", "30")),
    )


# ---------------------------------------------------------------------------
# GraphWriter
# ---------------------------------------------------------------------------


class GraphWriter:
    """Persists entities, events, and relationships to Neo4j/Neptune.

    Can be used as an async context manager::

        async with GraphWriter() as writer:
            await writer.write_to_graph(result)
    """

    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        database: Optional[str] = None,
    ) -> None:
        self._explicit_uri = uri
        self._explicit_user = user
        self._explicit_password = password
        self._database = database or os.getenv("NEO4J_DATABASE", "neo4j")
        self._driver: Optional[AsyncDriver] = None

    async def _get_driver(self) -> AsyncDriver:
        if self._driver is None:
            self._driver = build_driver(
                uri=self._explicit_uri,
                user=self._explicit_user,
                password=self._explicit_password,
            )
        return self._driver

    async def close(self) -> None:
        if self._driver is not None:
            await self._driver.close()
            self._driver = None

    async def __aenter__(self) -> "GraphWriter":
        await self._get_driver()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    # -----------------------------------------------------------------
    # Public write API
    # -----------------------------------------------------------------

    async def write_to_graph(self, result: ExtractionResult) -> None:
        """Persist an :class:`ExtractionResult` in a single transaction."""
        if not isinstance(result, ExtractionResult):
            raise TypeError("write_to_graph expects an ExtractionResult")
        await self.write_nodes_and_edges(
            result.entities, result.events, result.relationships
        )

    async def write_nodes_and_edges(
        self,
        entities: Sequence[Entity],
        events: Sequence[Event],
        relationships: Sequence[Relationship],
    ) -> None:
        """Persist entities, events, and relationships inside one transaction."""
        driver = await self._get_driver()
        entities_list: List[Entity] = list(entities)
        events_list: List[Event] = list(events)
        rels_list: List[Relationship] = list(relationships)

        try:
            async with driver.session(database=self._database) as session:
                await session.execute_write(
                    self._write_all,
                    entities_list,
                    events_list,
                    rels_list,
                )
        except Exception as exc:
            logger.exception(
                "Graph write failed: %d entities, %d events, %d relationships (%s)",
                len(entities_list),
                len(events_list),
                len(rels_list),
                exc,
            )
            raise

        logger.info(
            "Graph write complete: %d entities, %d events, %d relationships",
            len(entities_list),
            len(events_list),
            len(rels_list),
        )

    # -----------------------------------------------------------------
    # Transactional body
    # -----------------------------------------------------------------

    @staticmethod
    async def _write_all(
        tx: Any,
        entities: List[Entity],
        events: List[Event],
        relationships: List[Relationship],
    ) -> None:
        for entity in entities:
            await tx.run(
                """
                MERGE (n:Entity {id: $id})
                SET n.type = $type,
                    n.name = $name,
                    n.attributes = $attributes
                """,
                id=entity.id,
                type=entity.type,
                name=entity.name,
                attributes=dict(entity.attributes or {}),
            )

        for event in events:
            await tx.run(
                """
                MERGE (n:Event {id: $id})
                SET n.type = $type,
                    n.occurred_at = $occurred_at,
                    n.attributes = $attributes
                """,
                id=event.id,
                type=event.type,
                occurred_at=event.occurred_at,
                attributes=dict(event.attributes or {}),
            )

        # Track which ids were successfully written so we can drop dangling edges.
        written_ids: set[str] = {e.id for e in entities} | {ev.id for ev in events}

        for rel in relationships:
            if rel.source not in written_ids or rel.target not in written_ids:
                logger.debug(
                    "Skipping relationship %s -[%s]-> %s (endpoint not written)",
                    rel.source, rel.type, rel.target,
                )
                continue
            rel_type = _sanitize_rel_type(rel.type)
            # Cypher does not allow parameterized relationship types, so we
            # interpolate after sanitizing the type token above.
            query = (
                f"MATCH (a {{id: $source}}) "
                f"MATCH (b {{id: $target}}) "
                f"MERGE (a)-[r:{rel_type}]->(b) "
                f"SET r += $attributes"
            )
            await tx.run(
                query,
                source=rel.source,
                target=rel.target,
                attributes=dict(rel.attributes or {}),
            )

    # -----------------------------------------------------------------
    # Maintenance helpers
    # -----------------------------------------------------------------

    async def ensure_constraints(self) -> None:
        """Create uniqueness constraints required by the writer.

        Safe to call repeatedly; Neo4j will treat redundant CREATE
        CONSTRAINT statements as no-ops once they exist.
        """
        driver = await self._get_driver()
        statements = [
            "CREATE CONSTRAINT entity_id_unique IF NOT EXISTS FOR (n:Entity) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT event_id_unique IF NOT EXISTS FOR (n:Event) REQUIRE n.id IS UNIQUE",
        ]
        async with driver.session(database=self._database) as session:
            for stmt in statements:
                try:
                    await session.run(stmt)
                except Exception as exc:
                    # Neptune has limited Cypher support; treat syntax errors as warnings.
                    logger.warning("ensure_constraints: statement failed (%s): %s", stmt, exc)


# ---------------------------------------------------------------------------
# Module-level convenience for the ingest entry point
# ---------------------------------------------------------------------------


_DEFAULT_WRITER: Optional[GraphWriter] = None
_DEFAULT_LOCK = asyncio.Lock()


async def write_to_graph(result: ExtractionResult) -> None:
    """Persist an :class:`ExtractionResult` using a process-wide writer.

    The default writer is created lazily from environment variables and is
    reused across calls. Use :class:`GraphWriter` directly for finer-grained
    control (multiple databases, custom credentials, etc.).
    """
    global _DEFAULT_WRITER
    if _DEFAULT_WRITER is None:
        async with _DEFAULT_LOCK:
            if _DEFAULT_WRITER is None:
                _DEFAULT_WRITER = GraphWriter()
    await _DEFAULT_WRITER.write_to_graph(result)


async def close_default_writer() -> None:
    """Close the default writer, if one exists (called from ingest shutdown)."""
    global _DEFAULT_WRITER
    writer = _DEFAULT_WRITER
    _DEFAULT_WRITER = None
    if writer is not None:
        await writer.close()


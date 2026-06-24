python
// src/extractor.py
"""Multi-pass LLM extraction pipeline.

Produces ontology-aligned entities, events, and relationships from a
document's plain text using a three-pass Bedrock invocation. Each pass
uses a focused prompt and parses a JSON object out of the model response.

The three passes are intentionally independent so they can be parallelized
by an external orchestrator if desired; the default sequential ordering is
sufficient for small batches and gives deterministic logging order.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, ValidationError

from src.bedrock_client import invoke_bedrock_json

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic schema (ontology-aligned)
# ---------------------------------------------------------------------------


class Entity(BaseModel):
    """An entity extracted from a document (Person, Org, Location, etc.)."""

    id: str = Field(..., min_length=1, description="Stable, slug-style identifier")
    type: str = Field(..., min_length=1, description="Ontology type label")
    name: str = Field(..., min_length=1, description="Human-readable name")
    attributes: Dict[str, Any] = Field(default_factory=dict)


class Event(BaseModel):
    """An event extracted from a document."""

    id: str = Field(..., min_length=1)
    type: str = Field(..., min_length=1)
    occurred_at: str = Field("", description="ISO-8601 date or datetime")
    participants: List[str] = Field(default_factory=list)
    attributes: Dict[str, Any] = Field(default_factory=dict)


class Relationship(BaseModel):
    """A directed relationship between two entities or events."""

    source: str = Field(..., min_length=1)
    target: str = Field(..., min_length=1)
    type: str = Field(..., min_length=1)
    attributes: Dict[str, Any] = Field(default_factory=dict)


class ExtractionResult(BaseModel):
    """Combined output of all three extraction passes."""

    entities: List[Entity] = Field(default_factory=list)
    events: List[Event] = Field(default_factory=list)
    relationships: List[Relationship] = Field(default_factory=list)

    def counts(self) -> Dict[str, int]:
        return {
            "entities": len(self.entities),
            "events": len(self.events),
            "relationships": len(self.relationships),
        }


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------


ENTITY_PROMPT = """Extract all named entities from the document below.
Return ONLY a JSON object of the form:
{{"entities": [{{"id": "<slug>", "type": "<Type>", "name": "<name>", "attributes": {{...}}}}, ...]}}

Rules:
- Use slug-style ids (lowercase, hyphens, unique within the document)
- Use ontology-style types such as Person, Organization, Location, Artifact, Concept
- Include only entities explicitly mentioned in the document
- attributes is an optional object of additional structured fields

Document:
\"\"\"
{text}
\"\"\"
"""


EVENT_PROMPT = """Extract all events from the document below.
Return ONLY a JSON object of the form:
{{"events": [{{"id": "<slug>", "type": "<EventType>", "occurred_at": "<ISO-8601>", "participants": ["<entity_id>", ...], "attributes": {{...}}}}, ...]}}

Rules:
- occurred_at must be ISO-8601 (date or datetime precision)
- participants reference entity ids produced in the entity extraction pass
- Include only events explicitly mentioned in the document

Document:
\"\"\"
{text}
\"\"\"
"""


RELATIONSHIP_PROMPT = """Extract all relationships between entities and events from the document below.
Return ONLY a JSON object of the form:
{{"relationships": [{{"source": "<id>", "target": "<id>", "type": "<RELATION_TYPE>", "attributes": {{...}}}}, ...]}}

Rules:
- Use uppercase snake_case relation types (e.g. WORKS_FOR, LOCATED_IN, PARTICIPATED_IN)
- source and target must reference ids from the entity/event extraction passes
- Include only relationships explicitly stated or directly entailed by the document

Document:
\"\"\"
{text}
\"\"\"
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(value: str) -> str:
    """Convert an arbitrary string into a slug suitable for an entity id."""
    value = (value or "").lower().strip()
    value = _SLUG_RE.sub("-", value).strip("-")
    return value or "entity"


def _safe_rel_type(value: str) -> str:
    """Coerce a relationship type into a valid Cypher relationship type token."""
    sanitized = re.sub(r"[^A-Za-z0-9_]", "_", (value or "").strip()).strip("_")
    if not sanitized:
        return "RELATED_TO"
    if sanitized[0].isdigit():
        sanitized = "R_" + sanitized
    return sanitized.upper()


def _coerce_entities(raw: Any, prefix: str = "") -> List[Entity]:
    if not isinstance(raw, list):
        return []
    out: List[Entity] = []
    seen: set[str] = set()
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        try:
            base_id = item.get("id") or item.get("name") or f"entity-{idx}"
            base_id = _slugify(str(base_id))
            eid = f"{prefix}{base_id}" if prefix else base_id
            # Disambiguate duplicates within the document.
            original = eid
            counter = 1
            while eid in seen:
                counter += 1
                eid = f"{original}-{counter}"
            seen.add(eid)
            out.append(
                Entity(
                    id=eid,
                    type=str(item.get("type") or "Unknown").strip() or "Unknown",
                    name=str(item.get("name") or eid).strip() or eid,
                    attributes=dict(item.get("attributes") or {}),
                )
            )
        except ValidationError as exc:
            logger.warning("Skipping invalid entity at index %d: %s", idx, exc)
    return out


def _coerce_events(raw: Any, prefix: str = "") -> List[Event]:
    if not isinstance(raw, list):
        return []
    out: List[Event] = []
    seen: set[str] = set()
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        try:
            base_id = item.get("id") or item.get("type") or f"event-{idx}"
            base_id = _slugify(str(base_id))
            eid = f"{prefix}{base_id}" if prefix else base_id
            original = eid
            counter = 1
            while eid in seen:
                counter += 1
                eid = f"{original}-{counter}"
            seen.add(eid)
            out.append(
                Event(
                    id=eid,
                    type=str(item.get("type") or "Event").strip() or "Event",
                    occurred_at=str(item.get("occurred_at") or "").strip(),
                    participants=[str(p) for p in (item.get("participants") or []) if p],
                    attributes=dict(item.get("attributes") or {}),
                )
            )
        except ValidationError as exc:
            logger.warning("Skipping invalid event at index %d: %s", idx, exc)
    return out


def _coerce_relationships(
    raw: Any,
    known_ids: set[str],
    prefix: str = "",
) -> List[Relationship]:
    if not isinstance(raw, list):
        return []
    out: List[Relationship] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        source = item.get("source")
        target = item.get("target")
        rel_type = item.get("type")
        if not source or not target or not rel_type:
            continue
        source_s = str(source).strip()
        target_s = str(target).strip()
        if not source_s or not target_s:
            continue
        # Best-effort id resolution: if the model referenced an un-prefixed id,
        # try matching it against any known id by suffix.
        if known_ids and source_s not in known_ids:
            for kid in known_ids:
                if kid.endswith(source_s) or source_s.endswith(kid):
                    source_s = kid
                    break
        if known_ids and target_s not in known_ids:
            for kid in known_ids:
                if kid.endswith(target_s) or target_s.endswith(kid):
                    target_s = kid
                    break
        out.append(
            Relationship(
                source=source_s,
                target=target_s,
                type=_safe_rel_type(str(rel_type)),
                attributes=dict(item.get("attributes") or {}),
            )
        )
    return out


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def _build_id_prefix(doc: Dict[str, Any]) -> str:
    """Build a short, stable id prefix from the document's identifier."""
    raw = doc.get("id") or doc.get("source_url") or doc.get("source_name")
    if not raw:
        return ""
    slug = _slugify(str(raw))
    return f"{slug}:" if slug else ""


async def _run_pass(prompt_template: str, text: str) -> Dict[str, Any]:
    """Run a single extraction pass and return its parsed JSON object."""
    prompt = prompt_template.format(text=text)
    return await invoke_bedrock_json(prompt)


async def run_extraction_pipeline(doc: Dict[str, Any]) -> ExtractionResult:
    """Run the three extraction passes against a single document.

    The input dict must contain a ``text`` field. Optional fields:
    ``id``, ``source_name``, ``source_url`` — used for id prefixing and
    traceability.

    Returns an ``ExtractionResult`` with all invalid entries filtered out.
    Raises ``ValueError`` if the document has no usable text.
    """
    if not isinstance(doc, dict):
        raise ValueError("doc must be a dict with at least a 'text' field")
    text = (doc.get("text") or "").strip()
    if not text:
        logger.warning("Empty document text; returning empty extraction result")
        return ExtractionResult()

    prefix = _build_id_prefix(doc)

    try:
        entity_payload, event_payload, rel_payload = await _gather_passes(text)
    except Exception as exc:
        logger.exception("Extraction failed for doc %s: %s", doc.get("id"), exc)
        # Re-raise so the caller can decide whether to skip or retry.
        raise

    entities = _coerce_entities(entity_payload.get("entities"), prefix=prefix)
    events = _coerce_events(event_payload.get("events"), prefix=prefix)
    known_ids = {e.id for e in entities} | {ev.id for ev in events}
    relationships = _coerce_relationships(
        rel_payload.get("relationships"), known_ids=known_ids, prefix=prefix
    )

    result = ExtractionResult(
        entities=entities,
        events=events,
        relationships=relationships,
    )
    logger.info(
        "Extraction for %s: %s",
        doc.get("id") or "<unknown>",
        json.dumps(result.counts()),
    )
    return result


async def _gather_passes(text: str) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """Run the three extraction passes concurrently."""
    import asyncio

    entity_task = asyncio.create_task(_run_pass(ENTITY_PROMPT, text))
    event_task = asyncio.create_task(_run_pass(EVENT_PROMPT, text))
    rel_task = asyncio.create_task(_run_pass(RELATIONSHIP_PROMPT, text))
    return await asyncio.gather(entity_task, event_task, rel_task)


# AI Knowledge Graph Engineer — Backend, ML, AWS

**Built by: KMan | AI-Augmented Engineering Factory**

## 1. Overview

A backend/ML engineering role for an AI-powered knowledge graph platform that transforms unstructured documents into structured, queryable intelligence. The platform already has a defined ontology, a working prototype, and a clear roadmap.

This engagement focuses on building the production-grade backend pipelines that:
- Ingest documents from public sources
- Run multi-pass LLM extraction (entities, events, relationships)
- Normalize extracted data into ontology-aligned objects
- Persist to a graph database (AWS Neptune or Neo4j)
- Expose the graph via queryable backend services

## 2. Technical Stack

- **Language:** Python 3.11+
- **LLM/ML:** AWS Bedrock (Claude), SageMaker, fine-tuning pipelines
- **Graph DB:** Neo4j or AWS Neptune (Gremlin/Cypher)
- **Data validation:** Pydantic
- **Web scraping:** Crawl4Ai, Scrapling, proxy rotation
- **Infrastructure:** AWS (ECS, Lambda, S3, CloudWatch)
- **Pipelines:** ETL/ELT orchestration

## 3. Scope (Phase 1 — Core Pipeline)

### Phase 1 — Document Ingestion
- Batch ingestion from public sources
- Web scraping (Crawl4Ai / Scrapling)
- Proxy rotation
- Storage in S3 with metadata

### Phase 2 — Text Normalization
- Parsing (PDF, HTML, plain text)
- Tokenization, language detection
- Document chunking for LLM context

### Phase 3 — Multi-Pass LLM Extraction
- Pass 1: entity extraction
- Pass 2: event extraction
- Pass 3: relationship extraction
- Schema enforcement via Pydantic

### Phase 4 — Knowledge Graph Construction
- Normalization/resolution of entities
- Ontology alignment
- Graph writes to Neo4j/Neptune

### Phase 5 — Backend API & Human-in-the-Loop
- Query API for graph traversal
- Review UI endpoints
- LLM fine-tuning data collection

## 4. Architecture

```
┌────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  Public        │───▶│  Ingestion       │───▶│  S3 (raw docs)   │
│  Sources       │    │  (Crawl4Ai)      │    └──────────────────┘
└────────────────┘    └──────────────────┘             │
                                                         ▼
┌────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  Graph DB      │◀───│  Normalization   │◀───│  LLM Extraction  │
│  (Neptune/     │    │  + Resolution    │    │  (multi-pass)    │
│   Neo4j)       │    └──────────────────┘    └──────────────────┘
└────────────────┘                                    │
       │                                              ▼
       ▼                                    ┌──────────────────┐
┌────────────────┐                          │  Bedrock /       │
│  Query API     │                          │  SageMaker       │
└────────────────┘                          └──────────────────┘
       │
       ▼
┌────────────────┐
│  Human Review  │
│  (HITL)        │
└────────────────┘
```

## 5. Deliverables

- Document ingestion pipeline (Crawl4Ai)
- Multi-pass LLM extraction service
- Pydantic schema for ontology-aligned objects
- Graph database writes (Neo4j/Neptune)
- Query API endpoints
- Human-in-the-loop review workflow
- AWS deployment config
- Monitoring + observability
- README with onboarding guide

## 6. Acceptance Criteria

- Documents ingested at scale (10k+/day)
- Multi-pass extraction produces ontology-aligned entities/events/relations
- Graph queries return results in <1s for typical traversals
- HITL review cycle is operational
- AWS deployment is observable (CloudWatch dashboards)
- Fine-tuning pipeline can ingest labeled examples

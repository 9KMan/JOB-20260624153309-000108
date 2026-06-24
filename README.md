# AI Knowledge Graph Platform — Ingestion & Extraction Pipeline

**Built by: KMan | AI-Augmented Engineering Factory**

## Business Problem Solved

Organizations accumulate vast amounts of unstructured data — news articles, regulatory filings, research papers, internal reports — that contain valuable entities, events, and relationships. Manually extracting and structuring this information is slow, error-prone, and doesn't scale.

This platform automates the journey from messy documents to queryable knowledge:
1. **Crawl** public sources (web pages, feeds, document repositories) on schedule
2. **Extract** structured entities, events, and relationships using multi-pass LLM pipelines (AWS Bedrock Claude)
3. **Normalize** extracted data against the founder's ontology
4. **Persist** to a graph database (AWS Neptune or Neo4j) for fast traversal queries
5. **Review** through a human-in-the-loop workflow that improves extraction accuracy over time

The system is built for production scale: batch ingestion at 10k+ documents/day, multi-pass LLM extraction with structured Pydantic validation, and AWS-native deployment.

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  Public Sources │───▶│  Ingestion       │───▶│  S3 (raw docs)   │
│  (RSS, web)     │    │  (Crawl4Ai)      │    └──────────────────┘
└─────────────────┘    └──────────────────┘             │
                                                         ▼
┌─────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  Graph DB       │◀───│  Normalization   │◀───│  Multi-pass LLM  │
│  (Neptune /     │    │  + Resolution    │    │  Extraction      │
│   Neo4j)        │    └──────────────────┘    └──────────────────┘
└─────────────────┘                                     │
       │                                                ▼
       ▼                                    ┌──────────────────┐
┌─────────────────┐                          │  Bedrock Claude  │
│  Query API      │                          │  (3 Sonnet)      │
│  (FastAPI)      │                          └──────────────────┘
└─────────────────┘
       │
       ▼
┌─────────────────┐
│  Human Review   │
│  (HITL)         │
└─────────────────┘
```

### Pipeline Flow

1. **Crawl**: `crawler.py` uses Crawl4Ai to fetch documents from configured sources with proxy rotation
2. **Extract**: `extractor.py` runs three Bedrock passes — entities → events → relationships
3. **Normalize**: Resolved against ontology, deduplicated, merged
4. **Persist**: `graph_writer.py` writes nodes/edges to Neptune or Neo4j
5. **Review**: HITL endpoint collects labels for fine-tuning
6. **Query**: FastAPI service exposes graph queries (Cypher/Gremlin)

## Tech Stack

| Layer | Tool |
|-------|------|
| Language | Python 3.11+ |
| LLM | AWS Bedrock (Claude 3 Sonnet) |
| Graph DB | Neo4j or AWS Neptune |
| Data Validation | Pydantic |
| Web Scraping | Crawl4Ai, Scrapling |
| Backend | FastAPI (query API) |
| AWS | ECS, Lambda, S3, CloudWatch |
| Testing | pytest, pytest-asyncio |

## Project Structure

```
JOB-20260624153309-000108/
├── src/
│   ├── ingest.py              # Batch ingestion entry point
│   ├── crawler.py             # Crawl4Ai-based web scraping
│   ├── extractor.py           # Multi-pass LLM extraction
│   ├── bedrock_client.py      # AWS Bedrock wrapper
│   ├── graph_writer.py        # Neo4j/Neptune writes
│   └── query_api.py           # FastAPI query endpoints
├── config/
│   └── sources.yaml           # Public source configs
├── supabase/
│   └── migrations/            # (Not used — this is graph DB)
├── docs/
│   ├── schema.md              # Graph schema docs
│   └── architecture.md        # System architecture
├── .planning/
│   └── phases/                # GSD phase plans
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── SPEC.md
├── CLAUDE.md
├── OUT_OF_SCOPE.md
└── README.md
```

## How to Run

```bash
pip install -r requirements.txt

# Set AWS credentials for Bedrock
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...

# Run ingestion
python -m src.ingest

# Run query API
uvicorn src.query_api:app --port 8000
```

## Deployment

AWS-native via ECS Fargate:
- ECR for Docker images
- ECS for service orchestration
- S3 for raw document storage
- Neptune or RDS-Neo4j for graph storage
- CloudWatch for observability

## License

Proprietary — built for the founder's AI knowledge graph platform.

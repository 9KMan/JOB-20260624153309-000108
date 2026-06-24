# Phase 3: Architecture

## Phase Goal
Design the system architecture including API, data flow, and integrations.

## Files to Create

```file:src/ingest.py
"""Document ingestion entry point — batch crawl + extract."""
import asyncio
from pathlib import Path
from src.crawler import crawl_sources
from src.extractor import run_extraction_pipeline
from src.graph_writer import write_to_graph

async def ingest():
    sources = Path('config/sources.yaml').read_text()
    docs = await crawl_sources(sources)
    for doc in docs:
        entities = await run_extraction_pipeline(doc)
        await write_to_graph(entities)

if __name__ == '__main__':
    asyncio.run(ingest())
```

```file:src/crawler.py
"""Web crawler using Crawl4Ai + proxy rotation."""
from typing import AsyncIterator
from crawl4ai import AsyncWebCrawler

async def crawl_sources(sources_yaml: str) -> AsyncIterator[dict]:
    """Crawl public sources and yield normalized documents."""
    async with AsyncWebCrawler() as crawler:
        # TODO: parse sources_yaml and crawl each
        yield {}
```

```file:src/extractor.py
"""Multi-pass LLM extraction pipeline."""
from typing import List
from pydantic import BaseModel
from src.bedrock_client import invoke_bedrock

class Entity(BaseModel):
    id: str
    type: str
    name: str
    attributes: dict = {}

class Event(BaseModel):
    id: str
    type: str
    occurred_at: str
    participants: List[str] = []

class Relationship(BaseModel):
    source: str
    target: str
    type: str

async def run_extraction_pipeline(doc: dict) -> dict:
    """Pass 1: entities. Pass 2: events. Pass 3: relationships."""
    text = doc['text']
    entities_prompt = 'Extract entities from: ' + text
    events_prompt = 'Extract events from: ' + text
    rels_prompt = 'Extract relationships from: ' + text
    entities = await invoke_bedrock(entities_prompt)
    events = await invoke_bedrock(events_prompt)
    rels = await invoke_bedrock(rels_prompt)
    return {'entities': entities, 'events': events, 'relationships': rels}
```

```file:src/graph_writer.py
"""Write extracted entities/events/relations to graph DB."""
from neo4j import AsyncGraphDatabase

class GraphWriter:
    def __init__(self, uri: str, user: str, password: str):
        self.driver = AsyncGraphDatabase.driver(uri, auth=(user, password))

    async def write_nodes_and_edges(self, entities, events, rels):
        async with self.driver.session() as session:
            # TODO: implement graph writes
            pass
```

```file:src/bedrock_client.py
"""AWS Bedrock client for LLM calls."""
import boto3

async def invoke_bedrock(prompt: str, model_id: str = 'anthropic.claude-3-sonnet-20240229-v1:0') -> str:
    client = boto3.client('bedrock-runtime', region_name='us-east-1')
    # TODO: invoke model
    return ''
```

```file:config/sources.yaml
sources:
  - name: example_source
    url: https://example.com/feed
    kind: rss
    rate_limit: 100
```

## Done When
- python -m src.ingest runs the pipeline end-to-end
- Crawl4Ai scrapes configured sources
- Multi-pass extraction produces entities/events/relationships
- GraphWriter persists to Neo4j/Neptune

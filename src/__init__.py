python
// src/__init__.py
"""Source package for the AI Knowledge Graph ingestion pipeline.

Modules:
    ingest          - batch ingestion entry point (crawl -> extract -> write)
    crawler         - Crawl4Ai-based web crawler with proxy rotation
    extractor       - multi-pass LLM extraction (entities/events/relationships)
    graph_writer    - Neo4j / Neptune persistence layer
    bedrock_client  - AWS Bedrock async LLM client
"""
__version__ = "0.1.0"


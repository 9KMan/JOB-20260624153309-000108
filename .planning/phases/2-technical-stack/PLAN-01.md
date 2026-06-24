# Phase 2: Technical Stack

## Phase Goal
Select and justify the technology stack, frameworks, and tools.

## Tech Stack
Language:** Python 3.11+, LLM/ML:** AWS Bedrock (Claude), SageMaker, fine-tuning pipelines, Graph DB:** Neo4j or AWS Neptune (Gremlin/Cypher), Data validation:** Pydantic, Web scraping:** Crawl4Ai, Scrapling, proxy rotation, Infrastructure:** AWS (ECS

## Files to Create

```file:requirements.txt
boto3>=1.34.0
langchain>=0.2.0
neo4j>=5.20.0
pydantic>=2.7.0
httpx>=0.27.0
crawl4ai>=0.2.0
scrapling>=0.2.0
pyyaml>=6.0
python-dotenv>=1.0.0
pytest>=8.0
pytest-asyncio>=0.23.0

```

```file:.env.example
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/dbname
SECRET_KEY=***replace-with-random-secret***
```

```file:Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt 2>/dev/null || true
COPY . .
EXPOSE 8000
CMD python -m src.ingest
```

```file:docker-compose.yml
version: '3.9'
services:
  api:
    build: .
    ports: ['8000:8000']
    env_file: .env
    depends_on:
      postgres:
        condition: service_healthy
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: appdb
      POSTGRES_USER: appuser
      POSTGRES_PASSWORD: apppassword
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ['CMD-SHELL', 'pg_isready -U appuser']
      interval: 5s
      timeout: 5s
      retries: 5
volumes:
  pgdata:
```

## Done When
- requirements.txt lists all dependencies
- .env.example documents all environment variables
- Dockerfile builds: docker build .
- docker-compose.yml starts all services: docker compose up

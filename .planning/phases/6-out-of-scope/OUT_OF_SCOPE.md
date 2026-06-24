markdown
// .planning/phases/6-out-of-scope/OUT_OF_SCOPE.md
# Out of Scope

The following items are explicitly NOT included in this build of the AI Knowledge Graph Engineer platform.

## Out of Scope

### Frontend & User-Facing Surfaces
- Full graphical frontend application (the spec covers backend + HITL review endpoints only)
- Mobile applications (iOS / Android) for review or query
- Browser-based knowledge graph visualization (the query API returns data; rendering is a consumer concern)
- White-label / themable UI kits

### Identity, Access & Tenancy
- End-user authentication and authorization flows (the API is assumed to run inside a trusted boundary; callers handle their own auth)
- Multi-tenant isolation, row-level security, or per-tenant data partitioning
- SSO / SAML / OIDC integration with external identity providers
- Fine-grained RBAC for graph entities, properties, or traversal paths
- Per-user API keys, rate limiting policies, or quota enforcement beyond a single global limit

### Data Sources & Ingestion
- Private / paywalled / authenticated document sources (only public sources are in scope)
- Real-time streaming ingestion (e.g., Kafka, Kinesis, webhook-driven pipelines); ingestion is batch-oriented
- Continuous change detection / re-crawl scheduling for sources that mutate
- Source-specific adapters for systems behind bespoke APIs (only generic Crawl4Ai / Scrapling-based crawling is supported)
- OCR for scanned image-only PDFs (text-based PDF / HTML / plain text only)
- Audio, video, or image-as-primary-content ingestion (text-first pipeline only)

### LLM, ML & Models
- Training new foundation models from scratch (only prompting existing Bedrock-hosted models and fine-tuning collectors are in scope)
- On-prem / self-hosted LLM serving (AWS Bedrock is the only supported runtime)
- Custom embedding model training (uses whichever embeddings the chosen Bedrock model exposes)
- Reinforcement learning from human feedback (RLHF) pipelines
- Automatic quality scoring of LLM extractions without human labels

### Graph Database & Storage
- Migration tooling between graph engines (one of Neo4j or Neptune is chosen; the other is not adapted to)
- Cross-cluster / cross-region graph replication
- Graph database backups and point-in-time restore automation (delegated to the chosen engine's managed capabilities)
- Support for property-graph vendors outside the chosen target (no JanusGraph, TigerGraph, ArangoDB, etc.)

### Ontology & Semantics
- A graphical ontology authoring / editing tool (the ontology is treated as a versioned code artifact)
- Automatic ontology discovery or evolution from extracted data (the ontology is fixed per build)
- Reasoning / inference over the graph (e.g., OWL inference, materialised rules); only the persisted graph state is queryable
- Support for non-RDF graph models (no RDF/SPARQL endpoints)

### Operations & Platform
- Multi-cloud deployment (AWS only; no GCP / Azure paths)
- Disaster-recovery runbooks and cross-region failover automation
- Cost-optimisation engines (autoscaling, spot orchestration, intelligent-tiering) beyond sensible defaults
- On-call rotation tooling, paging integrations (PagerDuty / Opsgenie), or incident-management workflows
- Penetration testing, formal security audits, or compliance certifications (SOC2, ISO27001, HIPAA, etc.)

### Integrations & Ecosystem
- Direct connectors to third-party SaaS products (Notion, Confluence, Slack, SharePoint, etc.) as first-class sources
- BI / dashboard tooling (Tableau, Looker, Metabase) for graph analytics
- Outbound webhooks / event publication when graph state changes
- Public SDKs in languages other than Python

## Future Phases

The items below are recognised as valuable follow-on work but are deferred to later iterations:

- **Frontend review console** — purpose-built UI for the HITL workflow, replacing ad-hoc API consumers
- **Authentication & tenancy** — JWT- or OIDC-based auth, per-tenant namespaces, role-based graph access
- **Real-time ingestion** — streaming sources (news wires, RSS, social) with sub-minute end-to-end latency
- **OCR & multimodal ingestion** — scanned documents, charts, figures, audio transcription
- **Additional graph backends** — adapters and parity tests for the non-chosen engine
- **Inference & reasoning layer** — rule engines or OWL-style inference over the persisted graph
- **Ontology authoring tool** — versioned, collaborative editing of the entity / relation schema
- **Graph visualisation** — interactive browser-based traversal and subgraph exploration
- **Cross-region replication & DR** — active-passive or active-active topology with automated failover
- **Fine-tuning pipeline execution** — automated periodic retraining of Bedrock-hosted models from the labeled HITL corpus
- **Outbound integrations** — webhooks, Slack/Teams notifications, and BI tool connectors
- **Compliance & audit** — SOC2 / ISO27001 controls, audit log retention, data-residency options
- **Multi-language document support** — full extraction quality parity across non-English languages
- **SDKs in additional languages** — TypeScript / Go / Java client libraries


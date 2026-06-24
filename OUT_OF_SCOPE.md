# Out of Scope

The following items are explicitly NOT included in this build:

## Out of Scope
- Production AWS deployment (Terraform/CloudFormation)
- Frontend UI (this is a backend pipeline project)
- Multi-tenant isolation beyond RLS basics
- Custom ontology editor (uses founder's existing ontology)
- Mobile ingestion clients
- Real-time streaming ingestion (batch only for Phase 1)

## Future Phases
- Streaming ingestion (Kafka/Kinesis)
- Custom UI for human-in-the-loop review
- Multi-region replication
- Cost optimization for Bedrock calls
- Model distillation for inference

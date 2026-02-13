# Database Contracts

## Files

- `schema.v1.sql`: canonical relational schema for InfraGuard v1.
- `indexes.v1.sql`: performance indexes for query and workflow paths.
- `erd.md`: logical table ownership and relationships.

## Contract Rules

- Treat SQL files as source-of-truth for table/constraint contracts.
- Additive, backward-compatible changes can update v1 files with clear changelog notes.
- Breaking changes require new major version files (example `schema.v2.sql`).

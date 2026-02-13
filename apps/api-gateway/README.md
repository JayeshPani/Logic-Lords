# API Gateway

## Purpose
Unified HTTP API for clients (dashboard, mobile, external systems).

## Responsibilities
- Authentication/authorization facade
- Request validation and routing
- Aggregated read models for UI

## Inputs
- REST/HTTP requests

## Outputs
- JSON responses
- Commands/events forwarded to domain services

## Internal Modules (planned)
- `src/main.py`
- `src/routes/`
- `src/security/`
- `src/dependencies/`

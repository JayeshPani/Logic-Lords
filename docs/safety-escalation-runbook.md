# Safety Escalation Runbook (Management -> Police)

## Overview
InfraGuard enforces a deterministic incident escalation lifecycle:

1. High-risk workflow triggered.
2. Management notified immediately (`email + sms + webhook` fallback strategy).
3. Acknowledgement SLA timer starts (`30 minutes` default).
4. If no acknowledgement arrives by deadline, police is auto-notified (`webhook + sms` fallback).

## Services Involved

- `apps/orchestration-service`
- `apps/notification-service`
- `apps/api-gateway`
- `apps/dashboard-web`

## Startup Order

1. Start Notification Service:
```bash
cd apps/notification-service
python3 -m uvicorn src.main:app --reload --port 8201
```

2. Start Orchestration Service:
```bash
cd apps/orchestration-service
export ORCHESTRATION_NOTIFICATION_BASE_URL="http://127.0.0.1:8201"
export ORCHESTRATION_AUTHORITY_ACK_SLA_MINUTES="30"
python3 -m uvicorn src.main:app --reload --port 8200
```

3. Start API Gateway:
```bash
cd apps/api-gateway
export API_GATEWAY_ORCHESTRATION_BASE_URL="http://127.0.0.1:8200"
python3 -m uvicorn src.main:app --reload --port 8080
```

4. Open Dashboard:
```text
http://127.0.0.1:8080/dashboard
```

## Management ACK Procedure

1. Open the `Automation` tab in dashboard.
2. Find incident in `Awaiting ACK` stage.
3. Click `Acknowledge`.
4. Verify stage transitions to `Acknowledged`.

## Timeout Escalation Verification

1. Trigger a high-risk workflow and do not acknowledge.
2. Wait for SLA deadline to pass.
3. Confirm incident stage transitions to `Police Escalated`.
4. Check notification records in `notification-service` (`GET /dispatches`) for police channel dispatch IDs.

## Notes

- ACK endpoint is idempotent.
- If ACK is sent after police escalation, ACK metadata is still persisted for audit.
- Current runtime state is in-memory and intended for local/dev validation.

# InfraGuard IDs and Enums (v1)

## ID Conventions

- `asset_id`: `asset_<zone>_<type>_<numeric>`
  - Example: `asset_w12_bridge_0042`
- `sensor_id`: `sensor_<asset-short>_<metric>_<numeric>`
  - Example: `sensor_b42_strain_01`
- `ticket_id`: `insp_<yyyyMMdd>_<numeric>`
  - Example: `insp_20260213_0007`
- `maintenance_id`: `mnt_<yyyyMMdd>_<numeric>`
  - Example: `mnt_20260213_0012`

## Canonical Enums

- `severity`: `healthy | watch | warning | critical`
- `priority`: `low | medium | high | critical`
- `inspection_status`: `open | assigned | in_progress | completed | cancelled`
- `maintenance_status`: `planned | active | completed | verified | failed`
- `verification_status`: `pending | submitted | confirmed | failed`
- `notification_channel`: `email | sms | webhook | chat`

## Versioning Rules

- Additive changes: retain same major (`v1` -> `v1`).
- Breaking changes: increment major (`v1` -> `v2`) and publish new schema file version.
- Producers and consumers must declare supported versions explicitly.

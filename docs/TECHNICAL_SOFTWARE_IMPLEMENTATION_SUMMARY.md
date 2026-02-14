# InfraGuard Technical Software Implementation Summary

Date: 2026-02-14  
Repository root: `Cental Hack`

## 1. Scope of Analysis

This summary was derived from code and docs across:

- `apps/`
- `services/`
- `data-platform/`
- `contracts/`
- `blockchain/`
- `firmware/`
- `agents/`
- `infra/`
- `tests/`
- `scripts/`

It includes:

- Implemented software modules and runtime responsibilities
- All project algorithms and formulas currently present in source code
- Thresholds, model configs, and deterministic logic used in production/test flows

## 2. High-Level Technical Implementation

InfraGuard is implemented as a contract-first, event-driven platform:

1. Telemetry acquisition via ESP32 + Firebase (`firmware/`, `apps/sensor-ingestion-service`)
2. API and telemetry normalization (`apps/sensor-ingestion-service`, `apps/api-gateway`)
3. AI pipeline (`services/lstm-forecast-service`, `services/anomaly-detection-service`, `services/fuzzy-inference-service`, `services/health-score-service`)
4. Autonomous workflow orchestration (`apps/orchestration-service`, `agents/openclaw-agent`)
5. Report/evidence generation (`services/report-generation-service`)
6. Notification dispatch (`apps/notification-service`)
7. Blockchain anchoring + confirmation tracking (`services/blockchain-verification-service`, `blockchain/contracts`)
8. Operator visualization and interaction (`apps/dashboard-web`)
9. Storage/streaming foundations (`contracts/database`, `data-platform/storage`, `data-platform/streaming`)
10. Offline ML lifecycle (`data-platform/ml`)

## 3. Module-by-Module Implementation Summary

### 3.1 Contracts Layer

- API contract in `contracts/api/openapi.yaml` (OpenAPI 3.1)
- Event and command envelope schemas in `contracts/core/`
- Domain event schemas in `contracts/events/`
- Command schemas in `contracts/commands/`
- ML request/response schemas in `contracts/ml/`
- Database schema/index contracts in `contracts/database/schema.v1.sql` and `contracts/database/indexes.v1.sql`

Key implementation characteristics:

- Strong shape/range/pattern validation (IDs, hashes, [0,1] bounded scores, enum-based states)
- Fixed event and command versioning pattern (`vN`)
- SQL-level constraints, regex checks, and relational integrity guarantees

### 3.2 Applications (`apps/`)

#### `apps/sensor-ingestion-service`

- Firebase-backed telemetry fetch + ingest
- Computes derived engineering metrics from DHT11 + accelerometer payloads
- Exposes live normalized snapshot endpoint

#### `apps/api-gateway`

- Unified boundary API
- Bearer auth and fixed-window in-memory rate limiting
- Proxies telemetry and blockchain-connect paths to downstream services
- Uses in-memory read model for local/dev module validation

#### `apps/dashboard-web`

- Browser app split into transport (`src/api.js`), state derivation (`src/state.js`), and rendering (`src/visualization.js`)
- Live mode + graceful fallback synthetic data
- Risk chart, gauge, city map (Leaflet + fallback renderer), telemetry cards, blockchain connect, MetaMask connect

#### `apps/orchestration-service`

- Consumes risk/forecast events
- Applies threshold-based workflow trigger logic
- Generates inspection commands/events
- Supports retry and maintenance completion state transitions

#### `apps/notification-service`

- Renders severity-aware templates
- Retries failed channel attempts
- Fallback channel sequence routing
- Emits delivery status event payloads

### 3.3 Services (`services/`)

#### `services/asset-registry-service`

- SQLAlchemy-based asset + sensor registry
- CRUD, status transitions, sensor mapping, filtering, pagination

#### `services/lstm-forecast-service`

- Forecast inference pipeline with:
  - normalization to [0,1]
  - 48h sequence window builder
  - predictor factory (`surrogate`, `keras`, `torch`)
- Runtime fallback to surrogate predictor on startup/model errors (configurable)

#### `services/anomaly-detection-service`

- Isolation Forest runtime with optional pre-trained artifact loading
- Heuristic fallback scoring when model/runtime unavailable
- Emits anomaly score/flag and detector mode

#### `services/fuzzy-inference-service`

- Mamdani fuzzy inference with 15-rule base
- Triangular/trapezoidal membership functions
- Centroid defuzzification over configurable sampling resolution

#### `services/health-score-service`

- Final output composer:
  - clamps risk score
  - maps risk bands to labels
  - produces canonical output payload

#### `services/report-generation-service`

- Stores inspection + maintenance context events
- Generates deterministic evidence bundles
- Computes SHA-256 evidence hash
- Emits report event and blockchain verification command

#### `services/blockchain-verification-service`

- Creates deterministic tx hash from command payload
- Tracks confirmations until configured threshold
- Emits blockchain verification event when confirmed
- Includes Sepolia JSON-RPC connectivity checks with fallback endpoint list

#### `services/external-context-service`

- Placeholder entrypoint only (`src/main.py`), no implemented runtime logic yet

### 3.4 Data Platform (`data-platform/`)

#### Storage

- PostgreSQL runtime bootstrap (`data-platform/storage/migrations/001_storage_runtime.sql`)
- Contract schema + indexes applied by scripts
- Migration bookkeeping table (`schema_migrations`)

#### Streaming

- Outbox trigger via `pg_notify`
- dequeue/mark-failed functions in `data-platform/streaming/migrations/001_outbox_runtime.sql`
- CLI scripts for enqueue/dispatch runtime operations

#### ML

- Dataset adapters and canonical mapping scripts in `scripts/`
- Offline training scripts for LSTM and Isolation Forest
- Offline evaluation/backtesting and threshold calibration scripts
- Model + metadata artifacts in `data-platform/ml/models/`
- Reports in `data-platform/ml/reports/`

### 3.5 Blockchain

- Solidity contract `blockchain/contracts/InfraGuardVerification.sol`:
  - stores maintenance verification records by `maintenanceId`
  - emits `MaintenanceVerified` events
- Foundry-based deployment workflow (no Hardhat)

### 3.6 Firmware

- ESP32 firmware (`firmware/esp32/firebase_dht11_mpu6050/esp32_firebase_dht11_mpu6050.ino`)
- Reads DHT11 + MPU6050
- Converts raw accelerometer units to g
- Pushes telemetry to Firebase `latest` and `history`

### 3.7 Agents

- OpenClaw workflows in `agents/openclaw-agent/workflows/`
- Declarative guards/retries/schedules for orchestration policies

### 3.8 Testing and Quality Gates

- Contract tests (`tests/contract`)
- Integration tests (`tests/integration`)
- End-to-end workflows (`tests/e2e`)
- Performance smoke tests (`tests/performance`)
- Makefile module gates (`module4-check` ... `module15-check`) and AI step gates (`ai-step2`, `ai-step3`, `ai-check`)

## 4. Algorithms and Formulas Used

This section lists the implemented formulas and algorithms with source references.

### 4.1 Forecast Normalization and Sequence Construction

Source:

- `services/lstm-forecast-service/src/lstm_forecast/preprocessing.py`
- `services/lstm-forecast-service/src/lstm_forecast/config.py`

Formulas:

- Min-max scaling:  
  `scaled = (value - lower) / (upper - lower)`
- Clamp to unit interval:  
  `normalized = max(0, min(1, scaled))`
- Per-feature bounds:
  - strain: `[0, 2000]`
  - vibration: `[0, 10]`
  - temperature: `[-20, 80]`
  - humidity: `[0, 100]`
- 48h window cutoff:  
  `cutoff_ts = latest_ts - history_window_hours`
- Minimum sequence guard:  
  `len(windowed_points) >= min_sequence_points` (default 16)

### 4.2 Surrogate Forecast Probability (Fallback Predictor)

Source:

- `services/lstm-forecast-service/src/lstm_forecast/predictor.py`

Formulas:

- Latest-state risk:
  - `latest_risk = 0.35*strain + 0.30*vibration + 0.20*temperature + 0.15*humidity`
- Trend slope per feature:
  - `slope_i = abs(latest_i - first_i) / max(1, n-1)`
- Trend risk:
  - `trend_risk = 0.35*slope_strain + 0.30*slope_vibration + 0.20*slope_temperature + 0.15*slope_humidity`
- Final probability:
  - `p = clamp(0.75*latest_risk + 0.25*trend_risk)`
- Confidence heuristic:
  - `confidence = clamp(0.45 + 0.01*n_points)`

### 4.3 Trained LSTM Model Architecture and Training

Source:

- `services/lstm-forecast-service/src/lstm_forecast/predictor.py`
- `data-platform/ml/training/train_lstm_torch.py`

Architecture:

- `Input -> LSTM(64) -> Dropout(0.2) -> LSTM(32) -> Dense(16, ReLU) -> Dense(1, Sigmoid)`

Training pipeline:

- Time resampling to 10-min intervals + interpolation
- Chronological split: 70% train / 15% val / 15% test
- Sequence target index:
  - `target_idx = seq_end + horizon_steps - 1`
- Target clipping:
  - `y = clip(y, 0, 1)`
- Loss:
  - `MSELoss`
- Optimizer:
  - `Adam(lr=1e-3 default)`

### 4.4 Anomaly Detection: Isolation Forest + Heuristic Fallback

Source:

- `services/anomaly-detection-service/src/anomaly_detection/engine.py`
- `services/anomaly-detection-service/src/anomaly_detection/config.py`
- `data-platform/ml/training/train_isolation_forest.py`

Isolation Forest config:

- `n_estimators=100`
- `contamination=0.02`
- `random_state=42`

Score normalization:

- If calibration range unavailable:
  - `score = clamp(sigmoid(-5 * decision_function))`
- Else:
  - `score = clamp((decision_max - decision) / (decision_max - decision_min))`

Anomaly flag:

- `anomaly_flag = 1 if score >= anomaly_threshold else 0`  
  default `anomaly_threshold = 0.65`

Heuristic fallback formulas:

- Baseline-free weighted score:
  - `base_score = 0.35*strain + 0.35*vibration + 0.15*temperature + 0.15*humidity`
- Feature z-like deviation:
  - if `std <= 1e-6`: `z = abs(current - mean)`
  - else: `z = abs(current - mean) / std`
  - normalized: `z_norm = min(z, 6) / 6`
- Aggregate deviation:
  - `deviation = mean(z_norm across features)`
- Final heuristic anomaly score:
  - `score = clamp(0.45*base_score + 0.55*deviation)`

### 4.5 Fuzzy Inference (Mamdani + Centroid)

Source:

- `services/fuzzy-inference-service/src/fuzzy_inference/engine.py`
- `services/fuzzy-inference-service/src/fuzzy_inference/config.py`

Membership function formulas:

- Triangular:
  - piecewise linear rise/fall over `(a,b,c)`
- Trapezoidal:
  - piecewise ramp/plateau over `(a,b,c,d)`

Inference algorithm:

1. Fuzzification of 7 inputs: strain, vibration, temperature, rainfall, traffic, failure_probability, anomaly_score
2. Rule activation:
  - `activation(rule) = min(antecedent_memberships)`
3. Output clipping:
  - `mu_clipped(x) = min(activation, output_membership(x))`
4. Aggregation:
  - `mu_agg(x) = max(mu_agg(x), mu_clipped(x))`
5. Defuzzification (centroid):
  - `centroid = sum(x * mu_agg(x)) / sum(mu_agg(x))`
  - sampled over `centroid_resolution` points (default 401)

Risk band mapping:

- `<=0.2` Very Low
- `<=0.4` Low
- `<=0.6` Moderate
- `<=0.8` High
- `>0.8` Critical

Fuzzy event anomaly flag derivation:

- `anomaly_flag = 1 if anomaly_score >= FUZZY_ANOMALY_FLAG_THRESHOLD else 0`  
  default threshold `0.7`

### 4.6 Health Score Composition

Source:

- `services/health-score-service/src/health_score/engine.py`

Formulas:

- `health_score = clamp(final_risk_score)` then rounded to 4 decimals
- Same risk band mapping as fuzzy engine

### 4.7 Sensor Ingestion Engineering Formulas

Source:

- `apps/sensor-ingestion-service/src/main.py`

Formulas:

- Acceleration magnitude (g):
  - `a_mag = sqrt(x_g^2 + y_g^2 + z_g^2)`
- Vibration proxy (m/s^2):
  - `vibration_ms2 = abs(a_mag - 1.0) * 9.80665`
- Tilt angle:
  - `tilt_deg = degrees(acos(clamp(z_g / max(a_mag, 0.0001), -1, 1)))`
- Strain proxy:
  - `strain_proxy = vibration_ms2 * 16.0`
- Thermal stress index:
  - `thermal = clamp(((temp - 24)/16) + max(0, (humidity - 60)/120), 0, 1)`
- Fatigue index:
  - `fatigue = clamp(vibration_ms2 / 6.5, 0, 1)`
- Tilt penalty:
  - `tilt_penalty = clamp(tilt_deg / 45, 0, 1)`
- Health proxy:
  - `health_proxy = clamp(1 - (0.45*thermal + 0.45*fatigue + 0.10*tilt_penalty), 0, 1)`
- Delta presentation:
  - `delta = latest_sample - previous_sample`

### 4.8 Firmware Sensor Conversion

Source:

- `firmware/esp32/firebase_dht11_mpu6050/esp32_firebase_dht11_mpu6050.ino`

Formula:

- MPU6050 raw to g:
  - `x_g = ax_raw / 16384`
  - `y_g = ay_raw / 16384`
  - `z_g = az_raw / 16384`

### 4.9 Dataset Canonicalization Formulas

Source:

- `scripts/dataset_adapters.py`

Bridge dataset:

- `vibration_rms = sqrt(ax^2 + ay^2 + az^2)`
- `strain_value = clamp(fft_magnitude * 700, 0, 2500)`

Digital twin dataset:

- `traffic_density = clamp(Traffic_Volume_vph / 2000, 0, 1)`

Bearing dataset:

- `vibration_rms = mean(abs(Bearing1..Bearing4))`
- `strain_value = clamp(vibration_rms * 1500, 0, 2500)`

### 4.10 Offline Evaluation Metrics and Calibration

Source:

- `data-platform/ml/evaluation/common.py`
- `data-platform/ml/evaluation/evaluate_lstm_torch.py`
- `data-platform/ml/evaluation/evaluate_isolation_forest.py`

Regression metrics:

- `MSE = mean((y_pred - y_true)^2)`
- `RMSE = sqrt(MSE)`
- `MAE = mean(abs(y_pred - y_true))`
- `MAPE = mean(abs(y_pred - y_true)/max(abs(y_true),1e-6)) * 100`
- `R2 = 1 - SS_res/SS_tot`

Binary metrics:

- `accuracy = (TP + TN) / N`
- `precision = TP / (TP + FP)`
- `recall = TP / (TP + FN)`
- `F1 = 2*precision*recall / (precision + recall)`

Threshold sweep:

- Predict positive when `score >= threshold`
- Best threshold selection objective:
  1. Max F1
  2. Tie-break by higher accuracy
  3. Then higher recall
  4. Then higher precision

LSTM event-aware split algorithm:

- Searches train/val boundaries satisfying:
  - minimum train/val/test ratios
  - minimum proxy event count in val/test
- Optimizes boundary cost:
  - `cost = |train_end - 70%| + |val_end - 85%|`

Proxy-label rules:

- LSTM evaluation:
  - positive if any of:
    - `Maintenance_Alert`
    - `Flood_Event_Flag`
    - `High_Winds_Storms`
    - `Abnormal_Traffic_Load_Surges`
- Isolation evaluation (digital twin):
  - above event ORs plus `Anomaly_Detection_Score >= threshold` (default 0.7)
- Isolation evaluation (bridge):
  - `structural_condition >= threshold` (default 2)

### 4.11 API Gateway Control Algorithms

Source:

- `apps/api-gateway/src/api_gateway/security.py`
- `apps/api-gateway/src/api_gateway/routes.py`

Rate limiting:

- Fixed-window in-memory algorithm per key (`token` or `ip`)
- For each request:
  - drop timestamps `<= now - window_seconds`
  - deny if `len(bucket) >= limit`
  - else append current timestamp and allow

Pagination:

- `total_pages = ceil(total_items / page_size)` implemented as:
  - `(total_items + page_size - 1) // page_size`

### 4.12 Orchestration Decision and Priority Algorithms

Source:

- `apps/orchestration-service/src/orchestration_service/engine.py`

Effective failure probability:

- `effective_fp = max(risk_event_fp, latest_forecast_fp_if_available)`

Trigger conditions (OR logic):

- risk level in configured set (`High`, `Critical`)
- health score >= configured minimum (`0.70`)
- effective failure probability >= configured minimum (`0.60`)
- anomaly flag set with risk in `{Moderate, High, Critical}`

Priority mapping:

- `critical` if risk=`Critical` OR `effective_fp >= 0.85`
- `high` if risk=`High` OR `effective_fp >= 0.70`
- `medium` if risk=`Moderate`
- else `low`

Retry loop:

- Up to `max_retry_attempts` (default 3) for inspection command dispatch

### 4.13 Notification Retry/Fallback Algorithms

Source:

- `apps/notification-service/src/notification_service/engine.py`
- `apps/notification-service/src/notification_service/templates.py`

Channel sequence construction:

- `sequence = [primary] + fallback_channels(excluding duplicates) + remaining_channels`

Dispatch algorithm:

- For each channel in sequence:
  - attempt `1..max_retry_attempts` (default 3)
  - on success: stop
  - on failure after retries: continue to next channel

Fallback tracking:

- `fallback_used = true` when dispatcher moves past first channel

Template rendering:

- Severity-keyed format string with safe context substitution, output trimmed to 2000 chars

### 4.14 Deterministic Evidence and Blockchain Hashing

Source:

- `services/report-generation-service/src/report_generation/engine.py`
- `services/blockchain-verification-service/src/blockchain_verification/engine.py`

Evidence hash:

- Build canonical JSON of:
  - report command payload
  - maintenance context event
  - optional inspection event
  - `generated_at`
- Serialize with sorted keys and compact separators
- `evidence_hash = "0x" + sha256(canonical_json)`

Transaction hash:

- Canonical JSON from verification command fields:
  - `maintenance_id`, `asset_id`, `evidence_hash`, `network`, `contract_address`, `chain_id`, `command_id`
- `tx_hash = "0x" + sha256(canonical_json)`

Deterministic block number projection:

- `seed = int(tx_hash[2:10], 16)`
- `block_number = initial_block_number + (seed % 50000)`

Fallback hash:

- `fallback_tx_hash = "0x" + sha256(maintenance_id)`

Confirmation tracking:

- Each `/track` increments confirmation count by 1
- Status becomes `confirmed` when `confirmations >= required_confirmations` (default 3)

### 4.15 Sepolia Connectivity Selection Algorithm

Source:

- `services/blockchain-verification-service/src/blockchain_verification/engine.py`
- `services/blockchain-verification-service/src/blockchain_verification/sepolia_rpc.py`

Algorithm:

1. Build deduplicated endpoint list: primary + CSV fallbacks
2. Iterate endpoints in order
3. For each endpoint:
  - call `eth_chainId`
  - call `eth_blockNumber`
  - reject endpoint if chain ID mismatch
4. Select first endpoint that matches expected Sepolia chain (`11155111`)
5. Optional contract deployment check:
  - `eth_getCode`, considered deployed iff code not in `{0x,0x0,0x00}`

### 4.16 Streaming Outbox Runtime Algorithms

Source:

- `data-platform/streaming/migrations/001_outbox_runtime.sql`

Outbox dequeue:

- Select pending events with `next_attempt_at <= now()`
- Order by oldest (`created_at ASC`)
- Limit by batch size
- Lock with `FOR UPDATE SKIP LOCKED`
- Mark selected rows as `published` and stamp `published_at`

Failure marking:

- `retry_count = retry_count + 1`
- `next_attempt_at = now() + retry_delay_seconds`

Notify trigger:

- On insert, publish JSON payload to channel `infraguard_outbox` via `pg_notify`

### 4.17 Dashboard Client-Side Algorithms

Source:

- `apps/dashboard-web/src/config.js`
- `apps/dashboard-web/src/state.js`
- `apps/dashboard-web/src/api.js`
- `apps/dashboard-web/src/visualization.js`

Severity thresholds:

- watch `>= 0.35`
- warning `>= 0.60`
- critical `>= 0.80`

Overview aggregates:

- `overallHealth = mean(asset.healthScore)`
- `systemFailureRisk = max(asset.failureProbability72h)`
- assets sorted by:
  1. failure probability descending
  2. severity order
  3. assetId lexical

Synthetic forecast (fallback):

- For each hour in `0..72` step 8:
  - `wave = sin(hour / 12) * 0.07`
  - `drift = (hour / 72) * 0.16`
  - `p = clamp(base - 0.08 + wave + drift)`

Map marker sizing:

- `radius = markerMinRadius + (markerMaxRadius - markerMinRadius) * probability`

Fallback map coordinates:

- `xRatio = (lon - minLon) / max(0.0001, maxLon - minLon)`
- `yRatio = (lat - minLat) / max(0.0001, maxLat - minLat)`

Gauge rendering:

- `circumference = 2*pi*r`
- `strokeDashoffset = circumference * (1 - score)`

### 4.18 Test/Performance Calculation Logic

Source:

- `tests/performance/test_service_latency_smoke.py`

p95 calculation:

- sort latencies
- index:
  - `round(0.95 * (n - 1))`
- p95 value = element at computed index

Performance acceptance thresholds:

- health `/compose` p95 < 120ms, mean < 80ms
- notification `/dispatch` p95 < 150ms, mean < 90ms

## 5. Current Implementation Notes

- `services/external-context-service` is intentionally a placeholder, not yet implemented.
- Most runtime module stores are in-memory by design for local module validation.
- Contracts and tests enforce shape, range, and envelope consistency across all services.
- AI training/evaluation is offline; services perform inference only.


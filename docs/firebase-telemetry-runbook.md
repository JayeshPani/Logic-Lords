# Firebase Telemetry Runbook (ESP32 DHT11 + Accelerometer)

## 1. Create Firebase Realtime Database
1. In Firebase Console, create/select your project.
2. Open **Build -> Realtime Database** and create database.
3. Note your DB URL, e.g.:
   - `https://<project-id>-default-rtdb.firebaseio.com`

## 2. Configure Realtime Database Rules (Dev)
For local prototype testing, use permissive rules first:

```json
{
  "rules": {
    ".read": true,
    ".write": true
  }
}
```

For production, switch to authenticated rules and set `SENSOR_INGESTION_FIREBASE_AUTH_TOKEN`.

## 3. Flash ESP32 Firmware
1. Open:
   - `firmware/esp32/firebase_dht11_mpu6050/esp32_firebase_dht11_mpu6050.ino`
2. Set:
   - WiFi SSID/password
   - `FIREBASE_DB_URL`
   - optional `FIREBASE_AUTH_TOKEN`
   - `ASSET_ID` mapped to one dashboard asset
3. Upload to ESP32.
4. Confirm serial logs show successful `PUT latest` + `POST history`.

## 4. Start Sensor Ingestion Service
```bash
cd apps/sensor-ingestion-service
export SENSOR_INGESTION_FIREBASE_DB_URL="https://<project-id>-default-rtdb.firebaseio.com"
# export SENSOR_INGESTION_FIREBASE_AUTH_TOKEN="<optional-token>"
python3 -m uvicorn src.main:app --reload --port 8100
```

## 5. Start API Gateway (Telemetry Proxy Enabled)
```bash
cd apps/api-gateway
export API_GATEWAY_SENSOR_INGESTION_BASE_URL="http://127.0.0.1:8100"
python3 -m uvicorn src.main:app --reload --port 8090
```

## 6. Verify Live Data Path
1. Sensor service direct:
```bash
curl -sS http://127.0.0.1:8100/telemetry/assets/asset_w12_bridge_0042/latest
```

2. Gateway proxy:
```bash
curl -sS http://127.0.0.1:8090/telemetry/asset_w12_bridge_0042/latest \
  -H "Authorization: Bearer dev-token"
```

3. Dashboard:
   - Open `http://127.0.0.1:8090/dashboard`
   - Sensor cards should use live telemetry when available.

## 7. Expected Firebase Structure
```
infraguard/
  telemetry/
    <asset_id>/
      latest: { ...reading... }
      history/
        -Nxxxx: { ...reading... }
        -Nyyyy: { ...reading... }
```

## Notes
- Computations are performed in `apps/sensor-ingestion-service/src/main.py`:
  - vibration proxy, tilt, strain proxy, thermal/fatigue indexes, health proxy score.
- Dashboard falls back to synthetic telemetry if live endpoint is unavailable.

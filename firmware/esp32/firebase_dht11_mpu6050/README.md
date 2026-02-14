# ESP32 -> Firebase (DHT11 + MPU6050)

This sketch pushes sensor data to Firebase Realtime Database in the format expected by `apps/sensor-ingestion-service`.

## Hardware
- ESP32
- DHT11 sensor (default pin: `GPIO4`)
- MPU6050 accelerometer (I2C)

## Arduino Libraries
- `DHT sensor library` by Adafruit
- `MPU6050` (common Arduino MPU6050 library)

## Configuration
Edit constants in `esp32_firebase_dht11_mpu6050.ino`:
- `WIFI_SSID`
- `WIFI_PASSWORD`
- `FIREBASE_DB_URL`
- `FIREBASE_AUTH_TOKEN` (optional)
- `ASSET_ID`
- `DEVICE_ID`

## Firebase Paths Written
- `/<prefix>/telemetry/<asset_id>/latest`
- `/<prefix>/telemetry/<asset_id>/history/<push-id>`

Where `<prefix>` defaults to `infraguard`.

## Payload Shape
```json
{
  "device_id": "esp32-node-01",
  "captured_at": "2026-02-14T12:30:00Z",
  "firmware_version": "1.0.0",
  "dht11": {
    "temperature_c": 28.4,
    "humidity_pct": 61.2
  },
  "accelerometer": {
    "x_g": 0.02,
    "y_g": -0.01,
    "z_g": 0.98
  }
}
```

## Notes
- The sketch uses HTTPS with `client.setInsecure()` for quick prototyping.
- For production, add certificate pinning/CA validation.

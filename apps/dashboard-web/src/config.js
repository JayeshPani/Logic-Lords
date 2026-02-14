export const DASHBOARD_CONFIG = Object.freeze({
  refreshIntervalMs: 15000,
  clockIntervalMs: 1000,
  requestTimeoutMs: 8000,
  authToken: "dev-token",
  commandCenter: "METRO-NORTH_UNIT_04",
  maintenanceIdFallback: "mnt_20260214_0012",
  weather: {
    temperatureC: 24,
    humidityPct: 62,
    windKmh: 12,
    windDirection: "NW",
  },
});

export const RISK_COLOR_BY_LEVEL = Object.freeze({
  "Very Low": "#00ff88",
  Low: "#00ff88",
  Moderate: "#facc15",
  High: "#fb923c",
  Critical: "#f43f5e",
});

export const SEVERITY_COLOR = Object.freeze({
  healthy: "#00ff88",
  watch: "#facc15",
  warning: "#fb923c",
  critical: "#f43f5e",
});

export const CHART_THRESHOLDS = Object.freeze({
  watch: 0.35,
  warning: 0.6,
  critical: 0.8,
});

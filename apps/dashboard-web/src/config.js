const SERVER_CONFIG = globalThis.__INFRAGUARD_DASHBOARD_CONFIG__ || {};
const SERVER_FIREBASE = SERVER_CONFIG.firebase || {};

export const DASHBOARD_CONFIG = Object.freeze({
  refreshIntervalMs: 30000,
  clockIntervalMs: 1000,
  requestTimeoutMs: 10000,
  authToken: "dev-token",
  commandCenter: "METRO-NORTH_UNIT_04",
  maintenanceIdFallback: "mnt_20260214_0012",
  firebase: Object.freeze({
    enabled: Boolean(SERVER_FIREBASE.enabled),
    dbUrl: String(SERVER_FIREBASE.dbUrl || "").trim(),
    basePath: String(SERVER_FIREBASE.basePath || "infraguard/telemetry").trim() || "infraguard/telemetry",
  }),
});

export const MAP_CONFIG = Object.freeze({
  leafletCssUrl: "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css",
  leafletJsUrl: "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js",
  osmTileUrl: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
  osmAttribution:
    "&copy; <a href='https://www.openstreetmap.org/copyright' target='_blank' rel='noopener noreferrer'>OpenStreetMap</a> contributors",
  defaultCenter: Object.freeze([19.076, 72.8777]),
  defaultZoom: 12,
  minZoom: 10,
  maxZoom: 18,
  markerMinRadius: 6,
  markerMaxRadius: 22,
  leafletLoadTimeoutMs: 12000,
});

export const CHART_THRESHOLDS = Object.freeze({
  watch: 0.35,
  warning: 0.6,
  critical: 0.8,
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

export const SEVERITY_ORDER = Object.freeze({
  healthy: 0,
  watch: 1,
  warning: 2,
  critical: 3,
});

export const UI_ERROR_HINTS = Object.freeze({
  TIMEOUT: "Request timed out. Retry or check network reachability.",
  UNAUTHORIZED: "Gateway authorization failed. Verify auth token.",
  FORBIDDEN: "Access denied by gateway policy.",
  BLOCKCHAIN_TIMEOUT: "Blockchain service timed out. Retry shortly.",
  BLOCKCHAIN_UNAVAILABLE: "Blockchain service is unreachable.",
});

import { DASHBOARD_CONFIG } from "./config.js";
import { MOCK_DATA } from "./mock-data.js";
import { emptyWalletStatus } from "./wallet.js";

class DashboardApiError extends Error {
  constructor({ code, message, endpoint, status = null, details = null }) {
    super(message);
    this.name = "DashboardApiError";
    this.code = code;
    this.endpoint = endpoint;
    this.status = status;
    this.details = details;
  }
}

const FIREBASE_CONFIG_STORAGE_KEY = "infraguard.firebase.nodes.config.v1";
const DASHBOARD_FIREBASE_DEFAULTS = DASHBOARD_CONFIG.firebase || {};
const FIREBASE_DEFAULT_CONFIG = Object.freeze({
  enabled: Boolean(DASHBOARD_FIREBASE_DEFAULTS.enabled),
  dbUrl: normalizeFirebaseDbUrl(DASHBOARD_FIREBASE_DEFAULTS.dbUrl),
  basePath: normalizeFirebaseBasePath(DASHBOARD_FIREBASE_DEFAULTS.basePath || "infraguard/telemetry"),
  authToken: "",
});
let telemetryBackoffUntilMs = 0;
let gatewayRateLimitUntilMs = 0;
let verificationEndpointBackoffUntilMs = 0;
let evidenceEndpointBackoffUntilMs = 0;
let lstmEndpointBackoffUntilMs = 0;
let dashboardRefreshCycle = 0;

const OPTIONAL_ENDPOINT_COOLDOWN_MS = 5 * 60 * 1000;
const DEFAULT_GATEWAY_RETRY_MS = 60 * 1000;
const TELEMETRY_UPSTREAM_COOLDOWN_MS = 5 * 60 * 1000;
const HEALTH_REFRESH_EVERY_CYCLES = 2;
const FORECAST_REFRESH_EVERY_CYCLES = 3;
const TELEMETRY_REFRESH_EVERY_CYCLES = 3;
const AUTOMATION_REFRESH_EVERY_CYCLES = 2;
const LSTM_REFRESH_EVERY_CYCLES = 2;

function clamp01(value) {
  return Math.max(0, Math.min(1, Number(value ?? 0)));
}

function safeIso(value) {
  const date = new Date(value ?? "");
  if (Number.isNaN(date.getTime())) {
    return new Date().toISOString();
  }
  return date.toISOString();
}

function normalizeFirebaseDbUrl(dbUrl) {
  return String(dbUrl || "").trim().replace(/\/+$/, "");
}

function normalizeFirebaseBasePath(basePath) {
  const cleaned = String(basePath || "").trim().replace(/^\/+/, "").replace(/\/+$/, "");
  return cleaned || FIREBASE_DEFAULT_CONFIG.basePath;
}

function encodeFirebasePath(path) {
  return path
    .split("/")
    .map((segment) => encodeURIComponent(segment))
    .join("/");
}

function parseFirebaseNumber(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function firstFinite(...values) {
  for (const value of values) {
    const numeric = parseFirebaseNumber(value);
    if (numeric !== null) {
      return numeric;
    }
  }
  return null;
}

function parseFirebaseCoordinates(latest) {
  const location = latest?.location || {};
  const lat = firstFinite(location.lat, location.latitude, latest?.lat, latest?.latitude);
  const lon = firstFinite(location.lon, location.lng, location.longitude, latest?.lon, latest?.lng, latest?.longitude);
  if (lat === null || lon === null) {
    return null;
  }
  return { lat, lon };
}

function toIsoFromLatest(latest) {
  const candidates = [
    latest?.captured_at,
    latest?.evaluated_at,
    latest?.timestamp,
    latest?.recorded_at,
    latest?.created_at,
    latest?.updated_at,
  ];
  for (const value of candidates) {
    if (value) {
      return safeIso(value);
    }
  }
  return new Date().toISOString();
}

function parseFirebaseSensorTelemetry(latest) {
  const buildMetric = (candidate, fallbackUnit, precision, label) => {
    const numeric =
      typeof candidate === "object" && candidate !== null
        ? firstFinite(candidate.value)
        : firstFinite(candidate);
    if (numeric === null) {
      return null;
    }
    const value = Number(numeric.toFixed(precision));
    const samplesCandidate =
      typeof candidate === "object" && candidate !== null && Array.isArray(candidate.samples)
        ? candidate.samples
        : [value];
    const samples = samplesCandidate
      .map((sample) => parseFirebaseNumber(sample))
      .filter((sample) => sample !== null)
      .map((sample) => Number(sample.toFixed(precision)));
    return {
      value,
      unit:
        typeof candidate === "object" && candidate !== null && typeof candidate.unit === "string"
          ? candidate.unit
          : fallbackUnit,
      delta: `live ${label}`,
      samples: samples.length ? samples : [value],
    };
  };

  const strain = buildMetric(
    latest?.sensors?.strain ?? latest?.strain ?? latest?.strain_me,
    "me",
    1,
    "variance",
  );
  const vibration = buildMetric(
    latest?.sensors?.vibration ?? latest?.vibration ?? latest?.vibration_mms,
    "mm/s",
    1,
    "trend",
  );
  const temperature = buildMetric(
    latest?.sensors?.temperature ?? latest?.temperature ?? latest?.temperature_c,
    "C",
    1,
    "spike",
  );
  const tilt = buildMetric(
    latest?.sensors?.tilt ?? latest?.tilt ?? latest?.tilt_deg,
    "deg",
    2,
    "drift",
  );

  return {
    strain,
    vibration,
    temperature,
    tilt,
  };
}

function parseFirebaseNode(nodeId, nodeValue) {
  if (nodeValue === null || typeof nodeValue !== "object") {
    return null;
  }
  const latest = nodeValue.latest && typeof nodeValue.latest === "object" ? nodeValue.latest : nodeValue;
  const assetId = String(
    latest.asset_id || latest.assetId || latest.device_id || latest.deviceId || nodeId,
  );
  const nodeZone = String(latest.zone || latest.region || latest.country || "global").toLowerCase();
  const location = parseFirebaseCoordinates(latest);
  const latestAt = toIsoFromLatest(latest);
  const telemetry = parseFirebaseSensorTelemetry(latest);
  const historyCount = nodeValue.history && typeof nodeValue.history === "object"
    ? Object.keys(nodeValue.history).length
    : 0;
  const failureProbability = clamp01(
    firstFinite(latest.failure_probability_72h, latest.failureProbability72h, latest.risk_probability) ?? 0,
  );
  const healthScore = clamp01(
    firstFinite(latest.health_score, latest.healthScore, 1 - failureProbability) ?? (1 - failureProbability),
  );

  return {
    nodeId: String(nodeId),
    assetId,
    assetName: String(latest.asset_name || latest.assetName || assetId),
    zone: nodeZone,
    location,
    latestAt,
    telemetry,
    historyCount,
    failureProbability72h: failureProbability,
    healthScore,
    rawLatest: latest,
  };
}

function createFirebaseDisconnectedState(config, message) {
  return {
    ...config,
    connected: false,
    lastFetchedAt: null,
    nodes: [],
    mappedNodes: 0,
    totalNodes: 0,
    message,
    errorCode: null,
  };
}

function mergeFirebaseIntoPayload(payload, firebaseState) {
  const merged = {
    ...payload,
    firebaseNodes: firebaseState,
  };

  const existingIds = new Set((payload.assets || []).map((asset) => asset.asset_id));
  const assets = [...(payload.assets || [])];
  const healthByAsset = { ...(payload.healthByAsset || {}) };
  const forecastByAsset = { ...(payload.forecastByAsset || {}) };
  const sensorsByAsset = { ...(payload.sensorsByAsset || {}) };
  const maintenanceLogByAsset = { ...(payload.maintenanceLogByAsset || {}) };

  (firebaseState.nodes || []).forEach((node) => {
    const assetId = node.assetId;
    const location = node.location || { lat: 0, lon: 0 };
    const severity =
      node.failureProbability72h >= 0.8
        ? "critical"
        : node.failureProbability72h >= 0.6
          ? "warning"
          : node.failureProbability72h >= 0.35
            ? "watch"
            : "healthy";

    if (!existingIds.has(assetId)) {
      assets.push({
        asset_id: assetId,
        name: node.assetName || assetId,
        asset_type: "iot-node",
        status: "active",
        zone: node.zone || "global",
        location,
      });
      existingIds.add(assetId);
    }

    if (!healthByAsset[assetId]) {
      healthByAsset[assetId] = {
        asset_id: assetId,
        evaluated_at: node.latestAt,
        health_score: node.healthScore,
        risk_level: severity,
        failure_probability_72h: node.failureProbability72h,
        anomaly_flag: node.failureProbability72h >= 0.6 ? 1 : 0,
        severity,
        components: {
          mechanical_stress: clamp01(firstFinite(node.telemetry?.strain?.value, 0) / 20),
          thermal_stress: clamp01((firstFinite(node.telemetry?.temperature?.value, 20) - 20) / 25),
          fatigue: clamp01(firstFinite(node.telemetry?.vibration?.value, 0) / 10),
          environmental_exposure: clamp01(firstFinite(node.telemetry?.tilt?.value, 0) / 1.2),
        },
      };
    }

    if (!forecastByAsset[assetId]) {
      forecastByAsset[assetId] = buildSyntheticForecast(assetId, healthByAsset[assetId]);
    }

    if (!sensorsByAsset[assetId]) {
      sensorsByAsset[assetId] = {
        strain: node.telemetry?.strain,
        vibration: node.telemetry?.vibration,
        temperature: node.telemetry?.temperature,
        tilt: node.telemetry?.tilt,
      };
    }

    if (!maintenanceLogByAsset[assetId]) {
      maintenanceLogByAsset[assetId] = [
        {
          timestamp: node.latestAt,
          unit: String(node.nodeId).toUpperCase(),
          operator: "FIREBASE_NODE",
          status: "INGESTED",
          verified: true,
        },
      ];
    }
  });

  merged.assets = assets;
  merged.healthByAsset = healthByAsset;
  merged.forecastByAsset = forecastByAsset;
  merged.sensorsByAsset = sensorsByAsset;
  merged.maintenanceLogByAsset = maintenanceLogByAsset;
  return merged;
}

export function getFirebaseNodesConfig() {
  try {
    const raw = window.localStorage.getItem(FIREBASE_CONFIG_STORAGE_KEY);
    if (!raw) {
      return { ...FIREBASE_DEFAULT_CONFIG };
    }
    const parsed = JSON.parse(raw);
    return {
      ...FIREBASE_DEFAULT_CONFIG,
      ...(parsed && typeof parsed === "object" ? parsed : {}),
      dbUrl: normalizeFirebaseDbUrl(parsed?.dbUrl),
      basePath: normalizeFirebaseBasePath(parsed?.basePath),
      authToken: typeof parsed?.authToken === "string" ? parsed.authToken : "",
      enabled: Boolean(parsed?.enabled),
    };
  } catch (_error) {
    return { ...FIREBASE_DEFAULT_CONFIG };
  }
}

export function saveFirebaseNodesConfig(nextConfig) {
  const merged = {
    ...getFirebaseNodesConfig(),
    ...(nextConfig || {}),
  };
  const normalized = {
    enabled: Boolean(merged.enabled),
    dbUrl: normalizeFirebaseDbUrl(merged.dbUrl),
    basePath: normalizeFirebaseBasePath(merged.basePath),
    authToken: typeof merged.authToken === "string" ? merged.authToken.trim() : "",
  };
  try {
    window.localStorage.setItem(FIREBASE_CONFIG_STORAGE_KEY, JSON.stringify(normalized));
  } catch (_error) {
    // Ignore storage errors and continue runtime-only.
  }
  return normalized;
}

export function clearFirebaseNodesConfig() {
  const cleared = { ...FIREBASE_DEFAULT_CONFIG };
  try {
    window.localStorage.setItem(FIREBASE_CONFIG_STORAGE_KEY, JSON.stringify(cleared));
  } catch (_error) {
    // Ignore storage errors.
  }
  return cleared;
}

async function fetchFirebaseNodesRuntime(config) {
  const normalizedConfig = {
    enabled: Boolean(config.enabled),
    dbUrl: normalizeFirebaseDbUrl(config.dbUrl),
    basePath: normalizeFirebaseBasePath(config.basePath),
    authToken: typeof config.authToken === "string" ? config.authToken.trim() : "",
  };

  if (!normalizedConfig.enabled) {
    return createFirebaseDisconnectedState(normalizedConfig, "Firebase connector is disabled.");
  }
  if (!normalizedConfig.dbUrl) {
    return createFirebaseDisconnectedState(normalizedConfig, "Firebase DB URL is required.");
  }

  const encodedPath = encodeFirebasePath(normalizedConfig.basePath);
  const params = new URLSearchParams();
  if (normalizedConfig.authToken) {
    params.set("auth", normalizedConfig.authToken);
  }
  const endpoint = `${normalizedConfig.dbUrl}/${encodedPath}.json${params.toString() ? `?${params.toString()}` : ""}`;

  const controller = new AbortController();
  const configuredTimeoutMs = Number(DASHBOARD_CONFIG.requestTimeoutMs);
  const timeoutMs = Number.isFinite(configuredTimeoutMs) && configuredTimeoutMs > 0
    ? configuredTimeoutMs
    : 10000;
  const timer = setTimeout(
    () => controller.abort(),
    timeoutMs,
  );

  try {
    const response = await fetch(endpoint, {
      method: "GET",
      headers: { Accept: "application/json" },
      signal: controller.signal,
    });
    if (!response.ok) {
      return {
        ...createFirebaseDisconnectedState(normalizedConfig, `Firebase HTTP ${response.status}.`),
        errorCode: `HTTP_${response.status}`,
      };
    }
    const body = await response.json();
    if (!body || typeof body !== "object") {
      return {
        ...createFirebaseDisconnectedState(normalizedConfig, "Firebase returned an empty payload."),
        errorCode: "EMPTY_PAYLOAD",
      };
    }

    const nodes = Object.entries(body)
      .map(([nodeId, nodeValue]) => parseFirebaseNode(nodeId, nodeValue))
      .filter((node) => node !== null)
      .sort((left, right) => right.latestAt.localeCompare(left.latestAt));

    const mappedNodes = nodes.filter((node) => !!node.assetId).length;

    return {
      ...normalizedConfig,
      connected: true,
      lastFetchedAt: new Date().toISOString(),
      nodes,
      mappedNodes,
      totalNodes: nodes.length,
      message: nodes.length
        ? `Loaded ${nodes.length} nodes from Firebase path ${normalizedConfig.basePath}.`
        : "Connected to Firebase, but no nodes found at configured path.",
      errorCode: null,
    };
  } catch (error) {
    const message =
      error?.name === "AbortError"
        ? "Firebase request timed out."
        : `Firebase request failed: ${error?.message || "unknown error"}`;
    return {
      ...createFirebaseDisconnectedState(normalizedConfig, message),
      errorCode: error?.name === "AbortError" ? "TIMEOUT" : "NETWORK_ERROR",
    };
  } finally {
    clearTimeout(timer);
  }
}

function normalizeProbability(value) {
  return Math.max(0, Math.min(1, Number(value ?? 0)));
}

function normalizeForecastPoints(forecast) {
  if (forecast && Array.isArray(forecast.points) && forecast.points.length > 0) {
    return forecast.points
      .map((point) => ({ hour: Number(point.hour), probability: normalizeProbability(point.probability) }))
      .filter((point) => Number.isFinite(point.hour))
      .sort((left, right) => left.hour - right.hour);
  }

  const baseProbability = normalizeProbability(forecast?.failure_probability_72h ?? 0.4);
  const points = [];
  for (let hour = 0; hour <= 72; hour += 8) {
    const wave = Math.sin(hour / 12) * 0.07;
    const drift = (hour / 72) * 0.16;
    points.push({
      hour,
      probability: normalizeProbability(baseProbability - 0.08 + wave + drift),
    });
  }
  return points;
}

function buildSyntheticForecast(assetId, health) {
  const probability = normalizeProbability(health?.failure_probability_72h ?? 0.35);
  return {
    asset_id: assetId,
    horizon_hours: 72,
    confidence: 0.74,
    points: normalizeForecastPoints({ failure_probability_72h: probability }),
  };
}

function buildSensorTelemetry(health) {
  const components = health?.components ?? {};
  const bases = {
    strain: Number(components.mechanical_stress ?? 0.4),
    vibration: Number(components.fatigue ?? 0.35),
    temperature: Number(components.thermal_stress ?? 0.3),
    tilt: Number(components.environmental_exposure ?? 0.25),
  };

  const definitions = {
    strain: { factor: 18, unit: "me", label: "variance", precision: 1 },
    vibration: { factor: 9, unit: "mm/s", label: "trend", precision: 1 },
    temperature: { factor: 42, unit: "C", label: "spike", precision: 1 },
    tilt: { factor: 0.8, unit: "deg", label: "drift", precision: 2 },
  };

  const telemetry = {};
  Object.entries(definitions).forEach(([key, spec]) => {
    const value = bases[key] * spec.factor;
    const samples = [];
    for (let i = 0; i < 8; i += 1) {
      const ratio = 0.68 + i * 0.05;
      samples.push(Number((value * ratio).toFixed(spec.precision + 1)));
    }

    telemetry[key] = {
      value: Number(value.toFixed(spec.precision)),
      unit: spec.unit,
      delta: `+${(samples[samples.length - 1] - samples[samples.length - 2]).toFixed(spec.precision)} ${spec.label}`,
      samples,
    };
  });

  return telemetry;
}

function normalizeLiveSensorTelemetry(snapshot) {
  const sensors = snapshot?.sensors;
  if (!sensors || typeof sensors !== "object") {
    return null;
  }

  const definitions = {
    strain: { unit: "me", label: "variance", precision: 1 },
    vibration: { unit: "mm/s", label: "trend", precision: 2 },
    temperature: { unit: "C", label: "spike", precision: 1 },
    tilt: { unit: "deg", label: "drift", precision: 2 },
  };

  const normalized = {};
  for (const [key, spec] of Object.entries(definitions)) {
    const metric = sensors[key];
    const value = Number(metric?.value);
    if (!Number.isFinite(value)) {
      return null;
    }

    const samples = Array.isArray(metric?.samples)
      ? metric.samples.map((sample) => Number(sample)).filter((sample) => Number.isFinite(sample))
      : [];
    const normalizedSamples = samples.length ? samples : [value];
    const delta =
      typeof metric?.delta === "string" && metric.delta.trim()
        ? metric.delta
        : `+0.${"0".repeat(spec.precision)} ${spec.label}`;

    normalized[key] = {
      value: Number(value.toFixed(spec.precision)),
      unit: metric?.unit || spec.unit,
      delta,
      samples: normalizedSamples,
    };
  }

  return normalized;
}

function classifyHttpCode(status) {
  if (status === 401) {
    return "UNAUTHORIZED";
  }
  if (status === 403) {
    return "FORBIDDEN";
  }
  if (status === 429) {
    return "TOO_MANY_REQUESTS";
  }
  if (status === 404) {
    return "NOT_FOUND";
  }
  if (status >= 500) {
    return "UPSTREAM_ERROR";
  }
  return "HTTP_ERROR";
}

function inferFriendlyBlockchainMessage(error) {
  const raw = String(error?.message || "unknown error");
  if (/1010/.test(raw)) {
    return "Sepolia RPC blocked by provider firewall (1010). Switch to a fallback RPC endpoint.";
  }
  if (/timeout|timed out/i.test(raw) || error?.code === "TIMEOUT" || error?.code === "BLOCKCHAIN_TIMEOUT") {
    return "Sepolia connectivity check timed out. Retry or switch RPC endpoint.";
  }
  if (/expected.*11155111|wrong chain|chain_id/i.test(raw)) {
    return "Connected RPC is not Sepolia. Use chain ID 11155111.";
  }
  if (/unauthorized|forbidden|dev-token|401|403/i.test(raw) || error?.code === "UNAUTHORIZED") {
    return "Gateway authorization failed. Ensure Bearer dev-token is configured.";
  }
  return `Sepolia connection failed: ${raw}`;
}

function defaultBlockchainConnection(verification) {
  return {
    connected: false,
    network: "sepolia",
    expected_chain_id: 11155111,
    chain_id: null,
    latest_block: null,
    contract_address: verification?.contract_address ?? null,
    contract_deployed: null,
    checked_at: new Date().toISOString(),
    code: null,
    message: "Click 'Connect Sepolia' to validate live blockchain access.",
    source: "dashboard",
  };
}

function buildMaintenanceLogByAsset(assets, verification, healthByAsset) {
  const logs = {};

  assets.forEach((asset, index) => {
    const health = healthByAsset[asset.asset_id];
    const baseTime = health?.evaluated_at ?? new Date().toISOString();
    logs[asset.asset_id] = [
      {
        timestamp: baseTime,
        unit: asset.asset_id.toUpperCase(),
        operator: index % 2 === 0 ? "AUTO_SYS_A1" : "ORCH_ENGINE",
        status: verification?.asset_id === asset.asset_id ? String(verification.verification_status || "PENDING").toUpperCase() : "ANALYZED",
        verified: verification?.asset_id === asset.asset_id ? String(verification.verification_status || "").toLowerCase() === "confirmed" : true,
      },
      {
        timestamp: new Date(new Date(baseTime).getTime() - 2 * 60 * 60 * 1000).toISOString(),
        unit: asset.asset_id.toUpperCase(),
        operator: "TEAM_FIELD_12",
        status: "SCHEDULED",
        verified: false,
      },
    ];
  });

  return logs;
}

async function parseResponseJsonSafely(response) {
  try {
    return await response.json();
  } catch (_error) {
    return null;
  }
}

function parseRetryAfterMs(response) {
  const raw = response.headers?.get("Retry-After");
  const seconds = Number(raw);
  if (Number.isFinite(seconds) && seconds > 0) {
    return Math.round(seconds * 1000);
  }
  return DEFAULT_GATEWAY_RETRY_MS;
}

function secondsUntil(timestampMs) {
  return Math.max(1, Math.ceil((timestampMs - Date.now()) / 1000));
}

async function fetchJson(path, { auth = true, method = "GET", body = undefined } = {}) {
  const endpoint = path;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), DASHBOARD_CONFIG.requestTimeoutMs);

  try {
    const headers = {};
    if (auth) {
      headers.Authorization = `Bearer ${DASHBOARD_CONFIG.authToken}`;
    }
    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
    }

    const response = await fetch(path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });

    if (!response.ok) {
      let message = `HTTP ${response.status} for ${path}`;
      const parsed = await parseResponseJsonSafely(response);

      const code = parsed?.error?.code || classifyHttpCode(response.status);
      if (response.status === 429) {
        gatewayRateLimitUntilMs = Date.now() + parseRetryAfterMs(response);
      }
      if (parsed?.error?.message) {
        message = String(parsed.error.message);
      } else if (parsed?.detail) {
        message = String(parsed.detail);
      }

      throw new DashboardApiError({
        code,
        message,
        endpoint,
        status: response.status,
        details: parsed,
      });
    }

    return await response.json();
  } catch (error) {
    if (error instanceof DashboardApiError) {
      throw error;
    }

    if (error?.name === "AbortError") {
      throw new DashboardApiError({
        code: "TIMEOUT",
        message: `Request timed out for ${path}`,
        endpoint,
      });
    }

    throw new DashboardApiError({
      code: "NETWORK_ERROR",
      message: error?.message || `Network error for ${path}`,
      endpoint,
    });
  } finally {
    clearTimeout(timer);
  }
}

function cloneMockPayload(error = null) {
  const payload = JSON.parse(JSON.stringify(MOCK_DATA));
  const firebaseConfig = getFirebaseNodesConfig();
  payload.generatedAt = new Date().toISOString();
  payload.activeMaintenanceId = payload.activeMaintenanceId || payload.verification?.maintenance_id || null;
  payload.walletConnection = emptyWalletStatus();
  payload.verificationState = payload.verificationState || null;
  payload.evidenceByMaintenanceId = payload.evidenceByMaintenanceId || {};
  payload.firebaseNodes = createFirebaseDisconnectedState(
    firebaseConfig,
    firebaseConfig.enabled
      ? "Firebase configured. Refresh to load live nodes."
      : "Firebase connector is disabled.",
  );
  payload.error = error
    ? {
        code: error.code || "MOCK_FALLBACK",
        message: error.message || "Using fallback data.",
        endpoint: error.endpoint || null,
      }
    : null;
  return payload;
}

export async function loadDashboardData(previousPayload = null) {
  const firebaseConfig = getFirebaseNodesConfig();
  if (Date.now() < gatewayRateLimitUntilMs) {
    const waitSeconds = secondsUntil(gatewayRateLimitUntilMs);
    const error = new DashboardApiError({
      code: "TOO_MANY_REQUESTS",
      message: `Gateway is rate-limiting requests. Retrying in ${waitSeconds}s.`,
      endpoint: "/assets",
      status: 429,
    });

    const firebaseState = await fetchFirebaseNodesRuntime(firebaseConfig);
    if (previousPayload) {
      return {
        payload: mergeFirebaseIntoPayload(
          {
            ...previousPayload,
            stale: true,
            generatedAt: new Date().toISOString(),
            error: {
              code: error.code,
              message: error.message,
              endpoint: error.endpoint,
            },
          },
          firebaseState,
        ),
        stale: true,
      };
    }

    return {
      payload: mergeFirebaseIntoPayload(cloneMockPayload(error), firebaseState),
      stale: true,
    };
  }

  dashboardRefreshCycle += 1;
  const cycle = dashboardRefreshCycle;

  try {
    let gatewayHealth = previousPayload?.gatewayHealth || {
      status: "degraded",
      service: "api-gateway",
      message: "Gateway health check deferred.",
    };
    const shouldRefreshGatewayHealth = cycle % HEALTH_REFRESH_EVERY_CYCLES === 1 || !previousPayload?.gatewayHealth;
    if (shouldRefreshGatewayHealth) {
      try {
        gatewayHealth = await fetchJson("/health", { auth: false });
      } catch (_error) {
        gatewayHealth = previousPayload?.gatewayHealth || gatewayHealth;
      }
    }

    const assetsResponse = await fetchJson("/assets", { auth: true });

    const assets = assetsResponse.data ?? [];
    if (!assets.length) {
      return {
        payload: cloneMockPayload(new DashboardApiError({ code: "NO_ASSETS", message: "No assets returned by API.", endpoint: "/assets" })),
        stale: true,
      };
    }

    const healthByAsset = {};
    const forecastByAsset = {};
    const sensorsByAsset = {};

    const refreshHealthThisCycle = cycle % HEALTH_REFRESH_EVERY_CYCLES === 1;
    const refreshForecastThisCycle = cycle % FORECAST_REFRESH_EVERY_CYCLES === 1;
    const refreshTelemetryThisCycle = cycle % TELEMETRY_REFRESH_EVERY_CYCLES === 1;

    for (const asset of assets) {
      const assetId = asset.asset_id;
      const previousHealth = previousPayload?.healthByAsset?.[assetId] || null;
      let health = previousHealth;

      if (!health || refreshHealthThisCycle) {
        try {
          const healthResponse = await fetchJson(`/assets/${assetId}/health`, { auth: true });
          health = healthResponse.data;
        } catch (_error) {
          health = previousHealth;
        }
      }

      if (!health) {
        health = {
          asset_id: assetId,
          evaluated_at: new Date().toISOString(),
          health_score: 0.75,
          risk_level: "Moderate",
          failure_probability_72h: 0.4,
          anomaly_flag: 0,
          severity: "watch",
          components: {
            mechanical_stress: 0.4,
            thermal_stress: 0.35,
            fatigue: 0.35,
            environmental_exposure: 0.3,
          },
        };
      }
      healthByAsset[assetId] = health;

      const previousTelemetry = previousPayload?.sensorsByAsset?.[assetId] || null;
      if (Date.now() >= telemetryBackoffUntilMs && refreshTelemetryThisCycle) {
        try {
          const telemetryResponse = await fetchJson(`/telemetry/${assetId}/latest`, { auth: true });
          const liveTelemetry = normalizeLiveSensorTelemetry(telemetryResponse?.data);
          sensorsByAsset[assetId] = liveTelemetry || buildSensorTelemetry(health);
          telemetryBackoffUntilMs = 0;
        } catch (error) {
          if (["UPSTREAM_ERROR", "NETWORK_ERROR", "TIMEOUT", "TOO_MANY_REQUESTS"].includes(String(error?.code || ""))) {
            telemetryBackoffUntilMs = Date.now() + TELEMETRY_UPSTREAM_COOLDOWN_MS;
          }
          sensorsByAsset[assetId] = previousTelemetry || buildSensorTelemetry(health);
        }
      } else {
        sensorsByAsset[assetId] = previousTelemetry || buildSensorTelemetry(health);
      }

      const previousForecast = previousPayload?.forecastByAsset?.[assetId] || null;
      if (!previousForecast || refreshForecastThisCycle) {
        try {
          const forecastResponse = await fetchJson(`/assets/${assetId}/forecast?horizon_hours=72`, { auth: true });
          const forecast = forecastResponse.data ?? {};
          forecastByAsset[assetId] = {
            ...forecast,
            asset_id: assetId,
            points: normalizeForecastPoints(forecast),
          };
        } catch (_error) {
          forecastByAsset[assetId] = previousForecast || buildSyntheticForecast(assetId, health);
        }
      } else {
        forecastByAsset[assetId] = previousForecast;
      }
    }

    let automationIncidents = Array.isArray(previousPayload?.automationIncidents)
      ? previousPayload.automationIncidents
      : [];
    const shouldRefreshAutomation =
      cycle % AUTOMATION_REFRESH_EVERY_CYCLES === 1 || automationIncidents.length === 0;
    if (shouldRefreshAutomation) {
      try {
        const incidentsResponse = await fetchJson("/automation/incidents", { auth: true });
        automationIncidents = Array.isArray(incidentsResponse?.data) ? incidentsResponse.data : [];
      } catch (_error) {
        automationIncidents = Array.isArray(previousPayload?.automationIncidents)
          ? previousPayload.automationIncidents
          : [];
      }
    }

    const incidentMaintenanceId =
      automationIncidents.find(
        (incident) =>
          typeof incident?.maintenance_id === "string" && incident.maintenance_id.trim().length > 0,
      )?.maintenance_id || null;
    const previousLiveMaintenanceId =
      previousPayload?.source === "live" && typeof previousPayload?.activeMaintenanceId === "string"
        ? previousPayload.activeMaintenanceId
        : null;
    const fallbackMaintenanceId =
      typeof DASHBOARD_CONFIG.maintenanceIdFallback === "string" && DASHBOARD_CONFIG.maintenanceIdFallback.trim()
        ? DASHBOARD_CONFIG.maintenanceIdFallback.trim()
        : null;
    const preferredMaintenanceId =
      incidentMaintenanceId ||
      previousLiveMaintenanceId ||
      fallbackMaintenanceId ||
      null;

    let verification =
      previousPayload?.source === "live" &&
      previousPayload?.verification &&
      previousPayload?.verification?.maintenance_id === preferredMaintenanceId
        ? previousPayload.verification
        : null;
    const shouldRefreshMaintenanceDetails = true;
    if (
      preferredMaintenanceId &&
      Date.now() >= verificationEndpointBackoffUntilMs &&
      shouldRefreshMaintenanceDetails
    ) {
      try {
        const verificationResponse = await fetchJson(`/maintenance/${preferredMaintenanceId}/verification`, {
          auth: true,
        });
        verification = verificationResponse.data ?? null;
        verificationEndpointBackoffUntilMs = 0;
      } catch (error) {
        if (String(error?.code || "") === "NOT_FOUND") {
          verificationEndpointBackoffUntilMs = Date.now() + OPTIONAL_ENDPOINT_COOLDOWN_MS;
        } else if (String(error?.code || "") === "TOO_MANY_REQUESTS") {
          verificationEndpointBackoffUntilMs = Math.max(
            gatewayRateLimitUntilMs,
            Date.now() + DEFAULT_GATEWAY_RETRY_MS,
          );
        }
        verification =
          previousPayload?.source === "live" &&
          previousPayload?.verification &&
          previousPayload?.verification?.maintenance_id === preferredMaintenanceId
            ? previousPayload.verification
            : null;
      }
    }

    let evidenceItems =
      preferredMaintenanceId &&
      Array.isArray(previousPayload?.evidenceByMaintenanceId?.[preferredMaintenanceId])
        ? previousPayload.evidenceByMaintenanceId[preferredMaintenanceId]
        : [];
    if (
      preferredMaintenanceId &&
      Date.now() >= evidenceEndpointBackoffUntilMs &&
      shouldRefreshMaintenanceDetails
    ) {
      try {
        const evidenceResponse = await fetchJson(`/maintenance/${preferredMaintenanceId}/evidence`, { auth: true });
        evidenceItems = Array.isArray(evidenceResponse?.data) ? evidenceResponse.data : [];
        evidenceEndpointBackoffUntilMs = 0;
      } catch (error) {
        if (String(error?.code || "") === "NOT_FOUND") {
          evidenceEndpointBackoffUntilMs = Date.now() + OPTIONAL_ENDPOINT_COOLDOWN_MS;
        } else if (String(error?.code || "") === "TOO_MANY_REQUESTS") {
          evidenceEndpointBackoffUntilMs = Math.max(
            gatewayRateLimitUntilMs,
            Date.now() + DEFAULT_GATEWAY_RETRY_MS,
          );
        }
        evidenceItems =
          preferredMaintenanceId &&
          Array.isArray(previousPayload?.evidenceByMaintenanceId?.[preferredMaintenanceId])
            ? previousPayload.evidenceByMaintenanceId[preferredMaintenanceId]
            : [];
      }
    }

    const incidentWithVerification = automationIncidents.find(
      (incident) =>
        incident &&
        typeof incident.maintenance_id === "string" &&
        incident.maintenance_id === preferredMaintenanceId &&
        typeof incident.verification_status === "string",
    );
    const verificationState = incidentWithVerification
      ? {
          verification_status: incidentWithVerification.verification_status || null,
          verification_maintenance_id: incidentWithVerification.verification_maintenance_id || null,
          verification_tx_hash: incidentWithVerification.verification_tx_hash || null,
          verification_error: incidentWithVerification.verification_error || null,
          verification_updated_at: incidentWithVerification.verification_updated_at || null,
        }
      : null;

    let lstmRealtime = previousPayload?.lstmRealtime ?? null;
    const shouldRefreshLstm = cycle % LSTM_REFRESH_EVERY_CYCLES === 1 || !lstmRealtime;
    if (Date.now() >= lstmEndpointBackoffUntilMs && shouldRefreshLstm) {
      try {
        const lstmResponse = await fetchJson("/lstm/realtime", { auth: true });
        lstmRealtime = lstmResponse.data ?? null;
        lstmEndpointBackoffUntilMs = 0;
      } catch (error) {
        if (String(error?.code || "") === "NOT_FOUND") {
          lstmEndpointBackoffUntilMs = Date.now() + OPTIONAL_ENDPOINT_COOLDOWN_MS;
        } else if (String(error?.code || "") === "TOO_MANY_REQUESTS") {
          lstmEndpointBackoffUntilMs = Math.max(
            gatewayRateLimitUntilMs,
            Date.now() + DEFAULT_GATEWAY_RETRY_MS,
          );
        }
        lstmRealtime = previousPayload?.lstmRealtime ?? null;
      }
    }

    const payload = {
      source: "live",
      stale: false,
      error: null,
      generatedAt: new Date().toISOString(),
      gatewayHealth,
      assets,
      healthByAsset,
      forecastByAsset,
      sensorsByAsset,
      maintenanceLogByAsset: buildMaintenanceLogByAsset(assets, verification, healthByAsset),
      verification,
      verificationState,
      activeMaintenanceId: verification?.maintenance_id || preferredMaintenanceId || null,
      evidenceByMaintenanceId: preferredMaintenanceId
        ? {
            [preferredMaintenanceId]: evidenceItems,
          }
        : {},
      automationIncidents,
      lstmRealtime,
      blockchainConnection: defaultBlockchainConnection(verification),
      walletConnection: emptyWalletStatus(),
    };

    const firebaseState = await fetchFirebaseNodesRuntime(firebaseConfig);
    const mergedPayload = mergeFirebaseIntoPayload(payload, firebaseState);

    return { payload: mergedPayload, stale: false };
  } catch (error) {
    if (previousPayload) {
      const firebaseState = await fetchFirebaseNodesRuntime(firebaseConfig);
      const refreshedPrevious = mergeFirebaseIntoPayload(
        {
          ...previousPayload,
          walletConnection: previousPayload.walletConnection || emptyWalletStatus(),
        },
        firebaseState,
      );
      return {
        payload: {
          ...refreshedPrevious,
          stale: true,
          generatedAt: new Date().toISOString(),
          error: {
            code: error?.code || "UNKNOWN",
            message: error?.message || "Failed to refresh data.",
            endpoint: error?.endpoint || null,
          },
        },
        stale: true,
      };
    }

    return {
      payload: cloneMockPayload(error),
      stale: true,
    };
  }
}

export async function connectToSepolia() {
  try {
    const response = await fetchJson("/blockchain/connect", {
      auth: true,
      method: "POST",
      body: {},
    });

    return {
      ...defaultBlockchainConnection(null),
      ...response,
      checked_at: response.checked_at || new Date().toISOString(),
      code: response.code || null,
      message: response.message || "Connected to Sepolia.",
      source: response.source || "dashboard",
    };
  } catch (error) {
    return {
      ...defaultBlockchainConnection(null),
      checked_at: new Date().toISOString(),
      code: error?.code || "UNKNOWN",
      message: inferFriendlyBlockchainMessage(error),
      source: "dashboard",
    };
  }
}

export async function acknowledgeIncident(workflowId, { acknowledgedBy, ackNotes = null }) {
  const response = await fetchJson(`/automation/incidents/${workflowId}/acknowledge`, {
    auth: true,
    method: "POST",
    body: {
      acknowledged_by: acknowledgedBy,
      ack_notes: ackNotes,
    },
  });
  return response?.data || null;
}

export async function trackMaintenanceVerification(maintenanceId) {
  if (!maintenanceId) {
    throw new DashboardApiError({
      code: "MISSING_MAINTENANCE_ID",
      message: "No maintenance ID available for verification tracking.",
      endpoint: "/maintenance/{maintenance_id}/verification/track",
    });
  }

  const response = await fetchJson(`/maintenance/${maintenanceId}/verification/track`, {
    auth: true,
    method: "POST",
    body: {},
  });
  return response?.data || null;
}

export async function createEvidenceUpload(maintenanceId, payload) {
  if (!maintenanceId) {
    throw new DashboardApiError({
      code: "MISSING_MAINTENANCE_ID",
      message: "No maintenance ID available for evidence upload.",
      endpoint: "/maintenance/{maintenance_id}/evidence/uploads",
    });
  }
  const response = await fetchJson(`/maintenance/${maintenanceId}/evidence/uploads`, {
    auth: true,
    method: "POST",
    body: payload,
  });
  return response || null;
}

export async function finalizeEvidenceUpload(maintenanceId, evidenceId, payload) {
  if (!maintenanceId || !evidenceId) {
    throw new DashboardApiError({
      code: "MISSING_EVIDENCE_CONTEXT",
      message: "Maintenance ID or evidence ID missing for evidence finalize.",
      endpoint: "/maintenance/{maintenance_id}/evidence/{evidence_id}/finalize",
    });
  }
  const response = await fetchJson(`/maintenance/${maintenanceId}/evidence/${evidenceId}/finalize`, {
    auth: true,
    method: "POST",
    body: payload,
  });
  return response?.data || null;
}

export async function listMaintenanceEvidence(maintenanceId) {
  if (!maintenanceId) {
    return [];
  }
  const response = await fetchJson(`/maintenance/${maintenanceId}/evidence`, { auth: true });
  return Array.isArray(response?.data) ? response.data : [];
}

export async function submitVerification(maintenanceId, payload = {}) {
  if (!maintenanceId) {
    throw new DashboardApiError({
      code: "MISSING_MAINTENANCE_ID",
      message: "No maintenance ID available for verification submit.",
      endpoint: "/maintenance/{maintenance_id}/verification/submit",
    });
  }
  const response = await fetchJson(`/maintenance/${maintenanceId}/verification/submit`, {
    auth: true,
    method: "POST",
    body: payload,
  });
  return response?.data || null;
}

export async function sendAssistantChat({ message, language = "auto", history = [] }) {
  const text = String(message || "").trim();
  if (!text) {
    throw new DashboardApiError({
      code: "ASSISTANT_EMPTY_MESSAGE",
      message: "Type a question before sending.",
      endpoint: "/assistant/chat",
    });
  }

  const sanitizedHistory = Array.isArray(history)
    ? history
      .filter((item) => item && (item.role === "user" || item.role === "assistant"))
      .map((item) => ({
        role: item.role,
        content: String(item.content || "").trim(),
      }))
      .filter((item) => item.content.length > 0)
    : [];

  const response = await fetchJson("/assistant/chat", {
    auth: true,
    method: "POST",
    body: {
      message: text,
      language,
      history: sanitizedHistory,
    },
  });
  return response?.data || null;
}

async function uploadToSignedUrl(uploadUrl, uploadMethod, uploadHeaders, file) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), DASHBOARD_CONFIG.requestTimeoutMs);

  try {
    const response = await fetch(uploadUrl, {
      method: uploadMethod || "PUT",
      headers: uploadHeaders || {},
      body: file,
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new DashboardApiError({
        code: "EVIDENCE_UPLOAD_FAILED",
        message: `Evidence object upload failed with HTTP ${response.status}.`,
        endpoint: uploadUrl,
        status: response.status,
      });
    }
  } catch (error) {
    if (error instanceof DashboardApiError) {
      throw error;
    }
    if (error?.name === "AbortError") {
      throw new DashboardApiError({
        code: "TIMEOUT",
        message: "Evidence upload timed out.",
        endpoint: uploadUrl,
      });
    }
    throw new DashboardApiError({
      code: "NETWORK_ERROR",
      message: error?.message || "Evidence upload failed.",
      endpoint: uploadUrl,
    });
  } finally {
    clearTimeout(timer);
  }
}

export async function uploadAndFinalizeEvidence({
  maintenanceId,
  assetId,
  file,
  uploadedBy,
  category = null,
  notes = null,
}) {
  if (!file) {
    throw new DashboardApiError({
      code: "EVIDENCE_FILE_REQUIRED",
      message: "Select an evidence file before upload.",
      endpoint: "/maintenance/{maintenance_id}/evidence/uploads",
    });
  }

  const uploadSession = await createEvidenceUpload(maintenanceId, {
    asset_id: assetId,
    filename: file.name,
    content_type: file.type || "application/octet-stream",
    size_bytes: file.size,
    category,
    notes,
  });

  await uploadToSignedUrl(
    uploadSession.upload_url,
    uploadSession.upload_method,
    uploadSession.upload_headers,
    file,
  );

  const evidence = uploadSession?.data;
  const finalized = await finalizeEvidenceUpload(
    maintenanceId,
    evidence?.evidence_id,
    { uploaded_by: uploadedBy || "dashboard-operator" },
  );

  return finalized;
}

export { DashboardApiError };

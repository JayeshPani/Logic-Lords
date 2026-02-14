import { DASHBOARD_CONFIG } from "./config.js";
import { MOCK_DATA } from "./mock-data.js";
import { emptyWalletStatus } from "./wallet.js";

function normalizeForecastPoints(forecast) {
  if (!forecast) {
    return [];
  }
  if (Array.isArray(forecast.points) && forecast.points.length > 0) {
    return forecast.points;
  }

  const baseProbability = Number(forecast.failure_probability_72h ?? 0.45);
  const points = [];
  for (let hour = 0; hour <= 72; hour += 8) {
    const wobble = Math.sin(hour / 14) * 0.08;
    const drift = hour / 72 * 0.15;
    const probability = Math.max(0, Math.min(1, baseProbability - 0.1 + wobble + drift));
    points.push({ hour, probability });
  }
  return points;
}

function buildSensorTelemetry(health) {
  const components = health?.components ?? {};
  const base = {
    strain: Number(components.mechanical_stress ?? 0.4),
    vibration: Number(components.fatigue ?? 0.35),
    temperature: Number(components.thermal_stress ?? 0.3),
    tilt: Number(components.environmental_exposure ?? 0.28),
  };

  const sensorScale = {
    strain: { factor: 18, precision: 1, unit: "me", label: "variance" },
    vibration: { factor: 9, precision: 1, unit: "mm/s", label: "trend" },
    temperature: { factor: 42, precision: 1, unit: "C", label: "spike" },
    tilt: { factor: 0.8, precision: 2, unit: "deg", label: "shift" },
  };

  const telemetry = {};
  Object.entries(sensorScale).forEach(([key, spec]) => {
    const value = base[key] * spec.factor;
    const samples = [];
    for (let i = 0; i < 7; i += 1) {
      const ratio = 0.72 + i * 0.045;
      samples.push(Number((value * ratio).toFixed(spec.precision + 1)));
    }

    telemetry[key] = {
      value: Number(value.toFixed(spec.precision)),
      unit: spec.unit,
      delta: `+${(samples[6] - samples[5]).toFixed(spec.precision)} ${spec.label}`,
      samples,
    };
  });

  return telemetry;
}

function normalizeMaintenanceLog(verification, health) {
  const verifiedAt = verification?.verified_at ?? health?.evaluated_at ?? new Date().toISOString();
  const asset = verification?.asset_id ?? health?.asset_id ?? "unknown_asset";
  const status = verification?.verification_status?.toUpperCase() ?? "PENDING";

  return [
    {
      timestamp: verifiedAt,
      unit: asset.toUpperCase(),
      operator: "AUTO_SYS_A1",
      status,
      verified: status === "CONFIRMED",
    },
    {
      timestamp: health?.evaluated_at ?? verifiedAt,
      unit: asset.toUpperCase(),
      operator: "ORCH_ENGINE",
      status: "ANALYZED",
      verified: true,
    },
  ];
}

async function fetchJson(path, { auth = true, method = "GET", body = undefined } = {}) {
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
      let details = `HTTP ${response.status} for ${path}`;
      try {
        const errorBody = await response.json();
        const message = errorBody?.error?.message || errorBody?.detail;
        if (message) {
          details = String(message);
        }
      } catch (_error) {
        // Ignore non-JSON errors and keep default HTTP details.
      }
      throw new Error(details);
    }

    return await response.json();
  } finally {
    clearTimeout(timer);
  }
}

function selectPrimaryAsset(assets, healthByAsset) {
  if (!assets || assets.length === 0) {
    return null;
  }

  let selected = assets[0];
  let highest = -1;

  assets.forEach((asset) => {
    const health = healthByAsset[asset.asset_id];
    const probability = Number(health?.failure_probability_72h ?? 0);
    if (probability > highest) {
      highest = probability;
      selected = asset;
    }
  });

  return selected;
}

export async function loadDashboardData() {
  try {
    const [gatewayHealth, assetsResponse] = await Promise.all([
      fetchJson("/health", { auth: false }),
      fetchJson("/assets", { auth: true }),
    ]);

    const assets = assetsResponse.data ?? [];
    if (!assets.length) {
      return MOCK_DATA;
    }

    const healthResponses = await Promise.all(
      assets.map(async (asset) => {
        try {
          const health = await fetchJson(`/assets/${asset.asset_id}/health`, { auth: true });
          return [asset.asset_id, health.data];
        } catch (_error) {
          return [asset.asset_id, null];
        }
      }),
    );

    const healthByAsset = Object.fromEntries(healthResponses);
    const primaryAsset = selectPrimaryAsset(assets, healthByAsset) ?? assets[0];

    const [forecastResponse, verificationResponse] = await Promise.all([
      fetchJson(`/assets/${primaryAsset.asset_id}/forecast?horizon_hours=72`, { auth: true }),
      fetchJson(`/maintenance/${DASHBOARD_CONFIG.maintenanceIdFallback}/verification`, { auth: true }),
    ]);

    const health = healthByAsset[primaryAsset.asset_id] ?? MOCK_DATA.health;
    const forecast = forecastResponse.data ?? MOCK_DATA.forecast;
    const verification = verificationResponse.data ?? MOCK_DATA.verification;

    return {
      source: "live",
      gatewayHealth,
      assets,
      health,
      forecast: {
        ...forecast,
        points: normalizeForecastPoints(forecast),
      },
      verification,
      blockchainConnection: {
        connected: false,
        network: "sepolia",
        expected_chain_id: 11155111,
        chain_id: null,
        latest_block: null,
        contract_address: verification.contract_address ?? null,
        contract_deployed: null,
        checked_at: new Date().toISOString(),
        message: "Click 'Connect Sepolia' to validate live blockchain access.",
        source: "dashboard",
      },
      walletConnection: emptyWalletStatus(),
      maintenanceLog: normalizeMaintenanceLog(verification, health),
      sensors: buildSensorTelemetry(health),
    };
  } catch (_error) {
    return MOCK_DATA;
  }
}

export async function connectToSepolia() {
  try {
    return await fetchJson("/blockchain/connect", {
      auth: true,
      method: "POST",
      body: {},
    });
  } catch (error) {
    return {
      connected: false,
      network: "sepolia",
      expected_chain_id: 11155111,
      chain_id: null,
      latest_block: null,
      contract_address: null,
      contract_deployed: null,
      checked_at: new Date().toISOString(),
      message: `Sepolia connection failed: ${error.message}`,
      source: "dashboard",
    };
  }
}

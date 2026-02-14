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
  payload.generatedAt = new Date().toISOString();
  payload.activeMaintenanceId =
    payload.activeMaintenanceId || payload.verification?.maintenance_id || DASHBOARD_CONFIG.maintenanceIdFallback;
  payload.walletConnection = emptyWalletStatus();
  payload.verificationState = payload.verificationState || null;
  payload.evidenceByMaintenanceId = payload.evidenceByMaintenanceId || {};
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
  try {
    const [gatewayHealth, assetsResponse] = await Promise.all([
      fetchJson("/health", { auth: false }),
      fetchJson("/assets", { auth: true }),
    ]);

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

    await Promise.all(
      assets.map(async (asset) => {
        const healthResponse = await fetchJson(`/assets/${asset.asset_id}/health`, { auth: true });
        const health = healthResponse.data;
        healthByAsset[asset.asset_id] = health;

        try {
          const telemetryResponse = await fetchJson(`/telemetry/${asset.asset_id}/latest`, { auth: true });
          const liveTelemetry = normalizeLiveSensorTelemetry(telemetryResponse?.data);
          sensorsByAsset[asset.asset_id] = liveTelemetry || buildSensorTelemetry(health);
        } catch (_error) {
          sensorsByAsset[asset.asset_id] = buildSensorTelemetry(health);
        }

        try {
          const forecastResponse = await fetchJson(`/assets/${asset.asset_id}/forecast?horizon_hours=72`, { auth: true });
          const forecast = forecastResponse.data ?? {};
          forecastByAsset[asset.asset_id] = {
            ...forecast,
            asset_id: asset.asset_id,
            points: normalizeForecastPoints(forecast),
          };
        } catch (_error) {
          forecastByAsset[asset.asset_id] = buildSyntheticForecast(asset.asset_id, health);
        }
      }),
    );

    let automationIncidents = [];
    try {
      const incidentsResponse = await fetchJson("/automation/incidents", { auth: true });
      automationIncidents = Array.isArray(incidentsResponse?.data) ? incidentsResponse.data : [];
    } catch (_error) {
      automationIncidents = [];
    }

    const incidentMaintenanceId =
      automationIncidents.find(
        (incident) =>
          typeof incident?.maintenance_id === "string" && incident.maintenance_id.trim().length > 0,
      )?.maintenance_id || null;
    const preferredMaintenanceId =
      incidentMaintenanceId ||
      previousPayload?.verification?.maintenance_id ||
      previousPayload?.activeMaintenanceId ||
      null;

    let verification = null;
    if (preferredMaintenanceId) {
      try {
        const verificationResponse = await fetchJson(`/maintenance/${preferredMaintenanceId}/verification`, {
          auth: true,
        });
        verification = verificationResponse.data ?? null;
      } catch (_error) {
        verification = null;
      }
    }

    let evidenceItems = [];
    if (preferredMaintenanceId) {
      try {
        const evidenceResponse = await fetchJson(`/maintenance/${preferredMaintenanceId}/evidence`, { auth: true });
        evidenceItems = Array.isArray(evidenceResponse?.data) ? evidenceResponse.data : [];
      } catch (_error) {
        evidenceItems = [];
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
      blockchainConnection: defaultBlockchainConnection(verification),
      walletConnection: emptyWalletStatus(),
    };

    return { payload, stale: false };
  } catch (error) {
    if (previousPayload) {
      return {
        payload: {
          ...previousPayload,
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

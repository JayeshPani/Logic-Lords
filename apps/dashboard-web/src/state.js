import { CHART_THRESHOLDS, SEVERITY_ORDER } from "./config.js";
import { emptyWalletStatus } from "./wallet.js";

function clamp01(value) {
  return Math.max(0, Math.min(1, Number(value ?? 0)));
}

export function toPercent(value, digits = 0) {
  return `${(clamp01(value) * 100).toFixed(digits)}%`;
}

export function probabilityToSeverity(probability) {
  const value = clamp01(probability);
  if (value >= CHART_THRESHOLDS.critical) {
    return "critical";
  }
  if (value >= CHART_THRESHOLDS.warning) {
    return "warning";
  }
  if (value >= CHART_THRESHOLDS.watch) {
    return "watch";
  }
  return "healthy";
}

export function severityLabel(probabilityOrSeverity) {
  if (["critical", "warning", "watch", "healthy"].includes(String(probabilityOrSeverity))) {
    const normalized = String(probabilityOrSeverity);
    if (normalized === "critical") {
      return "Critical";
    }
    if (normalized === "warning") {
      return "Warning";
    }
    if (normalized === "watch") {
      return "Watch";
    }
    return "Stable";
  }

  return severityLabel(probabilityToSeverity(probabilityOrSeverity));
}

function buildFallbackHealth(asset) {
  return {
    asset_id: asset.asset_id,
    evaluated_at: new Date().toISOString(),
    health_score: 0,
    risk_level: "Low",
    failure_probability_72h: 0,
    anomaly_flag: 0,
    severity: "healthy",
    components: {
      mechanical_stress: 0,
      thermal_stress: 0,
      fatigue: 0,
      environmental_exposure: 0,
    },
  };
}

function buildFallbackForecast(assetId) {
  return {
    asset_id: assetId,
    horizon_hours: 72,
    confidence: 0,
    points: [
      { hour: 0, probability: 0 },
      { hour: 72, probability: 0 },
    ],
  };
}

function normalizeAssets(raw) {
  const assets = raw.assets ?? [];
  const healthByAsset = raw.healthByAsset ?? {};

  return assets
    .map((asset) => {
      const health = healthByAsset[asset.asset_id] ?? buildFallbackHealth(asset);
      const probability = clamp01(health.failure_probability_72h);
      const severity = ["critical", "warning", "watch", "healthy"].includes(String(health.severity))
        ? String(health.severity)
        : probabilityToSeverity(probability);

      return {
        assetId: asset.asset_id,
        name: asset.name,
        zone: asset.zone,
        type: asset.asset_type,
        status: asset.status,
        location: asset.location,
        evaluatedAt: health.evaluated_at,
        healthScore: clamp01(health.health_score),
        riskLevel: health.risk_level || severityLabel(severity),
        failureProbability72h: probability,
        anomalyFlag: Number(health.anomaly_flag ?? 0),
        severity,
        severityLabel: severityLabel(severity),
        components: health.components ?? buildFallbackHealth(asset).components,
        isCritical: severity === "critical",
        isDegraded: severity === "critical" || severity === "warning",
      };
    })
    .sort((left, right) => {
      if (right.failureProbability72h !== left.failureProbability72h) {
        return right.failureProbability72h - left.failureProbability72h;
      }
      if (SEVERITY_ORDER[right.severity] !== SEVERITY_ORDER[left.severity]) {
        return SEVERITY_ORDER[right.severity] - SEVERITY_ORDER[left.severity];
      }
      return left.assetId.localeCompare(right.assetId);
    });
}

function buildOverviewModel(assetRows, blockchainConnection, stale, error, source, generatedAt) {
  const totalAssets = assetRows.length;
  const overallHealth =
    totalAssets === 0
      ? 0
      : assetRows.reduce((sum, asset) => sum + asset.healthScore, 0) / totalAssets;

  const criticalAssets = assetRows.filter((asset) => asset.isCritical).length;
  const systemFailureRisk = assetRows.reduce(
    (max, asset) => Math.max(max, asset.failureProbability72h),
    0,
  );

  return {
    source,
    generatedAt,
    stale,
    staleReason: error?.message || null,
    totalAssets,
    criticalAssets,
    overallHealth,
    systemFailureRisk,
    ledgerReachability: Boolean(blockchainConnection?.connected),
    isConnected: Boolean(blockchainConnection?.connected),
    triageAssets: assetRows,
  };
}

function buildLstmOverviewModel(raw) {
  const data = raw.lstmRealtime;
  if (!data || typeof data !== "object") {
    return {
      available: false,
      assetId: null,
      generatedAt: raw.generatedAt || new Date().toISOString(),
      currentProbability72h: 0,
      history: [],
      forecastPoints: [],
      model: null,
    };
  }

  const history = Array.isArray(data.history)
    ? data.history
      .map((item) => ({
        timestamp: item.timestamp || new Date().toISOString(),
        strain: Number(item.strain_value ?? 0),
        vibration: Number(item.vibration_rms ?? 0),
        temperature: Number(item.temperature ?? 0),
        humidity: Number(item.humidity ?? 0),
      }))
      .filter((item) => Number.isFinite(item.strain) && Number.isFinite(item.vibration))
    : [];

  const forecastPoints = Array.isArray(data.forecast_points)
    ? data.forecast_points
      .map((point) => ({
        hour: Number(point.hour ?? 0),
        probability: clamp01(point.probability),
      }))
      .filter((point) => Number.isFinite(point.hour))
      .sort((left, right) => left.hour - right.hour)
    : [];

  return {
    available: true,
    assetId: data.asset_id || null,
    generatedAt: data.generated_at || raw.generatedAt || new Date().toISOString(),
    currentProbability72h: clamp01(data.current_failure_probability_72h),
    historyWindowHours: Number(data.history_window_hours || 48),
    forecastHorizonHours: Number(data.forecast_horizon_hours || 72),
    history,
    forecastPoints,
    model: data.model || null,
    source: data.source || "simulator",
  };
}

function pickSelectedAssetId(assetRows, requestedAssetId) {
  if (!assetRows.length) {
    return null;
  }
  if (requestedAssetId && assetRows.some((asset) => asset.assetId === requestedAssetId)) {
    return requestedAssetId;
  }
  return assetRows[0].assetId;
}

function buildAssetDetailModel(raw, selectedAsset, allAssets) {
  if (!selectedAsset) {
    return {
      selectedAssetId: null,
      title: "No Asset Selected",
      meta: "No asset data available",
      severity: "healthy",
      severityLabel: "Stable",
      healthScore: 0,
      failureProbability72h: 0,
      components: buildFallbackHealth({ asset_id: "none" }).components,
      forecast: buildFallbackForecast("none"),
      sensors: {},
      mapNodes: [],
      maintenanceLog: [],
      isCritical: false,
      isDegraded: false,
    };
  }

  const forecast = raw.forecastByAsset?.[selectedAsset.assetId] ?? buildFallbackForecast(selectedAsset.assetId);
  const sensors = raw.sensorsByAsset?.[selectedAsset.assetId] ?? {};
  const maintenanceLog = raw.maintenanceLogByAsset?.[selectedAsset.assetId] ?? [];

  const mapNodes = allAssets.map((asset) => ({
    assetId: asset.assetId,
    name: asset.name,
    zone: asset.zone,
    lat: Number(asset.location?.lat ?? 0),
    lon: Number(asset.location?.lon ?? 0),
    probability: asset.failureProbability72h,
    severity: asset.severityLabel,
    severityKey: asset.severity,
    selected: asset.assetId === selectedAsset.assetId,
  }));

  return {
    selectedAssetId: selectedAsset.assetId,
    title: selectedAsset.name,
    meta: `${selectedAsset.assetId.toUpperCase()} | ${selectedAsset.zone.toUpperCase()} | ${selectedAsset.type.toUpperCase()}`,
    severity: selectedAsset.severity,
    severityLabel: selectedAsset.severityLabel,
    healthScore: selectedAsset.healthScore,
    failureProbability72h: selectedAsset.failureProbability72h,
    components: selectedAsset.components,
    forecast,
    sensors,
    mapNodes,
    maintenanceLog,
    isCritical: selectedAsset.isCritical,
    isDegraded: selectedAsset.isDegraded,
    anomalyFlag: selectedAsset.anomalyFlag,
    evaluatedAt: selectedAsset.evaluatedAt,
  };
}

function buildNodesModel(raw, allAssets) {
  const firebaseState = raw.firebaseNodes || null;
  const firebaseNodes = Array.isArray(firebaseState?.nodes) ? firebaseState.nodes : [];

  const nodes = firebaseNodes.length
    ? firebaseNodes.map((node) => {
      const matchedAsset = allAssets.find((asset) => asset.assetId === node.assetId) || null;
      return {
        nodeId: node.nodeId,
        assetId: node.assetId,
        assetName: matchedAsset?.name || node.assetName || node.assetId,
        zone: matchedAsset?.zone || node.zone || "global",
        severity: matchedAsset?.severity || "watch",
        severityLabel: matchedAsset?.severityLabel || "Watch",
        failureProbability72h:
            typeof node.failureProbability72h === "number"
              ? clamp01(node.failureProbability72h)
              : clamp01(matchedAsset?.failureProbability72h),
        coordinates: node.location || null,
        lastSeen: node.latestAt || raw.generatedAt || new Date().toISOString(),
        telemetryCount: Object.values(node.telemetry || {}).filter(
          (entry) => entry && Number.isFinite(Number(entry.value)),
        ).length,
        telemetry: node.telemetry || {},
        rawLatest: node.rawLatest || {},
        mappedToAsset: Boolean(matchedAsset),
      };
    })
    : allAssets.map((asset) => {
      const telemetry = raw.sensorsByAsset?.[asset.assetId] ?? {};
      const telemetryCount = Object.values(telemetry).filter(
        (entry) => entry && Number.isFinite(Number(entry.value)),
      ).length;
      const lat = Number(asset.location?.lat ?? NaN);
      const lon = Number(asset.location?.lon ?? NaN);

      return {
        nodeId: asset.assetId,
        assetId: asset.assetId,
        assetName: asset.name,
        zone: asset.zone,
        severity: asset.severity,
        severityLabel: asset.severityLabel,
        failureProbability72h: asset.failureProbability72h,
        coordinates: Number.isFinite(lat) && Number.isFinite(lon) ? { lat, lon } : null,
        lastSeen: asset.evaluatedAt || raw.generatedAt || new Date().toISOString(),
        telemetryCount,
        telemetry,
        rawLatest: {},
        mappedToAsset: true,
      };
    });

  const mappedNodes = nodes.filter((node) => node.mappedToAsset).length;
  return {
    source: String(firebaseState?.connected ? "firebase" : raw.source || "unknown"),
    connected: Boolean(firebaseState?.connected),
    message: firebaseState?.message || "Using platform nodes from API gateway.",
    dbUrl: firebaseState?.dbUrl || "",
    basePath: firebaseState?.basePath || "",
    lastFetchedAt: firebaseState?.lastFetchedAt || null,
    totalNodes: nodes.length,
    mappedNodes,
    nodes,
  };
}

export function createViewModel(raw, { selectedAssetId = null } = {}) {
  const blockchainConnection = raw.blockchainConnection ?? {
    connected: false,
    network: "sepolia",
    expected_chain_id: 11155111,
    chain_id: null,
    latest_block: null,
    contract_address: null,
    contract_deployed: null,
    checked_at: new Date().toISOString(),
    code: null,
    message: "Click 'Connect Sepolia' to verify blockchain access.",
    source: "dashboard",
  };

  const walletConnection = raw.walletConnection ?? emptyWalletStatus();
  const assetRows = normalizeAssets(raw);
  const nextSelectedId = pickSelectedAssetId(assetRows, selectedAssetId);
  const selectedAsset = assetRows.find((asset) => asset.assetId === nextSelectedId) || null;

  const overviewModel = buildOverviewModel(
    assetRows,
    blockchainConnection,
    Boolean(raw.stale),
    raw.error,
    raw.source || "unknown",
    raw.generatedAt || new Date().toISOString(),
  );

  const assetDetailModel = buildAssetDetailModel(raw, selectedAsset, assetRows);
  const nodesModel = buildNodesModel(raw, assetRows);
  const lstmOverviewModel = buildLstmOverviewModel(raw);

  return {
    source: raw.source || "unknown",
    generatedAt: raw.generatedAt || new Date().toISOString(),
    overviewModel,
    assetDetailModel,
    lstmOverviewModel,
    verification: raw.verification || null,
    blockchainConnection,
    walletConnection,
    nodesModel,
    isConnected: Boolean(blockchainConnection.connected),
    isWalletReady: Boolean(walletConnection.connected),
    selectedAssetId: nextSelectedId,
  };
}

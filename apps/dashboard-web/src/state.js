import { CHART_THRESHOLDS, DASHBOARD_CONFIG, SEVERITY_ORDER } from "./config.js";
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

function normalizeEscalationStage(stage) {
  const value = String(stage || "").toLowerCase();
  if (value === "management_notified" || value === "acknowledged" || value === "police_notified" || value === "maintenance_completed") {
    return value;
  }
  return "management_notified";
}

function stageLabel(stage) {
  if (stage === "management_notified") {
    return "Awaiting ACK";
  }
  if (stage === "acknowledged") {
    return "Acknowledged";
  }
  if (stage === "police_notified") {
    return "Police Escalated";
  }
  return "Closed";
}

function stageClass(stage) {
  if (stage === "management_notified") {
    return "status-watch";
  }
  if (stage === "acknowledged") {
    return "status-ok";
  }
  if (stage === "police_notified") {
    return "status-alert";
  }
  return "status-ok";
}

function buildAutomationModel(raw) {
  const now = Date.now();
  const incidents = Array.isArray(raw.automationIncidents) ? raw.automationIncidents : [];

  const items = incidents
    .map((incident) => {
      const stage = normalizeEscalationStage(incident.escalation_stage);
      const deadlineMs = Date.parse(incident.authority_ack_deadline_at || "");
      const remainingSeconds = Number.isFinite(deadlineMs)
        ? Math.floor((deadlineMs - now) / 1000)
        : null;
      const remainingLabel =
        remainingSeconds === null
          ? "-"
          : remainingSeconds <= 0
            ? "Expired"
            : `${Math.floor(remainingSeconds / 60)}m ${remainingSeconds % 60}s`;

      return {
        workflowId: incident.workflow_id,
        assetId: incident.asset_id,
        riskPriority: String(incident.risk_priority || "low"),
        stage,
        stageLabel: stageLabel(stage),
        stageClass: stageClass(stage),
        status: String(incident.status || "inspection_requested"),
        triggerReason: String(incident.trigger_reason || ""),
        authorityNotifiedAt: incident.authority_notified_at || null,
        authorityAckDeadlineAt: incident.authority_ack_deadline_at || null,
        acknowledgedAt: incident.acknowledged_at || null,
        acknowledgedBy: incident.acknowledged_by || null,
        ackNotes: incident.ack_notes || null,
        policeNotifiedAt: incident.police_notified_at || null,
        inspectionTicketId: incident.inspection_ticket_id || null,
        maintenanceId: incident.maintenance_id || null,
        canAcknowledge: stage === "management_notified",
        deadlineRemainingSeconds: remainingSeconds,
        deadlineRemainingLabel: remainingLabel,
        createdAt: incident.created_at || null,
        updatedAt: incident.updated_at || null,
      };
    })
    .sort((left, right) => {
      const rightTime = Date.parse(right.updatedAt || right.createdAt || 0);
      const leftTime = Date.parse(left.updatedAt || left.createdAt || 0);
      return rightTime - leftTime;
    });

  return {
    incidents: items,
    openCount: items.filter((incident) => incident.stage === "management_notified").length,
    escalatedCount: items.filter((incident) => incident.stage === "police_notified").length,
  };
}

function normalizeEvidenceStatus(status) {
  const value = String(status || "").toLowerCase();
  if (value === "upload_pending" || value === "finalized" || value === "deleted") {
    return value;
  }
  return "upload_pending";
}

function resolveVerificationStatus(raw, verification) {
  const fromVerification = String(verification?.verification_status || "").toLowerCase();
  if (fromVerification) {
    return fromVerification;
  }
  const fromState = String(raw?.verificationState?.verification_status || "").toLowerCase();
  if (fromState) {
    return fromState;
  }
  return "awaiting_evidence";
}

function buildEvidenceModel(raw, activeMaintenanceId, selectedAssetId) {
  const evidenceItems = Array.isArray(raw.evidenceByMaintenanceId?.[activeMaintenanceId])
    ? raw.evidenceByMaintenanceId[activeMaintenanceId]
    : [];
  const normalizedItems = evidenceItems
    .map((item) => ({
      evidenceId: item.evidence_id,
      maintenanceId: item.maintenance_id,
      assetId: item.asset_id,
      filename: item.filename,
      contentType: item.content_type,
      sizeBytes: Number(item.size_bytes ?? 0),
      storageUri: item.storage_uri || "-",
      sha256Hex: item.sha256_hex || null,
      uploadedBy: item.uploaded_by || "-",
      uploadedAt: item.uploaded_at || null,
      finalizedAt: item.finalized_at || null,
      status: normalizeEvidenceStatus(item.status),
      category: item.category || null,
      notes: item.notes || null,
    }))
    .filter((item) => Boolean(item.evidenceId))
    .sort((left, right) => left.evidenceId.localeCompare(right.evidenceId));

  const finalizedCount = normalizedItems.filter((item) => item.status === "finalized").length;
  const verificationStatus = resolveVerificationStatus(raw, raw.verification);
  const lockStates = new Set(["pending", "submitted", "confirmed"]);
  const hasMaintenance = Boolean(activeMaintenanceId);
  const canUpload = hasMaintenance && !lockStates.has(verificationStatus);
  const canSubmit = hasMaintenance && finalizedCount > 0 && !lockStates.has(verificationStatus);

  return {
    maintenanceId: activeMaintenanceId || null,
    selectedAssetId: selectedAssetId || null,
    verificationStatus,
    items: normalizedItems,
    totalCount: normalizedItems.length,
    finalizedCount,
    pendingCount: normalizedItems.filter((item) => item.status === "upload_pending").length,
    canUpload,
    canSubmit,
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
  const automationModel = buildAutomationModel(raw);
  const fallbackMaintenanceId =
    typeof DASHBOARD_CONFIG.maintenanceIdFallback === "string" && DASHBOARD_CONFIG.maintenanceIdFallback.trim()
      ? DASHBOARD_CONFIG.maintenanceIdFallback.trim()
      : null;
  const activeMaintenanceId =
    raw.activeMaintenanceId || raw.verification?.maintenance_id || fallbackMaintenanceId || null;
  const evidenceModel = buildEvidenceModel(raw, activeMaintenanceId, nextSelectedId);
  const nodesModel = buildNodesModel(raw, assetRows);
  const lstmOverviewModel = buildLstmOverviewModel(raw);

  return {
    source: raw.source || "unknown",
    generatedAt: raw.generatedAt || new Date().toISOString(),
    overviewModel,
    assetDetailModel,
    lstmOverviewModel,
    verification: raw.verification || null,
    activeMaintenanceId,
    evidenceModel,
    automationModel,
    blockchainConnection,
    walletConnection,
    nodesModel,
    isConnected: Boolean(blockchainConnection.connected),
    isWalletReady: Boolean(walletConnection.connected),
    selectedAssetId: nextSelectedId,
  };
}

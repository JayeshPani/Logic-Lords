import { DASHBOARD_CONFIG, RISK_COLOR_BY_LEVEL, SEVERITY_COLOR, UI_ERROR_HINTS } from "./config.js";
import {
  renderForecastChart,
  renderHealthGauge,
  renderMapLegend,
  renderMicroBars,
  renderRiskBars,
  renderRiskMap,
} from "./visualization.js";
import { severityLabel, toPercent } from "./state.js";

function byId(id) {
  return document.getElementById(id);
}

function setText(id, value) {
  const element = byId(id);
  if (element) {
    element.textContent = value;
  }
}

function formatIso(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return "-";
  }
  return date.toISOString().replace("T", " ").slice(0, 19);
}

function shortHash(value) {
  if (!value || value.length < 18) {
    return value || "-";
  }
  return `${value.slice(0, 10)}...${value.slice(-10)}`;
}

function severityClass(severity) {
  if (severity === "critical") {
    return "severity-critical";
  }
  if (severity === "warning") {
    return "severity-warning";
  }
  if (severity === "watch") {
    return "severity-watch";
  }
  return "severity-healthy";
}

function connectionClass(connection) {
  if (connection.connected) {
    return "status-ok";
  }
  if (connection.chain_id && connection.chain_id !== connection.expected_chain_id) {
    return "status-watch";
  }
  return "status-alert";
}

function walletClass(connection) {
  if (connection.connected) {
    return "status-ok";
  }
  if (connection.chain_id && connection.chain_id !== 11155111) {
    return "status-watch";
  }
  return "status-alert";
}

function statusClass(status) {
  const normalized = String(status || "").toLowerCase();
  if (normalized.includes("confirm") || normalized.includes("calibrat") || normalized.includes("inspect") || normalized.includes("analyzed")) {
    return "status-ok";
  }
  if (
    normalized.includes("pending") ||
    normalized.includes("schedul") ||
    normalized.includes("alert") ||
    normalized.includes("submit")
  ) {
    return "status-watch";
  }
  return "status-alert";
}

function evidenceStatusClass(status) {
  const normalized = String(status || "").toLowerCase();
  if (normalized === "finalized") {
    return "status-ok";
  }
  if (normalized === "upload_pending") {
    return "status-watch";
  }
  return "status-alert";
}

function formatBytes(sizeBytes) {
  const value = Number(sizeBytes ?? 0);
  if (!Number.isFinite(value) || value <= 0) {
    return "-";
  }

  const units = ["B", "KB", "MB", "GB"];
  let index = 0;
  let scaled = value;
  while (scaled >= 1024 && index < units.length - 1) {
    scaled /= 1024;
    index += 1;
  }
  const precision = index === 0 ? 0 : 1;
  return `${scaled.toFixed(precision)} ${units[index]}`;
}

function renderSensorCards(sensors) {
  const config = [
    { key: "strain", valueId: "strain-value", deltaId: "strain-delta", barsId: "strain-bars", color: "#00d4ff" },
    { key: "vibration", valueId: "vibration-value", deltaId: "vibration-delta", barsId: "vibration-bars", color: "#00ff88" },
    { key: "temperature", valueId: "temperature-value", deltaId: "temperature-delta", barsId: "temperature-bars", color: "#fb923c" },
    { key: "tilt", valueId: "tilt-value", deltaId: "tilt-delta", barsId: "tilt-bars", color: "#3b82f6" },
  ];

  config.forEach((item) => {
    const sensor = sensors?.[item.key];
    if (!sensor) {
      setText(item.valueId, "-");
      setText(item.deltaId, "-");
      renderMicroBars(byId(item.barsId), [], item.color);
      return;
    }

    setText(item.valueId, `${Number(sensor.value).toFixed(sensor.unit === "deg" ? 2 : 1)} ${sensor.unit}`);
    setText(item.deltaId, sensor.delta || "-");
    renderMicroBars(byId(item.barsId), sensor.samples || [], item.color);
  });
}

function renderMaintenanceRows(rows) {
  const body = byId("maintenance-log-body");
  if (!body) {
    return;
  }
  body.innerHTML = "";

  (rows || []).forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="mono">${formatIso(row.timestamp)}</td>
      <td class="strong">${row.unit}</td>
      <td>${row.operator}</td>
      <td><span class="status-chip ${statusClass(row.status)}">${row.status}</span></td>
      <td class="align-right">${row.verified ? "<iconify-icon icon='lucide:check-circle' class='ok-icon'></iconify-icon>" : "<iconify-icon icon='lucide:clock-4' class='pending-icon'></iconify-icon>"}</td>
    `;
    body.appendChild(tr);
  });
}

function renderEvidenceRows(items) {
  const body = byId("evidence-list-body");
  if (!body) {
    return;
  }
  body.innerHTML = "";

  if (!Array.isArray(items) || items.length === 0) {
    const row = document.createElement("tr");
    row.innerHTML = "<td colspan='5' class='mono'>No evidence uploaded yet.</td>";
    body.appendChild(row);
    return;
  }

  items.forEach((item) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td class="mono">${item.evidenceId}</td>
      <td class="strong">${item.filename}</td>
      <td><span class="status-chip ${evidenceStatusClass(item.status)}">${String(item.status || "-").toUpperCase()}</span></td>
      <td class="mono hash">${shortHash(item.sha256Hex || "-")}</td>
      <td class="align-right mono">${formatBytes(item.sizeBytes)}</td>
    `;
    body.appendChild(row);
  });
}

export function renderEvidencePanel(
  evidenceModel,
  { selectedFileName = null, uploadInFlight = false, submitInFlight = false } = {},
) {
  setText("evidence-maintenance-id", evidenceModel?.maintenanceId || "-");
  setText("evidence-verification-status", String(evidenceModel?.verificationStatus || "-").toUpperCase());
  setText("evidence-file-selected", selectedFileName || "No file selected");
  renderEvidenceRows(evidenceModel?.items || []);

  const statusElement = byId("evidence-status-message");
  if (statusElement) {
    if (!evidenceModel?.maintenanceId) {
      statusElement.textContent = "No maintenance record selected yet. Complete maintenance first.";
      statusElement.className = "map-status map-status-warn";
    } else if ((evidenceModel?.finalizedCount || 0) === 0) {
      statusElement.textContent = "Upload at least one finalized evidence file to enable verification submit.";
      statusElement.className = "map-status map-status-quiet";
    } else if (evidenceModel?.canSubmit) {
      statusElement.textContent = `${evidenceModel.finalizedCount} finalized evidence file(s) ready.`;
      statusElement.className = "map-status map-status-ok";
    } else {
      statusElement.textContent = `Verification state is ${String(evidenceModel?.verificationStatus || "unknown").toUpperCase()}.`;
      statusElement.className = "map-status map-status-warn";
    }
  }

  const uploadButton = byId("evidence-upload-btn");
  if (uploadButton) {
    const canUpload = Boolean(evidenceModel?.canUpload);
    uploadButton.disabled = uploadInFlight || !canUpload;
    if (!canUpload) {
      uploadButton.textContent = "Upload Locked";
    } else if (uploadInFlight) {
      uploadButton.textContent = "Uploading...";
    } else {
      uploadButton.textContent = "Upload & Finalize Evidence";
    }
  }

  const submitButton = byId("submit-verification-btn");
  if (submitButton) {
    const canSubmit = Boolean(evidenceModel?.canSubmit);
    submitButton.disabled = submitInFlight || !canSubmit;
    if (!canSubmit) {
      submitButton.textContent = "Submit Unavailable";
    } else if (submitInFlight) {
      submitButton.textContent = "Submitting...";
    } else {
      submitButton.textContent = "Submit Verification";
    }
  }
}

export function renderAutomationPanel(automationModel, onAcknowledgeIncident, ackInFlightIds = new Set()) {
  const list = byId("automation-incident-list");
  const status = byId("automation-status-message");
  if (!list || !status) {
    return;
  }

  list.innerHTML = "";
  const incidents = automationModel?.incidents || [];
  if (!incidents.length) {
    status.textContent = "No active automation incidents.";
    status.className = "map-status map-status-quiet";
    return;
  }

  status.textContent = `${incidents.length} incident(s) tracked | awaiting ACK: ${automationModel?.openCount || 0} | police escalated: ${automationModel?.escalatedCount || 0}`;
  status.className = "map-status map-status-ok";

  incidents.forEach((incident) => {
    const row = document.createElement("article");
    row.className = "incident-row";

    const ackBusy = ackInFlightIds.has(incident.workflowId);
    const ackButton = incident.canAcknowledge
      ? `<button class="incident-ack-btn" data-ack-workflow-id="${incident.workflowId}" ${ackBusy ? "disabled" : ""}>${ackBusy ? "ACK..." : "Acknowledge"}</button>`
      : "";

    row.innerHTML = `
      <div class="incident-row-head">
        <div>
          <div class="incident-title">${incident.assetId}</div>
          <div class="incident-meta mono">${incident.workflowId}</div>
        </div>
        <span class="timeline-value ${incident.stageClass}">${incident.stageLabel}</span>
      </div>
      <div class="incident-grid">
        <div class="incident-cell">
          <span class="incident-label">Priority</span>
          <span class="incident-value mono">${incident.riskPriority.toUpperCase()}</span>
        </div>
        <div class="incident-cell">
          <span class="incident-label">ACK Deadline</span>
          <span class="incident-value mono">${incident.deadlineRemainingLabel}</span>
        </div>
        <div class="incident-cell">
          <span class="incident-label">Inspection</span>
          <span class="incident-value mono">${incident.inspectionTicketId || "-"}</span>
        </div>
        <div class="incident-cell">
          <span class="incident-label">Acknowledged By</span>
          <span class="incident-value">${incident.acknowledgedBy || "-"}</span>
        </div>
      </div>
      <div class="incident-actions">${ackButton}</div>
    `;

    const button = row.querySelector("[data-ack-workflow-id]");
    if (button && typeof onAcknowledgeIncident === "function") {
      button.addEventListener("click", () => {
        if (!button.hasAttribute("disabled")) {
          onAcknowledgeIncident(incident.workflowId);
        }
      });
    }

    list.appendChild(row);
  });
}

export function renderOverviewKpis(overviewModel) {
  setText("kpi-overall-health-value", overviewModel ? toPercent(overviewModel.overallHealth, 0) : "-");
  setText("kpi-critical-assets-value", overviewModel ? String(overviewModel.criticalAssets) : "-");
  setText("kpi-system-risk-value", overviewModel ? toPercent(overviewModel.systemFailureRisk, 0) : "-");
  setText("kpi-ledger-reachability-value", overviewModel?.isConnected ? "CONNECTED" : "DISCONNECTED");

  setText("status-data-source", String(overviewModel?.source || "unknown").toUpperCase());
  setText("status-asset-count", String(overviewModel?.totalAssets ?? 0));
  setText("status-critical-count", String(overviewModel?.criticalAssets ?? 0));
  setText("status-sync-time", formatIso(overviewModel?.generatedAt));

  const staleBadge = byId("stale-badge");
  if (staleBadge) {
    if (overviewModel?.stale) {
      staleBadge.textContent = `STALE DATA: ${overviewModel.staleReason || "refresh failed"}`;
      staleBadge.className = "stale-badge show";
    } else {
      staleBadge.textContent = "";
      staleBadge.className = "stale-badge";
    }
  }
}

export function renderTriageList(overviewModel, selectedAssetId, onSelectAsset) {
  const list = byId("triage-list");
  if (!list) {
    return;
  }
  list.innerHTML = "";

  (overviewModel?.triageAssets || []).forEach((asset, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `triage-row ${asset.assetId === selectedAssetId ? "triage-row-selected" : ""}`;
    button.setAttribute("role", "option");
    button.setAttribute("aria-selected", asset.assetId === selectedAssetId ? "true" : "false");
    button.dataset.assetId = asset.assetId;
    button.innerHTML = `
      <span class="triage-rank mono">#${index + 1}</span>
      <span class="triage-name">${asset.name}</span>
      <span class="triage-zone mono">${asset.zone.toUpperCase()}</span>
      <span class="triage-severity ${severityClass(asset.severity)}">${asset.severityLabel}</span>
      <span class="triage-risk mono">${toPercent(asset.failureProbability72h, 0)}</span>
    `;

    button.addEventListener("click", () => {
      if (typeof onSelectAsset === "function") {
        onSelectAsset(asset.assetId);
      }
    });

    list.appendChild(button);
  });
}

export function renderSelectedAssetHeader(assetDetailModel) {
  setText("selected-asset-title", assetDetailModel?.title || "No Asset Selected");
  setText("selected-asset-meta", assetDetailModel?.meta || "-");

  const chip = byId("selected-asset-severity");
  if (chip) {
    chip.textContent = assetDetailModel?.severityLabel || "Stable";
    chip.className = `severity-chip ${severityClass(assetDetailModel?.severity || "healthy")}`;
  }
}

export function renderSelectedAssetPanels(assetDetailModel) {
  const score = Number(assetDetailModel?.healthScore ?? 0);
  const probability = Number(assetDetailModel?.failureProbability72h ?? 0);

  setText("selected-asset-health", toPercent(score, 0));
  setText("health-score", score.toFixed(2));
  setText("failure-probability", `72h Failure: ${toPercent(probability, 0)}`);

  const statusBadge = byId("health-status-badge");
  if (statusBadge) {
    const badge = severityLabel(assetDetailModel?.severity || probability);
    statusBadge.textContent = `${badge} Status`;
    statusBadge.style.color = SEVERITY_COLOR[assetDetailModel?.severity] || RISK_COLOR_BY_LEVEL.High;
  }

  renderHealthGauge(score, byId("health-gauge-ring"));
  renderRiskBars(byId("selected-asset-components"), assetDetailModel?.components || {});
  renderForecastChart(byId("selected-asset-forecast"), assetDetailModel?.forecast?.points || []);
  renderSensorCards(assetDetailModel?.sensors || {});
}

export function renderLedgerWalletPanel(
  blockchainConnection,
  walletConnection,
  verification,
  { isTrackingVerification = false, activeMaintenanceId = null } = {},
) {
  const maintenanceId = verification?.maintenance_id || activeMaintenanceId || null;
  setText("ledger-status", String(verification?.verification_status || "-").toUpperCase());
  setText("ledger-maintenance-id", maintenanceId || "-");
  setText("ledger-tx", shortHash(verification?.tx_hash));
  setText("ledger-evidence", shortHash(verification?.evidence_hash));
  setText(
    "ledger-confirmations",
    `${Number(verification?.confirmations ?? 0)}/${Number(verification?.required_confirmations ?? 0)}`,
  );
  setText("ledger-submitted-at", formatIso(verification?.submitted_at));
  setText("ledger-confirmed-at", formatIso(verification?.confirmed_at || verification?.verified_at));
  setText("ledger-failure-reason", verification?.failure_reason || "-");

  setText("ledger-connection", blockchainConnection?.connected ? "CONNECTED" : "DISCONNECTED");
  setText("ledger-network", blockchainConnection?.network || "sepolia");
  setText("ledger-latest-block", blockchainConnection?.latest_block ?? "-");

  const ledgerMessage = byId("ledger-connect-message");
  if (ledgerMessage) {
    const hint = blockchainConnection?.code ? UI_ERROR_HINTS[blockchainConnection.code] : null;
    ledgerMessage.textContent = hint ? `${blockchainConnection.message} ${hint}` : blockchainConnection?.message || "No Sepolia status available.";
    ledgerMessage.className = `connection-message ${connectionClass(blockchainConnection || {})}`;
  }

  setText("wallet-connection", walletConnection?.connected ? "CONNECTED" : "DISCONNECTED");
  setText("wallet-address", shortHash(walletConnection?.wallet_address));
  setText("wallet-chain", walletConnection?.chain_id ?? "-");

  const walletMessage = byId("wallet-connect-message");
  if (walletMessage) {
    walletMessage.textContent = walletConnection?.message || "No wallet status available.";
    walletMessage.className = `connection-message ${walletClass(walletConnection || {})}`;
  }

  const trackButton = byId("track-verification-btn");
  if (trackButton) {
    const canTrackVerification = Boolean(maintenanceId);
    trackButton.disabled = isTrackingVerification || !canTrackVerification;
    if (!canTrackVerification) {
      trackButton.textContent = "No Verification Yet";
    } else if (isTrackingVerification) {
      trackButton.textContent = "Tracking...";
    } else {
      trackButton.textContent = "Track Verification";
    }
  }

  const timeline = byId("ledger-status-timeline");
  if (timeline) {
    timeline.innerHTML = "";
    const events = [
      {
        label: "Sepolia Reachability",
        value: blockchainConnection?.connected ? "PASS" : "FAIL",
        className: blockchainConnection?.connected ? "status-ok" : "status-alert",
      },
      {
        label: "Wallet Identity",
        value: walletConnection?.connected ? "READY" : "PENDING",
        className: walletConnection?.connected ? "status-ok" : "status-watch",
      },
      {
        label: "Maintenance Verification",
        value: String(verification?.verification_status || "pending").toUpperCase(),
        className: statusClass(verification?.verification_status),
      },
      {
        label: "Confirmations",
        value: `${Number(verification?.confirmations ?? 0)}/${Number(verification?.required_confirmations ?? 0)}`,
        className:
          Number(verification?.required_confirmations ?? 0) > 0 &&
          Number(verification?.confirmations ?? 0) >= Number(verification?.required_confirmations ?? 0)
            ? "status-ok"
            : "status-watch",
      },
    ];

    events.forEach((event) => {
      const item = document.createElement("li");
      item.className = "timeline-item";
      item.innerHTML = `<span>${event.label}</span><span class="timeline-value ${event.className}">${event.value}</span>`;
      timeline.appendChild(item);
    });
  }
}

export function renderDashboard(viewModel, options = {}) {
  const onSelectAsset = options.onSelectAsset;
  const onAcknowledgeIncident = options.onAcknowledgeIncident;
  const activeTab = options.activeTab || "overview";
  const ackInFlightIds = options.ackInFlightIds || new Set();
  const isTrackingVerification = Boolean(options.isTrackingVerification);
  const selectedEvidenceFileName = options.selectedEvidenceFileName || null;
  const isUploadingEvidence = Boolean(options.isUploadingEvidence);
  const isSubmittingVerification = Boolean(options.isSubmittingVerification);
  setText("command-center-value", DASHBOARD_CONFIG.commandCenter);
  setText(
    "weather-temp",
    `${DASHBOARD_CONFIG.weather.temperatureC}C / HUM ${DASHBOARD_CONFIG.weather.humidityPct}%`,
  );
  setText(
    "weather-wind",
    `${DASHBOARD_CONFIG.weather.windKmh}KM/H ${DASHBOARD_CONFIG.weather.windDirection}`,
  );
  renderOverviewKpis(viewModel.overviewModel);
  renderTriageList(viewModel.overviewModel, viewModel.selectedAssetId, onSelectAsset);
  renderSelectedAssetHeader(viewModel.assetDetailModel);
  renderSelectedAssetPanels(viewModel.assetDetailModel);
  renderLedgerWalletPanel(viewModel.blockchainConnection, viewModel.walletConnection, viewModel.verification, {
    isTrackingVerification,
    activeMaintenanceId: viewModel.activeMaintenanceId,
  });
  renderAutomationPanel(viewModel.automationModel, onAcknowledgeIncident, ackInFlightIds);
  renderRiskMap(byId("risk-map"), viewModel.assetDetailModel?.mapNodes || [], {
    selectedAssetId: viewModel.selectedAssetId,
    onSelectAsset,
    active: activeTab === "map",
    statusElement: byId("risk-map-status"),
  });
  renderMapLegend(byId("risk-map-legend"));
  renderMaintenanceRows(viewModel.assetDetailModel?.maintenanceLog || []);
  renderEvidencePanel(viewModel.evidenceModel, {
    selectedFileName: selectedEvidenceFileName,
    uploadInFlight: isUploadingEvidence,
    submitInFlight: isSubmittingVerification,
  });
}

export function renderClock(now = new Date()) {
  const dateLabel = now.toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "2-digit",
  });

  const timeLabel = `${now.toISOString().slice(11, 19)} UTC`;
  setText("clock-date", dateLabel);
  setText("clock-time", timeLabel);
}

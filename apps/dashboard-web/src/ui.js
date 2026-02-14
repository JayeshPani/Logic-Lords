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
  if (normalized.includes("pending") || normalized.includes("schedul") || normalized.includes("alert")) {
    return "status-watch";
  }
  return "status-alert";
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

export function renderLedgerWalletPanel(blockchainConnection, walletConnection, verification) {
  setText("ledger-status", String(verification?.verification_status || "-").toUpperCase());
  setText("ledger-tx", shortHash(verification?.tx_hash));
  setText("ledger-evidence", shortHash(verification?.evidence_hash));

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
  const activeTab = options.activeTab || "overview";
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
  renderLedgerWalletPanel(viewModel.blockchainConnection, viewModel.walletConnection, viewModel.verification);
  renderRiskMap(byId("risk-map"), viewModel.assetDetailModel?.mapNodes || [], {
    selectedAssetId: viewModel.selectedAssetId,
    onSelectAsset,
    active: activeTab === "map",
    statusElement: byId("risk-map-status"),
  });
  renderMapLegend(byId("risk-map-legend"));
  renderMaintenanceRows(viewModel.assetDetailModel?.maintenanceLog || []);
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

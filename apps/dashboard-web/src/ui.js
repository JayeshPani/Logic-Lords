import { DASHBOARD_CONFIG, RISK_COLOR_BY_LEVEL, SEVERITY_COLOR } from "./config.js";
import { renderForecastChart, renderHealthGauge, renderMicroBars, renderRiskBars, renderRiskMap } from "./visualization.js";
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

function connectionClass(connection) {
  if (connection.connected) {
    return "ok";
  }
  if (connection.chain_id && connection.chain_id !== connection.expected_chain_id) {
    return "warn";
  }
  return "error";
}

function walletClass(connection) {
  if (connection.connected) {
    return "ok";
  }
  if (connection.chain_id && connection.chain_id !== 11155111) {
    return "warn";
  }
  return "error";
}

function statusClass(status) {
  const normalized = String(status || "").toLowerCase();
  if (normalized.includes("confirm") || normalized.includes("calibrat") || normalized.includes("inspect")) {
    return "status-ok";
  }
  if (normalized.includes("pending") || normalized.includes("schedul")) {
    return "status-watch";
  }
  return "status-alert";
}

function renderMaintenanceRows(rows) {
  const body = byId("maintenance-log-body");
  if (!body) {
    return;
  }
  body.innerHTML = "";

  rows.forEach((row) => {
    const tr = document.createElement("tr");

    tr.innerHTML = `
      <td class="mono">${formatIso(row.timestamp)}</td>
      <td class="strong">${row.unit}</td>
      <td>${row.operator}</td>
      <td><span class="status-pill ${statusClass(row.status)}">${row.status}</span></td>
      <td class="align-right">${row.verified ? "<iconify-icon icon='lucide:check-circle' class='ok-icon'></iconify-icon>" : "<iconify-icon icon='lucide:clock-4' class='pending-icon'></iconify-icon>"}</td>
    `;

    body.appendChild(tr);
  });
}

function renderSensorCards(sensors) {
  const sensorConfig = [
    { key: "strain", valueId: "strain-value", deltaId: "strain-delta", barsId: "strain-bars", color: "#00d4ff" },
    {
      key: "vibration",
      valueId: "vibration-value",
      deltaId: "vibration-delta",
      barsId: "vibration-bars",
      color: "#00ff88",
    },
    {
      key: "temperature",
      valueId: "temperature-value",
      deltaId: "temperature-delta",
      barsId: "temperature-bars",
      color: "#fb923c",
    },
    { key: "tilt", valueId: "tilt-value", deltaId: "tilt-delta", barsId: "tilt-bars", color: "#3b82f6" },
  ];

  sensorConfig.forEach((item) => {
    const sensor = sensors[item.key];
    if (!sensor) {
      return;
    }

    const valueText = `${sensor.value.toFixed(sensor.unit === "deg" ? 2 : 1)} ${sensor.unit}`;
    setText(item.valueId, valueText);
    setText(item.deltaId, sensor.delta);
    renderMicroBars(byId(item.barsId), sensor.samples, item.color);
  });
}

export function renderBlockchainConnectionStatus(connection) {
  if (!connection) {
    return;
  }

  setText("ledger-connection", connection.connected ? "CONNECTED" : "DISCONNECTED");
  setText("ledger-network", connection.network || "sepolia");
  setText("ledger-latest-block", connection.latest_block ?? "-");

  const messageElement = byId("ledger-connect-message");
  if (messageElement) {
    messageElement.textContent = connection.message || "No Sepolia status available.";
    messageElement.className = `ledger-connect-message ${connectionClass(connection)}`;
  }
}

export function renderWalletConnectionStatus(walletConnection) {
  if (!walletConnection) {
    return;
  }

  setText("wallet-connection", walletConnection.connected ? "CONNECTED" : "DISCONNECTED");
  setText("wallet-address", shortHash(walletConnection.wallet_address));
  setText("wallet-chain", walletConnection.chain_id ?? "-");

  const messageElement = byId("wallet-connect-message");
  if (messageElement) {
    messageElement.textContent = walletConnection.message || "No wallet status available.";
    messageElement.className = `ledger-connect-message ${walletClass(walletConnection)}`;
  }
}

export function renderDashboard(viewModel) {
  setText("command-center-value", DASHBOARD_CONFIG.commandCenter);
  setText(
    "weather-temp",
    `${DASHBOARD_CONFIG.weather.temperatureC}C / HUM ${DASHBOARD_CONFIG.weather.humidityPct}%`,
  );
  setText(
    "weather-wind",
    `${DASHBOARD_CONFIG.weather.windKmh}KM/H ${DASHBOARD_CONFIG.weather.windDirection}`,
  );

  const dataSource = String(viewModel.source || "unknown").toUpperCase();
  setText("status-data-source", dataSource);
  setText("status-asset-count", String(viewModel.assets.length));
  setText("status-critical-count", String(viewModel.totals.critical));
  setText("status-sync-time", formatIso(viewModel.generatedAt));

  const score = Number(viewModel.health.health_score ?? 0);
  const probability = Number(viewModel.health.failure_probability_72h ?? 0);
  setText("health-score", score.toFixed(2));
  setText("failure-probability", `72h Failure: ${toPercent(probability, 0)}`);

  const statusBadge = byId("health-status-badge");
  if (statusBadge) {
    const status = severityLabel(probability);
    statusBadge.textContent = `${status} Status`;
    statusBadge.style.color = SEVERITY_COLOR[viewModel.health.severity] || RISK_COLOR_BY_LEVEL[viewModel.health.risk_level] || "#00ff88";
  }

  renderHealthGauge(score, byId("health-gauge-ring"));
  renderRiskBars(byId("risk-component-bars"), viewModel.health.components);
  renderForecastChart(byId("forecast-chart"), viewModel.forecast.points || []);
  renderSensorCards(viewModel.sensors);
  renderRiskMap(byId("risk-map"), viewModel.mapNodes);

  setText("ledger-status", String(viewModel.verification.verification_status || "-").toUpperCase());
  setText("ledger-tx", shortHash(viewModel.verification.tx_hash));
  setText("ledger-evidence", shortHash(viewModel.verification.evidence_hash));
  renderBlockchainConnectionStatus(viewModel.blockchainConnection);
  renderWalletConnectionStatus(viewModel.walletConnection);

  renderMaintenanceRows(viewModel.maintenanceLog);
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

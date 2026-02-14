import { CHART_THRESHOLDS } from "./config.js";
import { emptyWalletStatus } from "./wallet.js";

export function toPercent(value, digits = 0) {
  return `${(Number(value) * 100).toFixed(digits)}%`;
}

export function severityLabel(probability) {
  const value = Number(probability ?? 0);
  if (value >= CHART_THRESHOLDS.critical) {
    return "Critical";
  }
  if (value >= CHART_THRESHOLDS.warning) {
    return "Warning";
  }
  if (value >= CHART_THRESHOLDS.watch) {
    return "Watch";
  }
  return "Stable";
}

function countBySeverity(assets, primaryHealth) {
  const probabilities = assets.map((_asset) => Number(primaryHealth.failure_probability_72h ?? 0));
  const critical = probabilities.filter((probability) => probability >= CHART_THRESHOLDS.critical).length;
  const high = probabilities.filter(
    (probability) => probability >= CHART_THRESHOLDS.warning && probability < CHART_THRESHOLDS.critical,
  ).length;
  const watch = probabilities.filter(
    (probability) => probability >= CHART_THRESHOLDS.watch && probability < CHART_THRESHOLDS.warning,
  ).length;
  return { critical, high, watch };
}

function buildMapNodes(assets, health) {
  const baseProbability = Number(health.failure_probability_72h ?? 0.3);

  return assets.map((asset, index) => {
    const multiplier = 0.72 + (index % 4) * 0.13;
    const probability = Math.max(0.05, Math.min(0.98, baseProbability * multiplier));

    return {
      assetId: asset.asset_id,
      name: asset.name,
      zone: asset.zone,
      probability,
      lat: Number(asset.location.lat),
      lon: Number(asset.location.lon),
      severity: severityLabel(probability),
    };
  });
}

export function createViewModel(raw) {
  const assets = raw.assets ?? [];
  const health = raw.health ?? {};
  const forecast = raw.forecast ?? { points: [] };
  const verification = raw.verification ?? {};
  const blockchainConnection = raw.blockchainConnection ?? {
    connected: false,
    network: "sepolia",
    expected_chain_id: 11155111,
    chain_id: null,
    latest_block: null,
    contract_address: verification.contract_address ?? null,
    contract_deployed: null,
    checked_at: new Date().toISOString(),
    message: "Click 'Connect Sepolia' to verify blockchain access.",
    source: "dashboard",
  };
  const walletConnection = raw.walletConnection ?? emptyWalletStatus();
  const sensors = raw.sensors ?? {};

  const totals = countBySeverity(assets, health);

  return {
    source: raw.source ?? "unknown",
    gatewayHealth: raw.gatewayHealth ?? {},
    assets,
    health,
    forecast,
    verification,
    blockchainConnection,
    walletConnection,
    maintenanceLog: raw.maintenanceLog ?? [],
    sensors,
    mapNodes: buildMapNodes(assets, health),
    totals,
    generatedAt: new Date().toISOString(),
  };
}

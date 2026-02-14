const NOW = new Date();

function isoMinusHours(hours) {
  return new Date(NOW.getTime() - hours * 60 * 60 * 1000).toISOString();
}

const assets = [
  {
    asset_id: "asset_w12_bridge_0042",
    name: "West Sector Bridge 42",
    asset_type: "bridge",
    status: "active",
    zone: "w12",
    location: { lat: 19.0728, lon: 72.8826 },
  },
  {
    asset_id: "asset_w12_road_0101",
    name: "West Sector Road 101",
    asset_type: "road",
    status: "maintenance",
    zone: "w12",
    location: { lat: 19.081, lon: 72.891 },
  },
  {
    asset_id: "asset_c02_bridge_0188",
    name: "Central Corridor Bridge 188",
    asset_type: "bridge",
    status: "active",
    zone: "c02",
    location: { lat: 19.0605, lon: 72.9004 },
  },
];

const healthByAsset = {
  asset_w12_bridge_0042: {
    asset_id: "asset_w12_bridge_0042",
    evaluated_at: isoMinusHours(1),
    health_score: 0.84,
    risk_level: "High",
    failure_probability_72h: 0.67,
    anomaly_flag: 1,
    severity: "warning",
    components: {
      mechanical_stress: 0.82,
      thermal_stress: 0.61,
      fatigue: 0.76,
      environmental_exposure: 0.58,
    },
  },
  asset_w12_road_0101: {
    asset_id: "asset_w12_road_0101",
    evaluated_at: isoMinusHours(2),
    health_score: 0.73,
    risk_level: "Moderate",
    failure_probability_72h: 0.44,
    anomaly_flag: 0,
    severity: "watch",
    components: {
      mechanical_stress: 0.52,
      thermal_stress: 0.43,
      fatigue: 0.47,
      environmental_exposure: 0.4,
    },
  },
  asset_c02_bridge_0188: {
    asset_id: "asset_c02_bridge_0188",
    evaluated_at: isoMinusHours(1),
    health_score: 0.61,
    risk_level: "Critical",
    failure_probability_72h: 0.83,
    anomaly_flag: 1,
    severity: "critical",
    components: {
      mechanical_stress: 0.9,
      thermal_stress: 0.71,
      fatigue: 0.88,
      environmental_exposure: 0.74,
    },
  },
};

const forecastByAsset = {
  asset_w12_bridge_0042: {
    asset_id: "asset_w12_bridge_0042",
    horizon_hours: 72,
    confidence: 0.81,
    points: [
      { hour: 0, probability: 0.41 },
      { hour: 8, probability: 0.47 },
      { hour: 16, probability: 0.53 },
      { hour: 24, probability: 0.59 },
      { hour: 32, probability: 0.63 },
      { hour: 40, probability: 0.69 },
      { hour: 48, probability: 0.72 },
      { hour: 56, probability: 0.74 },
      { hour: 64, probability: 0.71 },
      { hour: 72, probability: 0.67 },
    ],
  },
  asset_w12_road_0101: {
    asset_id: "asset_w12_road_0101",
    horizon_hours: 72,
    confidence: 0.79,
    points: [
      { hour: 0, probability: 0.24 },
      { hour: 8, probability: 0.28 },
      { hour: 16, probability: 0.31 },
      { hour: 24, probability: 0.35 },
      { hour: 32, probability: 0.38 },
      { hour: 40, probability: 0.42 },
      { hour: 48, probability: 0.45 },
      { hour: 56, probability: 0.44 },
      { hour: 64, probability: 0.43 },
      { hour: 72, probability: 0.41 },
    ],
  },
  asset_c02_bridge_0188: {
    asset_id: "asset_c02_bridge_0188",
    horizon_hours: 72,
    confidence: 0.76,
    points: [
      { hour: 0, probability: 0.62 },
      { hour: 8, probability: 0.66 },
      { hour: 16, probability: 0.7 },
      { hour: 24, probability: 0.74 },
      { hour: 32, probability: 0.78 },
      { hour: 40, probability: 0.82 },
      { hour: 48, probability: 0.86 },
      { hour: 56, probability: 0.88 },
      { hour: 64, probability: 0.85 },
      { hour: 72, probability: 0.83 },
    ],
  },
};

const sensorsByAsset = {
  asset_w12_bridge_0042: {
    strain: { value: 14.8, unit: "me", delta: "+0.2 variance", samples: [11, 12, 13, 14, 14.2, 14.4, 14.8] },
    vibration: { value: 6.2, unit: "mm/s", delta: "+0.6 trend", samples: [4.8, 5.1, 5.4, 5.8, 5.9, 6.0, 6.2] },
    temperature: { value: 31.4, unit: "C", delta: "+1.3C spike", samples: [27, 27.8, 28.4, 29.1, 29.8, 30.7, 31.4] },
    tilt: { value: 0.42, unit: "deg", delta: "+0.04 deg", samples: [0.22, 0.24, 0.29, 0.31, 0.35, 0.39, 0.42] },
  },
  asset_w12_road_0101: {
    strain: { value: 10.5, unit: "me", delta: "+0.1 variance", samples: [8.1, 8.6, 8.9, 9.4, 9.8, 10.1, 10.5] },
    vibration: { value: 3.9, unit: "mm/s", delta: "+0.2 trend", samples: [2.9, 3.1, 3.2, 3.4, 3.6, 3.7, 3.9] },
    temperature: { value: 28.1, unit: "C", delta: "+0.8C spike", samples: [25.2, 25.9, 26.4, 26.8, 27.3, 27.8, 28.1] },
    tilt: { value: 0.27, unit: "deg", delta: "+0.02 deg", samples: [0.17, 0.19, 0.2, 0.22, 0.24, 0.25, 0.27] },
  },
  asset_c02_bridge_0188: {
    strain: { value: 18.4, unit: "me", delta: "+0.4 variance", samples: [14.1, 15.1, 15.9, 16.8, 17.4, 17.9, 18.4] },
    vibration: { value: 8.1, unit: "mm/s", delta: "+0.7 trend", samples: [5.9, 6.2, 6.7, 7.1, 7.4, 7.8, 8.1] },
    temperature: { value: 34.6, unit: "C", delta: "+1.7C spike", samples: [30.1, 30.9, 31.4, 32.2, 33.1, 33.9, 34.6] },
    tilt: { value: 0.58, unit: "deg", delta: "+0.06 deg", samples: [0.31, 0.35, 0.39, 0.43, 0.48, 0.53, 0.58] },
  },
};

const maintenanceLogByAsset = {
  asset_w12_bridge_0042: [
    {
      timestamp: isoMinusHours(1),
      unit: "BRIDGE_N_04",
      operator: "AUTO_SYS_A1",
      status: "CALIBRATED",
      verified: true,
    },
    {
      timestamp: isoMinusHours(3),
      unit: "BRIDGE_N_04",
      operator: "TEAM_17",
      status: "INSPECTED",
      verified: true,
    },
    {
      timestamp: isoMinusHours(7),
      unit: "BRIDGE_N_04",
      operator: "ORCH_ENGINE",
      status: "SCHEDULED",
      verified: false,
    },
  ],
  asset_w12_road_0101: [
    {
      timestamp: isoMinusHours(2),
      unit: "ROAD_W12_101",
      operator: "AUTO_SYS_B2",
      status: "INSPECTED",
      verified: true,
    },
    {
      timestamp: isoMinusHours(8),
      unit: "ROAD_W12_101",
      operator: "TEAM_07",
      status: "SCHEDULED",
      verified: false,
    },
  ],
  asset_c02_bridge_0188: [
    {
      timestamp: isoMinusHours(1),
      unit: "BRIDGE_C02_188",
      operator: "AUTO_SYS_A1",
      status: "ALERTED",
      verified: false,
    },
    {
      timestamp: isoMinusHours(4),
      unit: "BRIDGE_C02_188",
      operator: "TEAM_02",
      status: "INSPECTED",
      verified: true,
    },
  ],
};

export const MOCK_DATA = Object.freeze({
  source: "mock",
  stale: false,
  error: null,
  generatedAt: NOW.toISOString(),
  gatewayHealth: {
    status: "ok",
    dependencies: {
      database: { status: "ok", latency_ms: 6 },
      event_stream: { status: "ok", latency_ms: 4 },
      blockchain_verifier: { status: "ok", latency_ms: 7 },
    },
  },
  assets,
  healthByAsset,
  forecastByAsset,
  sensorsByAsset,
  maintenanceLogByAsset,
  verification: {
    maintenance_id: "mnt_20260214_0012",
    asset_id: "asset_w12_bridge_0042",
    verification_status: "confirmed",
    evidence_hash: "0x" + "a".repeat(64),
    tx_hash: "0x" + "b".repeat(64),
    network: "sepolia",
    block_number: 129934,
    verified_at: isoMinusHours(2),
  },
  blockchainConnection: {
    connected: false,
    network: "sepolia",
    expected_chain_id: 11155111,
    chain_id: null,
    latest_block: null,
    contract_address: "0x" + "1".repeat(40),
    contract_deployed: null,
    checked_at: NOW.toISOString(),
    code: null,
    message: "Click 'Connect Sepolia' to verify live chain reachability.",
    source: "mock",
  },
  walletConnection: {
    connected: false,
    wallet_address: null,
    chain_id: null,
    network: "sepolia",
    message: "Click 'Connect Wallet' to link MetaMask operator identity.",
    checked_at: NOW.toISOString(),
  },
});

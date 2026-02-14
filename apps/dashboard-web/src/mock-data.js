const NOW = new Date();

function isoMinusHours(hours) {
  return new Date(NOW.getTime() - hours * 60 * 60 * 1000).toISOString();
}

export const MOCK_DATA = Object.freeze({
  source: "mock",
  gatewayHealth: {
    status: "ok",
    dependencies: {
      database: { status: "ok", latency_ms: 6 },
      event_stream: { status: "ok", latency_ms: 4 },
      blockchain_verifier: { status: "ok", latency_ms: 7 },
    },
  },
  assets: [
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
  ],
  health: {
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
  forecast: {
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
  maintenanceLog: [
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
      timestamp: isoMinusHours(6),
      unit: "ROAD_W12_101",
      operator: "AUTO_SYS_B2",
      status: "SCHEDULED",
      verified: false,
    },
  ],
  sensors: {
    strain: { value: 14.8, unit: "me", delta: "+0.2% variance", samples: [11, 12, 13, 14, 14.2, 14.4, 14.8] },
    vibration: { value: 6.2, unit: "mm/s", delta: "+0.6% trend", samples: [4.8, 5.1, 5.4, 5.8, 5.9, 6.0, 6.2] },
    temperature: { value: 31.4, unit: "C", delta: "+1.3C spike", samples: [27, 27.8, 28.4, 29.1, 29.8, 30.7, 31.4] },
    tilt: { value: 0.42, unit: "deg", delta: "+0.04 deg", samples: [0.22, 0.24, 0.29, 0.31, 0.35, 0.39, 0.42] },
  },
});

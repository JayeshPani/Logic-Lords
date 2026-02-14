import { DASHBOARD_CONFIG } from "./config.js";
import { connectToSepolia, loadDashboardData } from "./api.js";
import { createViewModel } from "./state.js";
import { connectMetaMaskWallet } from "./wallet.js";
import { renderBlockchainConnectionStatus, renderClock, renderDashboard, renderWalletConnectionStatus } from "./ui.js";

let refreshHandle = null;
let lastBlockchainConnection = null;
let lastWalletConnection = null;

async function refreshDashboard() {
  const raw = await loadDashboardData();
  const viewModel = createViewModel(raw);
  if (lastBlockchainConnection) {
    viewModel.blockchainConnection = lastBlockchainConnection;
  }
  if (lastWalletConnection) {
    viewModel.walletConnection = lastWalletConnection;
  }
  renderDashboard(viewModel);
}

function setupInteractions() {
  const verifyButton = document.getElementById("verify-chain-btn");
  const walletButton = document.getElementById("connect-wallet-btn");
  if (!verifyButton || !walletButton) {
    return;
  }

  verifyButton.addEventListener("click", async () => {
    verifyButton.disabled = true;
    verifyButton.textContent = "Connecting...";

    try {
      const connection = await connectToSepolia();
      lastBlockchainConnection = connection;
      renderBlockchainConnectionStatus(connection);
      verifyButton.textContent = connection.connected ? "Sepolia Connected" : "Retry Sepolia";
      setTimeout(() => {
        verifyButton.textContent = "Connect Sepolia";
      }, 1500);
    } finally {
      verifyButton.disabled = false;
    }
  });

  walletButton.addEventListener("click", async () => {
    walletButton.disabled = true;
    walletButton.textContent = "Connecting...";

    try {
      const walletConnection = await connectMetaMaskWallet();
      lastWalletConnection = walletConnection;
      renderWalletConnectionStatus(walletConnection);
      walletButton.textContent = walletConnection.connected ? "Wallet Connected" : "Retry Wallet";
      setTimeout(() => {
        walletButton.textContent = "Connect Wallet";
      }, 1500);
    } finally {
      walletButton.disabled = false;
    }
  });
}

async function boot() {
  renderClock(new Date());
  setInterval(() => renderClock(new Date()), DASHBOARD_CONFIG.clockIntervalMs);

  await refreshDashboard();
  setupInteractions();

  if (refreshHandle) {
    clearInterval(refreshHandle);
  }
  refreshHandle = setInterval(refreshDashboard, DASHBOARD_CONFIG.refreshIntervalMs);
}

boot();

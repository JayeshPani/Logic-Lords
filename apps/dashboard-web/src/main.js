import { DASHBOARD_CONFIG } from "./config.js";
import { connectToSepolia, loadDashboardData } from "./api.js";
import { createViewModel } from "./state.js";
import { connectMetaMaskWallet } from "./wallet.js";
import { renderClock, renderDashboard } from "./ui.js";

let refreshHandle = null;
let refreshInFlight = false;

let lastPayload = null;
let lastBlockchainConnection = null;
let lastWalletConnection = null;
let selectedAssetId = null;
let activeTabTarget = "overview";

function setupSectionTabs(onTabChange) {
  const triggers = Array.from(document.querySelectorAll(".tab-trigger"));
  const panels = Array.from(document.querySelectorAll(".tab-panel"));
  if (!triggers.length || !panels.length) {
    return;
  }

  const availableTargets = new Set(
    panels.map((panel) => panel.getAttribute("data-tab-panel")).filter(Boolean),
  );

  let activeTarget = "overview";
  try {
    const saved = window.localStorage.getItem("infraguard.activeTab");
    if (saved && availableTargets.has(saved)) {
      activeTarget = saved;
    }
  } catch (_error) {
    // Ignore localStorage access failures and continue with default.
  }

  const activateTab = (target) => {
    if (!availableTargets.has(target)) {
      return;
    }

    panels.forEach((panel) => {
      const isActive = panel.getAttribute("data-tab-panel") === target;
      panel.hidden = !isActive;
      panel.classList.toggle("tab-panel-active", isActive);
    });

    triggers.forEach((trigger) => {
      const isActive = trigger.getAttribute("data-tab-target") === target;
      trigger.classList.toggle("nav-item-active", isActive);
      trigger.classList.toggle("tab-trigger-active", isActive);
      trigger.setAttribute("aria-selected", isActive ? "true" : "false");
    });

    activeTarget = target;
    activeTabTarget = target;
    try {
      window.localStorage.setItem("infraguard.activeTab", target);
    } catch (_error) {
      // Ignore localStorage access failures.
    }

    if (typeof onTabChange === "function") {
      onTabChange(target);
    }
  };

  triggers.forEach((trigger) => {
    trigger.addEventListener("click", () => {
      const target = trigger.getAttribute("data-tab-target");
      if (target) {
        activateTab(target);
      }
    });
  });

  activateTab(activeTarget);
}

function buildRenderablePayload(basePayload) {
  if (!basePayload) {
    return null;
  }

  return {
    ...basePayload,
    blockchainConnection: lastBlockchainConnection || basePayload.blockchainConnection,
    walletConnection: lastWalletConnection || basePayload.walletConnection,
  };
}

function renderCurrent() {
  const payload = buildRenderablePayload(lastPayload);
  if (!payload) {
    return;
  }

  const viewModel = createViewModel(payload, { selectedAssetId });
  selectedAssetId = viewModel.selectedAssetId;

  renderDashboard(viewModel, {
    activeTab: activeTabTarget,
    onSelectAsset: (assetId) => {
      selectedAssetId = assetId;
      renderCurrent();
    },
  });
}

async function refreshDashboard() {
  if (refreshInFlight) {
    return;
  }
  refreshInFlight = true;

  try {
    const result = await loadDashboardData(lastPayload);
    lastPayload = result.payload;
    renderCurrent();
  } finally {
    refreshInFlight = false;
  }
}

function setButtonBusy(button, busy, busyLabel, idleLabel) {
  if (!button) {
    return;
  }
  button.disabled = busy;
  button.textContent = busy ? busyLabel : idleLabel;
}

function setupInteractions() {
  const verifyButton = document.getElementById("verify-chain-btn");
  const walletButton = document.getElementById("connect-wallet-btn");
  if (!verifyButton || !walletButton) {
    return;
  }

  verifyButton.addEventListener("click", async () => {
    setButtonBusy(verifyButton, true, "Connecting...", "Connect Sepolia");
    try {
      const connection = await connectToSepolia();
      lastBlockchainConnection = connection;
      renderCurrent();
      verifyButton.textContent = connection.connected ? "Sepolia Connected" : "Retry Sepolia";
      setTimeout(() => {
        if (!verifyButton.disabled) {
          verifyButton.textContent = "Connect Sepolia";
        }
      }, 1800);
    } finally {
      verifyButton.disabled = false;
    }
  });

  walletButton.addEventListener("click", async () => {
    setButtonBusy(walletButton, true, "Connecting...", "Connect Wallet");
    try {
      const walletConnection = await connectMetaMaskWallet();
      lastWalletConnection = walletConnection;
      renderCurrent();
      walletButton.textContent = walletConnection.connected ? "Wallet Connected" : "Retry Wallet";
      setTimeout(() => {
        if (!walletButton.disabled) {
          walletButton.textContent = "Connect Wallet";
        }
      }, 1800);
    } finally {
      walletButton.disabled = false;
    }
  });
}

async function boot() {
  setupSectionTabs(() => {
    renderCurrent();
  });
  renderClock(new Date());
  setInterval(() => renderClock(new Date()), DASHBOARD_CONFIG.clockIntervalMs);

  await refreshDashboard();
  setupInteractions();

  if (refreshHandle) {
    clearInterval(refreshHandle);
  }
  refreshHandle = setInterval(() => {
    void refreshDashboard();
  }, DASHBOARD_CONFIG.refreshIntervalMs);
}

void boot();

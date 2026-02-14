import { DASHBOARD_CONFIG } from "./config.js";
import { connectToSepolia, loadDashboardData } from "./api.js";
import { createViewModel } from "./state.js";
import { connectMetaMaskWallet, emptyWalletStatus } from "./wallet.js";
import { renderClock, renderDashboard } from "./ui.js";

let refreshHandle = null;
let refreshInFlight = false;

let lastPayload = null;
let lastBlockchainConnection = null;
let lastWalletConnection = null;
let selectedAssetId = null;
let activeTabTarget = "overview";
let activateTabRef = null;

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

    const mainContent = document.getElementById("main-content");
    if (mainContent) {
      mainContent.scrollTop = 0;
    }
  };

  activateTabRef = activateTab;

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
    onSelectAsset: (assetId, options = {}) => {
      selectedAssetId = assetId;
      if (options.navigateToAssetDetail && typeof activateTabRef === "function") {
        activateTabRef("asset");
        return;
      }
      renderCurrent();
    },
  });

  const accountWalletStatus = document.getElementById("account-wallet-status");
  const accountWalletAddress = document.getElementById("account-wallet-address");
  const accountWalletChain = document.getElementById("account-wallet-chain");
  const accountChainStatus = document.getElementById("account-chain-status");
  if (accountWalletStatus) {
    accountWalletStatus.textContent = viewModel?.walletConnection?.connected ? "Connected" : "Disconnected";
  }
  if (accountWalletAddress) {
    accountWalletAddress.textContent = viewModel?.walletConnection?.wallet_address || "-";
  }
  if (accountWalletChain) {
    accountWalletChain.textContent = String(viewModel?.walletConnection?.chain_id ?? "-");
  }
  if (accountChainStatus) {
    accountChainStatus.textContent = viewModel?.blockchainConnection?.connected ? "Reachable" : "Unavailable";
  }
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

function setupHeaderActions() {
  const profileButton = document.getElementById("profile-btn");
  const accountModal = document.getElementById("account-modal");
  const accountCloseButton = document.getElementById("account-close-btn");
  const profileNote = document.getElementById("profile-action-note");
  const refreshButton = document.getElementById("profile-refresh-btn");
  const disconnectWalletButton = document.getElementById("profile-disconnect-wallet-btn");

  if (!profileButton || !accountModal) {
    return;
  }

  const openAccountModal = () => {
    accountModal.hidden = false;
    profileButton.setAttribute("aria-expanded", "true");
  };

  const closeAccountModal = () => {
    accountModal.hidden = true;
    profileButton.setAttribute("aria-expanded", "false");
  };

  profileButton.addEventListener("click", () => {
    const isOpen = !accountModal.hidden;
    if (isOpen) {
      closeAccountModal();
      return;
    }
    openAccountModal();
  });

  accountModal.querySelectorAll("[data-nav-target]").forEach((button) => {
    button.addEventListener("click", () => {
      const target = button.getAttribute("data-nav-target");
      if (target && typeof activateTabRef === "function") {
        activateTabRef(target);
      }
      closeAccountModal();
    });
  });

  if (refreshButton) {
    refreshButton.addEventListener("click", async () => {
      if (profileNote) {
        profileNote.textContent = "Refreshing dashboard data...";
      }
      await refreshDashboard();
      if (profileNote) {
        profileNote.textContent = "Data refreshed.";
      }
    });
  }

  if (disconnectWalletButton) {
    disconnectWalletButton.addEventListener("click", () => {
      lastWalletConnection = emptyWalletStatus();
      renderCurrent();
      if (profileNote) {
        profileNote.textContent = "Wallet status reset in dashboard view.";
      }
    });
  }

  document.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof Node)) {
      return;
    }
    if (target instanceof HTMLElement && target.dataset.accountClose === "true") {
      closeAccountModal();
    }
  });

  if (accountCloseButton) {
    accountCloseButton.addEventListener("click", () => {
      closeAccountModal();
    });
  }

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeAccountModal();
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
  setupHeaderActions();

  if (refreshHandle) {
    clearInterval(refreshHandle);
  }
  refreshHandle = setInterval(() => {
    void refreshDashboard();
  }, DASHBOARD_CONFIG.refreshIntervalMs);
}

void boot();

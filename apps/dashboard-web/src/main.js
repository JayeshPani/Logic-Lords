import { DASHBOARD_CONFIG } from "./config.js";
import {
  acknowledgeIncident,
  connectToSepolia,
  loadDashboardData,
  submitVerification,
  trackMaintenanceVerification,
  uploadAndFinalizeEvidence,
} from "./api.js";
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
const ackInFlightIds = new Set();
let verificationTrackInFlight = false;
let evidenceUploadInFlight = false;
let verificationSubmitInFlight = false;
let selectedEvidenceFileName = null;
let selectedNodeId = null;
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
    ackInFlightIds,
    isTrackingVerification: verificationTrackInFlight,
    isUploadingEvidence: evidenceUploadInFlight,
    isSubmittingVerification: verificationSubmitInFlight,
    selectedEvidenceFileName,
    onSelectAsset: (assetId, options = {}) => {
      selectedAssetId = assetId;
      selectedNodeId = null;
      if (options.navigateToAssetDetail && typeof activateTabRef === "function") {
        activateTabRef("asset");
        return;
      }
      renderCurrent();
    },
    onSelectNode: (nodeId) => {
      selectedNodeId = nodeId;
      renderCurrent();
    },
    selectedNodeId,
    onAcknowledgeIncident: (workflowId) => {
      void acknowledgeWorkflow(workflowId);
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

async function acknowledgeWorkflow(workflowId) {
  if (!workflowId || ackInFlightIds.has(workflowId)) {
    return;
  }

  ackInFlightIds.add(workflowId);
  renderCurrent();

  const acknowledgedBy = lastWalletConnection?.wallet_address || "dashboard-operator";
  try {
    await acknowledgeIncident(workflowId, {
      acknowledgedBy,
      ackNotes: "Acknowledged from InfraGuard dashboard.",
    });
    await refreshDashboard();
  } catch (error) {
    if (lastPayload) {
      lastPayload = {
        ...lastPayload,
        error: {
          code: error?.code || "ACK_FAILED",
          message: error?.message || "Failed to acknowledge incident.",
          endpoint: error?.endpoint || null,
        },
      };
    }
  } finally {
    ackInFlightIds.delete(workflowId);
    renderCurrent();
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

function resolveActiveMaintenanceId() {
  if (lastPayload?.verification?.maintenance_id) {
    return lastPayload.verification.maintenance_id;
  }
  if (lastPayload?.activeMaintenanceId) {
    return lastPayload.activeMaintenanceId;
  }

  const incidents = Array.isArray(lastPayload?.automationIncidents)
    ? lastPayload.automationIncidents
    : [];
  const incident = incidents.find(
    (item) => typeof item?.maintenance_id === "string" && item.maintenance_id.trim().length > 0,
  );
  if (incident) {
    return incident.maintenance_id;
  }

  return null;
}

async function trackVerificationStatus() {
  if (verificationTrackInFlight) {
    return;
  }

  const maintenanceId = resolveActiveMaintenanceId();
  if (!maintenanceId) {
    return;
  }

  verificationTrackInFlight = true;
  renderCurrent();

  try {
    const tracked = await trackMaintenanceVerification(maintenanceId);
    if (lastPayload) {
      lastPayload = {
        ...lastPayload,
        activeMaintenanceId: maintenanceId,
        verification: tracked || lastPayload.verification || null,
        generatedAt: new Date().toISOString(),
        error: null,
      };
    }
  } catch (error) {
    if (lastPayload) {
      lastPayload = {
        ...lastPayload,
        error: {
          code: error?.code || "TRACK_FAILED",
          message: error?.message || "Failed to track verification.",
          endpoint: error?.endpoint || null,
        },
      };
    }
  } finally {
    verificationTrackInFlight = false;
    renderCurrent();
  }
}

function setButtonBusy(button, busy, busyLabel, idleLabel) {
  if (!button) {
    return;
  }
  button.disabled = busy;
  button.textContent = busy ? busyLabel : idleLabel;
}

function setDashboardError(error, fallbackCode, fallbackMessage) {
  if (!lastPayload) {
    return;
  }
  lastPayload = {
    ...lastPayload,
    error: {
      code: error?.code || fallbackCode,
      message: error?.message || fallbackMessage,
      endpoint: error?.endpoint || null,
    },
  };
}

function resolveEvidenceAssetId(maintenanceId) {
  const incidents = Array.isArray(lastPayload?.automationIncidents) ? lastPayload.automationIncidents : [];
  const incidentMatch = incidents.find(
    (incident) =>
      typeof incident?.maintenance_id === "string" &&
      incident.maintenance_id === maintenanceId &&
      typeof incident?.asset_id === "string" &&
      incident.asset_id.length > 0,
  );
  if (incidentMatch) {
    return incidentMatch.asset_id;
  }

  if (
    lastPayload?.verification &&
    typeof lastPayload.verification.maintenance_id === "string" &&
    lastPayload.verification.maintenance_id === maintenanceId &&
    typeof lastPayload.verification.asset_id === "string" &&
    lastPayload.verification.asset_id.length > 0
  ) {
    return lastPayload.verification.asset_id;
  }

  if (selectedAssetId) {
    return selectedAssetId;
  }

  const assets = Array.isArray(lastPayload?.assets) ? lastPayload.assets : [];
  if (assets.length > 0 && typeof assets[0]?.asset_id === "string") {
    return assets[0].asset_id;
  }
  return null;
}

async function handleEvidenceUpload() {
  if (evidenceUploadInFlight) {
    return;
  }

  const maintenanceId = resolveActiveMaintenanceId();
  const assetId = resolveEvidenceAssetId(maintenanceId);
  const fileInput = document.getElementById("evidence-file-input");
  const categoryInput = document.getElementById("evidence-category");
  const notesInput = document.getElementById("evidence-notes");
  const file = fileInput?.files?.[0] || null;

  if (!maintenanceId) {
    setDashboardError(
      { code: "MISSING_MAINTENANCE_ID", message: "No maintenance ID available for evidence upload." },
      "MISSING_MAINTENANCE_ID",
      "No maintenance ID available for evidence upload.",
    );
    renderCurrent();
    return;
  }
  if (!assetId) {
    setDashboardError(
      { code: "MISSING_ASSET_ID", message: "No asset selected for evidence upload." },
      "MISSING_ASSET_ID",
      "No asset selected for evidence upload.",
    );
    renderCurrent();
    return;
  }
  if (!file) {
    setDashboardError(
      { code: "EVIDENCE_FILE_REQUIRED", message: "Select an evidence file before upload." },
      "EVIDENCE_FILE_REQUIRED",
      "Select an evidence file before upload.",
    );
    renderCurrent();
    return;
  }

  evidenceUploadInFlight = true;
  selectedEvidenceFileName = file.name;
  renderCurrent();

  try {
    await uploadAndFinalizeEvidence({
      maintenanceId,
      assetId,
      file,
      uploadedBy: lastWalletConnection?.wallet_address || "dashboard-operator",
      category: categoryInput?.value?.trim() || null,
      notes: notesInput?.value?.trim() || null,
    });

    if (fileInput) {
      fileInput.value = "";
    }
    if (notesInput) {
      notesInput.value = "";
    }
    selectedEvidenceFileName = null;
    await refreshDashboard();
  } catch (error) {
    setDashboardError(error, "EVIDENCE_UPLOAD_FAILED", "Failed to upload evidence.");
  } finally {
    evidenceUploadInFlight = false;
    renderCurrent();
  }
}

async function handleVerificationSubmit() {
  if (verificationSubmitInFlight) {
    return;
  }

  const maintenanceId = resolveActiveMaintenanceId();
  if (!maintenanceId) {
    setDashboardError(
      { code: "MISSING_MAINTENANCE_ID", message: "No maintenance ID available for verification submit." },
      "MISSING_MAINTENANCE_ID",
      "No maintenance ID available for verification submit.",
    );
    renderCurrent();
    return;
  }

  verificationSubmitInFlight = true;
  renderCurrent();

  try {
    await submitVerification(maintenanceId, {
      submitted_by: lastWalletConnection?.wallet_address || "dashboard-operator",
      operator_wallet_address: lastWalletConnection?.wallet_address || undefined,
    });
    await refreshDashboard();
  } catch (error) {
    setDashboardError(error, "VERIFICATION_SUBMIT_FAILED", "Failed to submit verification.");
  } finally {
    verificationSubmitInFlight = false;
    renderCurrent();
  }
}

function setupInteractions() {
  const verifyButton = document.getElementById("verify-chain-btn");
  const trackButton = document.getElementById("track-verification-btn");
  const walletButton = document.getElementById("connect-wallet-btn");
  const evidenceUploadButton = document.getElementById("evidence-upload-btn");
  const evidenceSubmitButton = document.getElementById("submit-verification-btn");
  const evidenceFileInput = document.getElementById("evidence-file-input");
  if (!verifyButton || !walletButton || !trackButton || !evidenceUploadButton || !evidenceSubmitButton) {
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

  trackButton.addEventListener("click", async () => {
    await trackVerificationStatus();
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

  evidenceUploadButton.addEventListener("click", async () => {
    await handleEvidenceUpload();
  });

  evidenceSubmitButton.addEventListener("click", async () => {
    await handleVerificationSubmit();
  });

  if (evidenceFileInput) {
    evidenceFileInput.addEventListener("change", () => {
      const file = evidenceFileInput.files?.[0] || null;
      selectedEvidenceFileName = file?.name || null;
      renderCurrent();
    });
  }
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

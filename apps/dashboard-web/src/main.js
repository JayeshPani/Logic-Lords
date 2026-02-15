import { DASHBOARD_CONFIG } from "./config.js";
import {
  acknowledgeIncident,
  clearFirebaseNodesConfig,
  connectToSepolia,
  getFirebaseNodesConfig,
  loadDashboardData,
  saveFirebaseNodesConfig,
  sendAssistantChat,
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
const assistantHistory = [];
let assistantSendInFlight = false;
let assistantSpeechRecognition = null;
let assistantMicListening = false;
let assistantMicBlocked = false;
let telemetryEventSource = null;
let telemetryStreamAssetId = null;

function stopTelemetryStream() {
  if (telemetryEventSource) {
    try {
      telemetryEventSource.close();
    } catch (_error) {
      // Ignore close errors.
    }
  }
  telemetryEventSource = null;
  telemetryStreamAssetId = null;
}

function ensureTelemetryStream(assetId) {
  const id = typeof assetId === "string" ? assetId.trim() : "";
  if (!id) {
    stopTelemetryStream();
    return;
  }
  if (telemetryStreamAssetId === id && telemetryEventSource) {
    return;
  }

  stopTelemetryStream();

  const token = encodeURIComponent(DASHBOARD_CONFIG.authToken || "");
  const endpoint = `/telemetry/${encodeURIComponent(id)}/stream?token=${token}`;
  telemetryStreamAssetId = id;

  try {
    telemetryEventSource = new EventSource(endpoint);
  } catch (_error) {
    telemetryEventSource = null;
    telemetryStreamAssetId = null;
    return;
  }

  telemetryEventSource.onmessage = (event) => {
    if (!event?.data) {
      return;
    }
    let telemetry = null;
    try {
      telemetry = JSON.parse(event.data);
    } catch (_error) {
      return;
    }
    const sensors = telemetry?.sensors;
    if (!sensors || typeof sensors !== "object") {
      return;
    }
    if (!lastPayload) {
      return;
    }

    // Patch in latest sensor card metrics without re-fetching the whole dashboard.
    lastPayload = {
      ...lastPayload,
      source: lastPayload.source || "live",
      generatedAt: new Date().toISOString(),
      sensorsByAsset: {
        ...(lastPayload.sensorsByAsset || {}),
        [id]: sensors,
      },
      error: null,
    };
    renderCurrent();
  };

  telemetryEventSource.addEventListener("error", () => {
    // Keep the UI usable even if SSE fails; periodic refresh still runs.
  });
}

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
  ensureTelemetryStream(selectedAssetId);

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

  const fallback =
    typeof DASHBOARD_CONFIG.maintenanceIdFallback === "string" && DASHBOARD_CONFIG.maintenanceIdFallback.trim()
      ? DASHBOARD_CONFIG.maintenanceIdFallback.trim()
      : null;
  return fallback;
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

function setupFirebaseConnectorControls() {
  const dbInput = document.getElementById("firebase-db-url");
  const basePathInput = document.getElementById("firebase-base-path");
  const authTokenInput = document.getElementById("firebase-auth-token");
  const connectButton = document.getElementById("firebase-connect-btn");
  const disconnectButton = document.getElementById("firebase-disconnect-btn");
  if (!dbInput || !basePathInput || !authTokenInput || !connectButton || !disconnectButton) {
    return;
  }

  const applyConfigToInputs = (config) => {
    dbInput.value = config?.dbUrl || "";
    basePathInput.value = config?.basePath || "infraguard/telemetry";
    authTokenInput.value = config?.authToken || "";
  };

  applyConfigToInputs(getFirebaseNodesConfig());

  connectButton.addEventListener("click", async () => {
    const normalized = saveFirebaseNodesConfig({
      enabled: true,
      dbUrl: dbInput.value,
      basePath: basePathInput.value,
      authToken: authTokenInput.value,
    });
    applyConfigToInputs(normalized);
    setButtonBusy(connectButton, true, "Connecting...", "Connect Firebase");
    try {
      await refreshDashboard();
      connectButton.textContent = "Connected";
      setTimeout(() => {
        if (!connectButton.disabled) {
          connectButton.textContent = "Connect Firebase";
        }
      }, 1500);
    } finally {
      connectButton.disabled = false;
    }
  });

  disconnectButton.addEventListener("click", async () => {
    const cleared = clearFirebaseNodesConfig();
    applyConfigToInputs(cleared);
    setButtonBusy(disconnectButton, true, "Disconnecting...", "Disconnect");
    try {
      await refreshDashboard();
    } finally {
      disconnectButton.disabled = false;
      disconnectButton.textContent = "Disconnect";
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

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function appendAssistantMessage(role, content) {
  const messagesEl = document.getElementById("assistant-chat-messages");
  if (!messagesEl) {
    return;
  }
  const item = document.createElement("div");
  item.className = role === "assistant" ? "assistant-msg assistant-msg-bot" : "assistant-msg assistant-msg-user";
  item.innerHTML = `<p>${escapeHtml(content)}</p>`;
  messagesEl.appendChild(item);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function appendAssistantStatus(content) {
  const messagesEl = document.getElementById("assistant-chat-messages");
  if (!messagesEl) {
    return null;
  }
  messagesEl.querySelectorAll(".assistant-status").forEach((node) => node.remove());
  const item = document.createElement("div");
  item.className = "assistant-status";
  item.textContent = content;
  messagesEl.appendChild(item);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return item;
}

function assistantFallbackReply(message, languageMode = "auto") {
  const text = String(message || "").toLowerCase();
  const asksModules =
    /module|architecture|flow|service|what does|explain|component|workflow|orchestration|ledger|blockchain|firebase/.test(
      text,
    );
  const asksTroubleshoot =
    /error|not working|fix|debug|failed|timeout|503|429|404|issue|problem/.test(text);

  const enBase = asksModules
    ? [
      "AI assistant backend is currently unavailable, so I am answering in local fallback mode.",
      "InfraGuard module quick map:",
      "1. Sensor ingestion: reads Firebase telemetry and normalizes metrics.",
      "2. API Gateway: auth, rate-limit, and proxy to all services.",
      "3. Orchestration: incident lifecycle, ACK SLA, and escalation.",
      "4. Report generation: evidence hash and verification command.",
      "5. Blockchain verification: submit/track verification state.",
      "6. Dashboard: operator UI for triage, nodes, maintenance, ledger.",
    ].join("\n")
    : asksTroubleshoot
      ? [
        "AI assistant backend is currently unavailable, fallback mode is active.",
        "Quick checks:",
        "1. Restart API gateway with latest code.",
        "2. Set `API_GATEWAY_ASSISTANT_GROQ_API_KEY`.",
        "3. Verify `/assistant/chat` exists and returns non-404.",
        "4. Hard refresh the dashboard (Cmd+Shift+R).",
      ].join("\n")
      : "AI assistant backend is currently unavailable. Please retry in a moment. I can still provide module and troubleshooting guidance locally.";

  const hiBase = asksModules
    ? [
      "AI assistant backend abhi unavailable hai, isliye main local fallback mode mein jawab de raha hoon.",
      "InfraGuard module quick map:",
      "1. Sensor ingestion: Firebase telemetry read karke metrics normalize karta hai.",
      "2. API Gateway: auth, rate-limit, aur sab services ko proxy karta hai.",
      "3. Orchestration: incident lifecycle, ACK SLA, aur escalation.",
      "4. Report generation: evidence hash aur verification command.",
      "5. Blockchain verification: verification state submit/track.",
      "6. Dashboard: triage, nodes, maintenance, ledger UI.",
    ].join("\n")
    : asksTroubleshoot
      ? [
        "AI assistant backend unavailable hai, fallback mode active hai.",
        "Quick checks:",
        "1. API gateway latest code ke saath restart karo.",
        "2. `API_GATEWAY_ASSISTANT_GROQ_API_KEY` set karo.",
        "3. `/assistant/chat` endpoint 404 na de, yeh verify karo.",
        "4. Dashboard hard refresh karo (Cmd+Shift+R).",
      ].join("\n")
      : "AI assistant backend abhi unavailable hai. Thodi der baad retry karein. Main local mode mein module aur troubleshooting help de sakta hoon.";

  const mode = String(languageMode || "auto").toLowerCase();
  if (mode === "english") {
    return enBase;
  }
  if (mode === "hindi") {
    return hiBase;
  }
  if (mode === "bilingual") {
    return `${enBase}\n\n---\n\n${hiBase}`;
  }

  const hasHindi = /[\u0900-\u097f]/.test(message || "");
  return hasHindi ? hiBase : enBase;
}

function setAssistantMicState(active) {
  assistantMicListening = active;
  const micBtn = document.getElementById("assistant-chat-mic-btn");
  if (!micBtn) {
    return;
  }
  micBtn.classList.toggle("assistant-mic-live", active);
  micBtn.textContent = active ? "Listening..." : "Mic";
}

function setupAssistantMic(languageSelect, inputEl, micBtn) {
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Recognition || !inputEl || !micBtn) {
    if (micBtn) {
      micBtn.disabled = true;
      micBtn.textContent = "Mic N/A";
    }
    return;
  }
  if (assistantMicBlocked) {
    micBtn.disabled = true;
    micBtn.textContent = "Mic Blocked";
    return;
  }
  micBtn.disabled = false;
  if (!assistantMicListening) {
    micBtn.textContent = "Mic";
  }
  if (assistantSpeechRecognition && assistantMicListening) {
    try {
      assistantSpeechRecognition.stop();
    } catch (_error) {
      // Ignore stop errors during reconfiguration.
    }
  }
  assistantSpeechRecognition = new Recognition();
  assistantSpeechRecognition.continuous = false;
  assistantSpeechRecognition.interimResults = false;
  assistantSpeechRecognition.maxAlternatives = 1;
  assistantSpeechRecognition.onstart = () => setAssistantMicState(true);
  assistantSpeechRecognition.onend = () => setAssistantMicState(false);
  assistantSpeechRecognition.onerror = (event) => {
    setAssistantMicState(false);
    const code = String(event?.error || "").toLowerCase();
    if (code === "not-allowed" || code === "service-not-allowed" || code === "audio-capture") {
      assistantMicBlocked = true;
      micBtn.disabled = true;
      micBtn.textContent = "Mic Blocked";
      appendAssistantStatus("Microphone permission blocked by browser. Enable mic permission, then reload.");
      return;
    }
    appendAssistantStatus("Microphone input failed. Type your question instead.");
  };
  assistantSpeechRecognition.onresult = (event) => {
    const transcript = event?.results?.[0]?.[0]?.transcript || "";
    if (!transcript) {
      return;
    }
    inputEl.value = `${inputEl.value} ${transcript}`.trim();
    inputEl.focus();
  };

  const selectedLanguage = String(languageSelect?.value || "auto").toLowerCase();
  if (selectedLanguage === "hindi") {
    assistantSpeechRecognition.lang = "hi-IN";
  } else {
    assistantSpeechRecognition.lang = "en-US";
  }
}

async function handleAssistantSend() {
  if (assistantSendInFlight) {
    return;
  }
  const inputEl = document.getElementById("assistant-chat-input");
  const languageEl = document.getElementById("assistant-chat-language");
  const sendBtn = document.getElementById("assistant-chat-send-btn");
  if (!inputEl || !languageEl || !sendBtn) {
    return;
  }

  const message = String(inputEl.value || "").trim();
  if (!message) {
    return;
  }

  assistantSendInFlight = true;
  inputEl.disabled = true;
  sendBtn.disabled = true;
  appendAssistantMessage("user", message);
  assistantHistory.push({ role: "user", content: message });
  inputEl.value = "";
  const statusNode = appendAssistantStatus("InfraGuard Assistant is thinking...");
  const selectedLanguage = languageEl.value || "auto";

  try {
    const response = await sendAssistantChat({
      message,
      language: selectedLanguage,
      history: assistantHistory.slice(-8),
    });
    const reply = response?.reply || "No response from assistant.";
    appendAssistantMessage("assistant", reply);
    assistantHistory.push({ role: "assistant", content: reply });
  } catch (error) {
    const code = String(error?.code || "");
    const messageText = String(error?.message || "");
    if (code === "NOT_FOUND" || code.startsWith("ASSISTANT_") || code === "NETWORK_ERROR" || code === "TIMEOUT") {
      const fallback = assistantFallbackReply(message, selectedLanguage);
      appendAssistantMessage("assistant", fallback);
      assistantHistory.push({ role: "assistant", content: fallback });
      if (code === "NOT_FOUND") {
        appendAssistantStatus("Assistant endpoint not found. Restart API gateway with latest code.");
      }
    } else {
      appendAssistantMessage(
        "assistant",
        `I could not complete that request. ${messageText || "Please try again."}`,
      );
    }
  } finally {
    if (statusNode && statusNode.parentElement) {
      statusNode.remove();
    }
    assistantSendInFlight = false;
    inputEl.disabled = false;
    sendBtn.disabled = false;
    inputEl.focus();
  }
}

function setupAssistantWidget() {
  const toggleBtn = document.getElementById("assistant-chat-toggle");
  const panel = document.getElementById("assistant-chat-panel");
  const closeBtn = document.getElementById("assistant-chat-close-btn");
  const sendBtn = document.getElementById("assistant-chat-send-btn");
  const inputEl = document.getElementById("assistant-chat-input");
  const micBtn = document.getElementById("assistant-chat-mic-btn");
  const languageEl = document.getElementById("assistant-chat-language");
  const messagesEl = document.getElementById("assistant-chat-messages");
  if (!toggleBtn || !panel || !closeBtn || !sendBtn || !inputEl || !micBtn || !languageEl || !messagesEl) {
    return;
  }

  if (!messagesEl.dataset.initialized) {
    appendAssistantMessage(
      "assistant",
      "Hi, I am InfraGuard Assistant. Ask me about any module, workflow, or operations issue in English or Hindi.",
    );
    messagesEl.dataset.initialized = "true";
  }

  toggleBtn.addEventListener("click", () => {
    const isHidden = panel.hidden;
    panel.hidden = !isHidden;
    toggleBtn.setAttribute("aria-expanded", isHidden ? "true" : "false");
    if (isHidden) {
      inputEl.focus();
    }
  });

  closeBtn.addEventListener("click", () => {
    panel.hidden = true;
    toggleBtn.setAttribute("aria-expanded", "false");
  });

  sendBtn.addEventListener("click", async () => {
    await handleAssistantSend();
  });

  inputEl.addEventListener("keydown", async (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      await handleAssistantSend();
    }
  });

  languageEl.addEventListener("change", () => {
    setupAssistantMic(languageEl, inputEl, micBtn);
  });

  setupAssistantMic(languageEl, inputEl, micBtn);

  micBtn.addEventListener("click", () => {
    if (!assistantSpeechRecognition) {
      appendAssistantStatus("Microphone input is not supported in this browser.");
      return;
    }
    if (assistantMicListening) {
      assistantSpeechRecognition.stop();
      return;
    }
    try {
      assistantSpeechRecognition.start();
    } catch (_error) {
      appendAssistantStatus("Microphone is busy. Try again.");
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
  setupFirebaseConnectorControls();
  setupHeaderActions();
  setupAssistantWidget();

  window.addEventListener("beforeunload", () => {
    stopTelemetryStream();
  });

  if (refreshHandle) {
    clearInterval(refreshHandle);
  }
  refreshHandle = setInterval(() => {
    void refreshDashboard();
  }, DASHBOARD_CONFIG.refreshIntervalMs);
}

void boot();

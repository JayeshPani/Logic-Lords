const SEPOLIA_CHAIN_ID_HEX = "0xaa36a7";
const SEPOLIA_CHAIN_ID_DEC = 11155111;

function fallbackStatus(message) {
  return {
    connected: false,
    wallet_address: null,
    chain_id: null,
    network: "sepolia",
    message,
    checked_at: new Date().toISOString(),
  };
}

function normalizeAddress(value) {
  if (!value || typeof value !== "string") {
    return null;
  }
  return value;
}

async function switchToSepolia(ethereum) {
  try {
    await ethereum.request({
      method: "wallet_switchEthereumChain",
      params: [{ chainId: SEPOLIA_CHAIN_ID_HEX }],
    });
    return { switched: true, error: null };
  } catch (error) {
    const message = error?.message || "Unable to switch wallet network to Sepolia.";
    return { switched: false, error: message };
  }
}

function parseChainIdHex(chainIdHex) {
  if (!chainIdHex || typeof chainIdHex !== "string" || !chainIdHex.startsWith("0x")) {
    return null;
  }
  return Number.parseInt(chainIdHex, 16);
}

export async function connectMetaMaskWallet() {
  const ethereum = window.ethereum;
  if (!ethereum || typeof ethereum.request !== "function") {
    return fallbackStatus("MetaMask provider was not found in this browser.");
  }

  try {
    const accounts = await ethereum.request({ method: "eth_requestAccounts" });
    const address = normalizeAddress(Array.isArray(accounts) ? accounts[0] : null);

    if (!address) {
      return fallbackStatus("No wallet account was returned by MetaMask.");
    }

    let chainIdHex = await ethereum.request({ method: "eth_chainId" });
    let chainId = parseChainIdHex(chainIdHex);

    if (chainId !== SEPOLIA_CHAIN_ID_DEC) {
      const switchResult = await switchToSepolia(ethereum);
      if (!switchResult.switched) {
        return {
          connected: false,
          wallet_address: address,
          chain_id: chainId,
          network: "sepolia",
          message: `Wallet connected, but network switch failed: ${switchResult.error}`,
          checked_at: new Date().toISOString(),
        };
      }

      chainIdHex = await ethereum.request({ method: "eth_chainId" });
      chainId = parseChainIdHex(chainIdHex);
    }

    const connected = chainId === SEPOLIA_CHAIN_ID_DEC;
    const message = connected
      ? "Wallet connected on Sepolia."
      : `Wallet connected on chain ${chainIdHex}; expected Sepolia.`;

    return {
      connected,
      wallet_address: address,
      chain_id: chainId,
      network: "sepolia",
      message,
      checked_at: new Date().toISOString(),
    };
  } catch (error) {
    return fallbackStatus(`MetaMask connection failed: ${error?.message || "unknown error"}`);
  }
}

export function emptyWalletStatus() {
  return fallbackStatus("Click 'Connect Wallet' to link MetaMask operator identity.");
}

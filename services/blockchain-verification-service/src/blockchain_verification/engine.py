"""Core logic for blockchain verification submission and confirmation tracking."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re

from .config import Settings
from .events import build_maintenance_verified_blockchain_event
from .schemas import SepoliaConnectionResponse, VerificationRecordBlockchainCommand
from .sepolia_rpc import SepoliaRpcClient, SepoliaRpcError
from .store import InMemoryVerificationStore, VerificationRecordMutable


@dataclass(frozen=True)
class TrackResult:
    """Result of one confirmation tracking call."""

    record: VerificationRecordMutable
    maintenance_verified_event: dict | None


class BlockchainVerificationEngine:
    """Handles verification record creation and confirmation state transitions."""

    def __init__(self, *, settings: Settings, store: InMemoryVerificationStore) -> None:
        self._settings = settings
        self._store = store

    def reset_state_for_tests(self) -> None:
        """Reset in-memory state for deterministic tests."""

        self._store.reset()

    def record(self, command: VerificationRecordBlockchainCommand) -> VerificationRecordMutable:
        """Create submitted verification record from command payload."""

        existing = self._store.get(command.payload.maintenance_id)
        if existing is not None:
            raise ValueError(f"verification already exists for maintenance_id={command.payload.maintenance_id}")

        now = datetime.now(tz=timezone.utc)
        verification_id = self._store.next_verification_id(now)
        tx_hash = self._build_tx_hash(command)
        block_number = self._derive_block_number(tx_hash)

        record = VerificationRecordMutable(
            verification_id=verification_id,
            command_id=str(command.command_id),
            maintenance_id=command.payload.maintenance_id,
            asset_id=command.payload.asset_id,
            verification_status="submitted",
            evidence_hash=command.payload.evidence_hash,
            tx_hash=tx_hash,
            network=command.payload.network,
            contract_address=command.payload.contract_address,
            chain_id=command.payload.chain_id,
            block_number=block_number,
            confirmations=0,
            required_confirmations=self._settings.required_confirmations,
            submitted_at=now,
            confirmed_at=None,
            failure_reason=None,
            created_at=now,
            updated_at=now,
            trace_id=command.trace_id,
            maintenance_verified_event=None,
        )
        self._store.put(record)
        return record

    def track(self, maintenance_id: str) -> TrackResult:
        """Advance confirmation count and emit verified event once confirmed."""

        record = self._store.get(maintenance_id)
        if record is None:
            raise KeyError(f"verification not found for maintenance_id={maintenance_id}")

        if record.verification_status == "failed":
            return TrackResult(record=record, maintenance_verified_event=None)

        if record.verification_status == "confirmed":
            return TrackResult(record=record, maintenance_verified_event=None)

        record.confirmations += 1
        now = datetime.now(tz=timezone.utc)
        record.updated_at = now

        if record.confirmations >= record.required_confirmations:
            record.verification_status = "confirmed"
            record.confirmed_at = now
            event = build_maintenance_verified_blockchain_event(
                maintenance_id=record.maintenance_id,
                asset_id=record.asset_id,
                evidence_hash=record.evidence_hash,
                tx_hash=record.tx_hash or self._build_fallback_hash(record.maintenance_id),
                network=record.network,
                verified_at=now,
                trace_id=record.trace_id,
                produced_by=self._settings.event_produced_by,
            )
            record.maintenance_verified_event = event
            self._store.put(record)
            return TrackResult(record=record, maintenance_verified_event=event)

        self._store.put(record)
        return TrackResult(record=record, maintenance_verified_event=None)

    def get(self, maintenance_id: str) -> VerificationRecordMutable | None:
        """Return one verification by maintenance ID."""

        return self._store.get(maintenance_id)

    def list(self, *, status: str | None = None, asset_id: str | None = None) -> list[VerificationRecordMutable]:
        """List verification records filtered by status/asset."""

        return self._store.list(status=status, asset_id=asset_id)

    def connect_sepolia(self) -> SepoliaConnectionResponse:
        """Verify Sepolia RPC connectivity and optional contract availability."""

        checked_at = datetime.now(tz=timezone.utc)
        configured_contract = self._settings.sepolia_contract_address
        contract_address = self._normalize_contract_address(configured_contract)
        contract_warning = ""
        if configured_contract and contract_address is None:
            contract_warning = (
                " Invalid BLOCKCHAIN_VERIFICATION_SEPOLIA_CONTRACT_ADDRESS was ignored "
                "(expected 0x + 40 hex chars)."
            )

        if not self._settings.sepolia_rpc_url:
            return SepoliaConnectionResponse(
                connected=False,
                expected_chain_id=self._settings.sepolia_chain_id,
                chain_id=None,
                latest_block=None,
                contract_address=contract_address,
                contract_deployed=None,
                checked_at=checked_at,
                message=(
                    "Sepolia RPC is not configured. Set BLOCKCHAIN_VERIFICATION_SEPOLIA_RPC_URL."
                    f"{contract_warning}"
                ),
            )

        client = SepoliaRpcClient(
            rpc_url=self._settings.sepolia_rpc_url,
            timeout_seconds=self._settings.sepolia_rpc_timeout_seconds,
        )

        try:
            chain_id = client.get_chain_id()
            latest_block = client.get_latest_block_number()
        except SepoliaRpcError as exc:
            return SepoliaConnectionResponse(
                connected=False,
                expected_chain_id=self._settings.sepolia_chain_id,
                chain_id=None,
                latest_block=None,
                contract_address=contract_address,
                contract_deployed=None,
                checked_at=checked_at,
                message=f"Sepolia RPC connection failed: {exc}.{contract_warning}",
            )

        if chain_id != self._settings.sepolia_chain_id:
            return SepoliaConnectionResponse(
                connected=False,
                expected_chain_id=self._settings.sepolia_chain_id,
                chain_id=chain_id,
                latest_block=latest_block,
                contract_address=contract_address,
                contract_deployed=None,
                checked_at=checked_at,
                message=(
                    f"Connected RPC chain_id={chain_id}, expected "
                    f"{self._settings.sepolia_chain_id} (Sepolia).{contract_warning}"
                ),
            )

        contract_deployed: bool | None = None
        message = f"Connected to Sepolia RPC.{contract_warning}"

        if contract_address:
            try:
                contract_deployed = client.contract_is_deployed(contract_address)
            except SepoliaRpcError as exc:
                return SepoliaConnectionResponse(
                    connected=False,
                    expected_chain_id=self._settings.sepolia_chain_id,
                    chain_id=chain_id,
                    latest_block=latest_block,
                    contract_address=contract_address,
                    contract_deployed=None,
                    checked_at=checked_at,
                    message=f"Sepolia contract lookup failed: {exc}.{contract_warning}",
                )

            if not contract_deployed:
                message = f"Connected to Sepolia, but no contract code at {contract_address}."

        return SepoliaConnectionResponse(
            connected=True,
            expected_chain_id=self._settings.sepolia_chain_id,
            chain_id=chain_id,
            latest_block=latest_block,
            contract_address=contract_address,
            contract_deployed=contract_deployed,
            checked_at=checked_at,
            message=message,
        )

    @staticmethod
    def _normalize_contract_address(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if re.fullmatch(r"0x[a-fA-F0-9]{40}", normalized):
            return normalized
        return None

    @staticmethod
    def _build_tx_hash(command: VerificationRecordBlockchainCommand) -> str:
        payload = {
            "maintenance_id": command.payload.maintenance_id,
            "asset_id": command.payload.asset_id,
            "evidence_hash": command.payload.evidence_hash,
            "network": command.payload.network,
            "contract_address": command.payload.contract_address,
            "chain_id": command.payload.chain_id,
            "command_id": str(command.command_id),
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return f"0x{digest}"

    def _derive_block_number(self, tx_hash: str) -> int:
        seed = int(tx_hash[2:10], 16)
        return self._settings.initial_block_number + (seed % 50000)

    @staticmethod
    def _build_fallback_hash(maintenance_id: str) -> str:
        digest = hashlib.sha256(maintenance_id.encode("utf-8")).hexdigest()
        return f"0x{digest}"

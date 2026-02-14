"""Core logic for blockchain verification submission and confirmation tracking."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any
from urllib.parse import urlparse

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


@dataclass(frozen=True)
class LiveSubmissionResult:
    """Result of live-mode transaction submission attempt."""

    verification_status: str
    tx_hash: str | None
    block_number: int | None
    submitted_at: datetime | None
    failure_reason: str | None


class BlockchainVerificationEngine:
    """Handles verification record creation and confirmation state transitions."""

    def __init__(self, *, settings: Settings, store: InMemoryVerificationStore) -> None:
        self._settings = settings
        self._store = store

    def reset_state_for_tests(self) -> None:
        """Reset in-memory state for deterministic tests."""

        self._store.reset()

    def record(self, command: VerificationRecordBlockchainCommand) -> VerificationRecordMutable:
        """Create verification record from command payload."""

        existing = self._store.get(command.payload.maintenance_id)
        if existing is not None:
            raise ValueError(f"verification already exists for maintenance_id={command.payload.maintenance_id}")

        now = datetime.now(tz=timezone.utc)
        verification_id = self._store.next_verification_id(now)
        tx_mode = self._tx_mode()
        tx_hash: str | None = None
        block_number: int | None = None
        verification_status = "submitted"
        failure_reason: str | None = None
        submitted_at: datetime | None = now

        if tx_mode == "live":
            live_submission = self._submit_live_transaction(command, now)
            verification_status = live_submission.verification_status
            tx_hash = live_submission.tx_hash
            block_number = live_submission.block_number
            submitted_at = live_submission.submitted_at
            failure_reason = live_submission.failure_reason
        else:
            tx_hash = self._build_tx_hash(command)
            block_number = self._derive_block_number(tx_hash)

        record = VerificationRecordMutable(
            verification_id=verification_id,
            command_id=str(command.command_id),
            maintenance_id=command.payload.maintenance_id,
            asset_id=command.payload.asset_id,
            verification_status=verification_status,
            evidence_hash=command.payload.evidence_hash,
            tx_hash=tx_hash,
            network=command.payload.network,
            contract_address=command.payload.contract_address,
            chain_id=command.payload.chain_id,
            block_number=block_number,
            confirmations=0,
            required_confirmations=self._settings.required_confirmations,
            submitted_at=submitted_at,
            confirmed_at=None,
            failure_reason=failure_reason,
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

        if self._tx_mode() == "live":
            return self._track_live_record(record)
        return self._track_deterministic_record(record)

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

        rpc_urls = self._sepolia_rpc_candidates()
        if not rpc_urls:
            return SepoliaConnectionResponse(
                connected=False,
                expected_chain_id=self._settings.sepolia_chain_id,
                chain_id=None,
                latest_block=None,
                contract_address=contract_address,
                contract_deployed=None,
                checked_at=checked_at,
                message=(
                    "Sepolia RPC is not configured. Set BLOCKCHAIN_VERIFICATION_SEPOLIA_RPC_URL "
                    "or BLOCKCHAIN_VERIFICATION_SEPOLIA_RPC_FALLBACK_URLS_CSV."
                    f"{contract_warning}"
                ),
            )
        selected_rpc_label = ""
        selected_client: SepoliaRpcClient | None = None
        chain_id: int | None = None
        latest_block: int | None = None
        last_rpc_error: str | None = None
        last_chain_mismatch_chain_id: int | None = None
        last_chain_mismatch_latest_block: int | None = None

        for rpc_url in rpc_urls:
            rpc_label = self._rpc_label(rpc_url)
            candidate_client = SepoliaRpcClient(
                rpc_url=rpc_url,
                timeout_seconds=self._settings.sepolia_rpc_timeout_seconds,
            )
            try:
                candidate_chain_id = candidate_client.get_chain_id()
                candidate_latest_block = candidate_client.get_latest_block_number()
            except SepoliaRpcError as exc:
                last_rpc_error = f"{rpc_label}: {exc}"
                continue

            if candidate_chain_id != self._settings.sepolia_chain_id:
                last_chain_mismatch_chain_id = candidate_chain_id
                last_chain_mismatch_latest_block = candidate_latest_block
                last_rpc_error = (
                    f"{rpc_label}: chain_id={candidate_chain_id}, "
                    f"expected={self._settings.sepolia_chain_id}"
                )
                continue

            selected_rpc_label = rpc_label
            selected_client = candidate_client
            chain_id = candidate_chain_id
            latest_block = candidate_latest_block
            break

        if selected_client is None:
            message = f"Sepolia RPC connection failed across {len(rpc_urls)} endpoint(s)."
            if last_rpc_error:
                message = f"{message} Last error: {last_rpc_error}."
            if len(message) > 480:
                message = message[:480]
            return SepoliaConnectionResponse(
                connected=False,
                expected_chain_id=self._settings.sepolia_chain_id,
                chain_id=last_chain_mismatch_chain_id,
                latest_block=last_chain_mismatch_latest_block,
                contract_address=contract_address,
                contract_deployed=None,
                checked_at=checked_at,
                message=f"{message}{contract_warning}",
            )

        contract_deployed: bool | None = None
        message = f"Connected to Sepolia RPC via {selected_rpc_label}.{contract_warning}"

        if contract_address:
            try:
                contract_deployed = selected_client.contract_is_deployed(contract_address)
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

    def _tx_mode(self) -> str:
        mode = (self._settings.tx_mode or "deterministic").strip().lower()
        if mode == "live":
            return "live"
        return "deterministic"

    def _track_deterministic_record(self, record: VerificationRecordMutable) -> TrackResult:
        record.confirmations += 1
        now = datetime.now(tz=timezone.utc)
        record.updated_at = now

        if record.confirmations >= record.required_confirmations:
            return self._confirm_record(record, now)

        self._store.put(record)
        return TrackResult(record=record, maintenance_verified_event=None)

    def _track_live_record(self, record: VerificationRecordMutable) -> TrackResult:
        now = datetime.now(tz=timezone.utc)
        record.updated_at = now

        if not record.tx_hash:
            record.verification_status = "failed"
            record.failure_reason = "live mode tracking requires tx_hash"
            self._store.put(record)
            return TrackResult(record=record, maintenance_verified_event=None)

        client, rpc_label, select_error = self._select_live_rpc_client()
        if client is None:
            # Keep status submitted so polling can continue when RPC recovers.
            if select_error:
                record.failure_reason = f"live tracking unavailable: {select_error}"
            self._store.put(record)
            return TrackResult(record=record, maintenance_verified_event=None)

        try:
            receipt = client.get_transaction_receipt(record.tx_hash)
            if receipt is None:
                self._store.put(record)
                return TrackResult(record=record, maintenance_verified_event=None)

            status = str(receipt.get("status", "0x1")).lower()
            if status in {"0x0", "0"}:
                record.verification_status = "failed"
                record.failure_reason = f"live transaction reverted via {rpc_label}"
                self._store.put(record)
                return TrackResult(record=record, maintenance_verified_event=None)

            record.failure_reason = None
            block_number = self._parse_hex_int(receipt.get("blockNumber"))
            if block_number is not None:
                record.block_number = block_number
                latest_block = client.get_latest_block_number()
                record.confirmations = max(0, latest_block - block_number + 1)

            if record.confirmations >= record.required_confirmations:
                return self._confirm_record(record, now)

            self._store.put(record)
            return TrackResult(record=record, maintenance_verified_event=None)
        except SepoliaRpcError as exc:
            record.failure_reason = f"live tracking RPC error: {exc}"
            self._store.put(record)
            return TrackResult(record=record, maintenance_verified_event=None)

    def _confirm_record(self, record: VerificationRecordMutable, now: datetime) -> TrackResult:
        record.verification_status = "confirmed"
        record.confirmed_at = now
        record.failure_reason = None
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

    def _submit_live_transaction(
        self,
        command: VerificationRecordBlockchainCommand,
        now: datetime,
    ) -> LiveSubmissionResult:
        if command.payload.network.lower() != "sepolia":
            return LiveSubmissionResult(
                verification_status="failed",
                tx_hash=None,
                block_number=None,
                submitted_at=None,
                failure_reason=f"live mode supports only sepolia network, got '{command.payload.network}'",
            )
        if command.payload.chain_id != self._settings.sepolia_chain_id:
            return LiveSubmissionResult(
                verification_status="failed",
                tx_hash=None,
                block_number=None,
                submitted_at=None,
                failure_reason=(
                    f"chain_id mismatch: expected {self._settings.sepolia_chain_id}, "
                    f"got {command.payload.chain_id}"
                ),
            )

        private_key = (self._settings.signer_private_key or "").strip()
        if not private_key:
            return LiveSubmissionResult(
                verification_status="failed",
                tx_hash=None,
                block_number=None,
                submitted_at=None,
                failure_reason="live mode requires BLOCKCHAIN_VERIFICATION_SIGNER_PRIVATE_KEY",
            )
        if not private_key.startswith("0x"):
            private_key = f"0x{private_key}"

        try:
            from eth_account import Account  # type: ignore
        except Exception as exc:  # pragma: no cover - depends on optional dependency
            return LiveSubmissionResult(
                verification_status="failed",
                tx_hash=None,
                block_number=None,
                submitted_at=None,
                failure_reason=f"live mode requires eth-account dependency: {exc}",
            )

        client, rpc_label, select_error = self._select_live_rpc_client()
        if client is None:
            return LiveSubmissionResult(
                verification_status="failed",
                tx_hash=None,
                block_number=None,
                submitted_at=None,
                failure_reason=select_error or "no reachable Sepolia RPC endpoint",
            )

        try:
            account = Account.from_key(private_key)
        except Exception as exc:
            return LiveSubmissionResult(
                verification_status="failed",
                tx_hash=None,
                block_number=None,
                submitted_at=None,
                failure_reason=f"invalid service wallet private key: {exc}",
            )

        try:
            tx_data = self._encode_record_verification_call(command)
        except RuntimeError as exc:
            return LiveSubmissionResult(
                verification_status="failed",
                tx_hash=None,
                block_number=None,
                submitted_at=None,
                failure_reason=str(exc),
            )

        try:
            nonce = client.get_transaction_count(account.address, "pending")
            gas_price = client.get_gas_price_wei()
        except SepoliaRpcError as exc:
            return LiveSubmissionResult(
                verification_status="failed",
                tx_hash=None,
                block_number=None,
                submitted_at=None,
                failure_reason=f"live mode preflight failed via {rpc_label}: {exc}",
            )

        gas_price_cap = max(self._settings.max_gas_gwei, 1) * 1_000_000_000
        gas_price = min(gas_price, gas_price_cap)

        tx_template: dict[str, Any] = {
            "to": command.payload.contract_address,
            "value": 0,
            "data": tx_data,
            "chainId": command.payload.chain_id,
            "gas": max(self._settings.gas_limit, 21000),
            "gasPrice": gas_price,
        }

        last_error: str | None = None
        for nonce_offset in (0, 1):
            tx_payload = dict(tx_template)
            tx_payload["nonce"] = nonce + nonce_offset
            try:
                signed = Account.sign_transaction(tx_payload, private_key)
                raw_bytes = getattr(signed, "raw_transaction", None)
                if raw_bytes is None:
                    raw_bytes = getattr(signed, "rawTransaction")
                raw_hex = "0x" + bytes(raw_bytes).hex()
                tx_hash = client.send_raw_transaction(raw_hex)
                latest_block = client.get_latest_block_number()
                return LiveSubmissionResult(
                    verification_status="submitted",
                    tx_hash=tx_hash,
                    block_number=latest_block,
                    submitted_at=now,
                    failure_reason=None,
                )
            except SepoliaRpcError as exc:
                message = str(exc)
                last_error = message
                if "nonce too low" in message.lower() and nonce_offset == 0:
                    continue
                break
            except Exception as exc:  # pragma: no cover - defensive
                last_error = str(exc)
                break

        return LiveSubmissionResult(
            verification_status="failed",
            tx_hash=None,
            block_number=None,
            submitted_at=None,
            failure_reason=f"live tx submit failed via {rpc_label}: {last_error or 'unknown error'}",
        )

    def _select_live_rpc_client(self) -> tuple[SepoliaRpcClient | None, str | None, str | None]:
        rpc_urls = self._sepolia_rpc_candidates()
        if not rpc_urls:
            return None, None, "SEPOLIA RPC endpoint is not configured"

        last_error: str | None = None
        for rpc_url in rpc_urls:
            client = SepoliaRpcClient(
                rpc_url=rpc_url,
                timeout_seconds=self._settings.sepolia_rpc_timeout_seconds,
            )
            label = self._rpc_label(rpc_url)
            try:
                chain_id = client.get_chain_id()
            except SepoliaRpcError as exc:
                last_error = f"{label}: {exc}"
                continue

            if chain_id != self._settings.sepolia_chain_id:
                last_error = (
                    f"{label}: chain_id mismatch {chain_id}, "
                    f"expected {self._settings.sepolia_chain_id}"
                )
                continue
            return client, label, None

        return None, None, last_error or "no healthy Sepolia RPC endpoint"

    def _encode_record_verification_call(self, command: VerificationRecordBlockchainCommand) -> str:
        try:
            from eth_abi import encode as abi_encode  # type: ignore
            from eth_utils import keccak  # type: ignore
        except Exception as exc:  # pragma: no cover - depends on optional dependency
            raise RuntimeError(f"live mode requires eth-abi and eth-utils dependencies: {exc}") from exc

        evidence_hash_hex = command.payload.evidence_hash[2:]
        evidence_hash_bytes = bytes.fromhex(evidence_hash_hex)
        selector = keccak(text="recordVerification(string,string,bytes32)")[:4]
        encoded_args = abi_encode(
            ["string", "string", "bytes32"],
            [
                command.payload.maintenance_id,
                command.payload.asset_id,
                evidence_hash_bytes,
            ],
        )
        return "0x" + (selector + encoded_args).hex()

    @staticmethod
    def _parse_hex_int(value: object) -> int | None:
        if value is None:
            return None
        if not isinstance(value, str) or not value.startswith("0x"):
            return None
        try:
            return int(value, 16)
        except ValueError:
            return None

    def _sepolia_rpc_candidates(self) -> list[str]:
        """Return deduplicated list of configured RPC endpoints, ordered by priority."""

        candidates: list[str] = []
        seen: set[str] = set()

        def _append(raw: str | None) -> None:
            if raw is None:
                return
            normalized = raw.strip()
            if not normalized or normalized in seen:
                return
            seen.add(normalized)
            candidates.append(normalized)

        _append(self._settings.sepolia_rpc_url)
        for value in self._settings.sepolia_rpc_fallback_urls_csv.split(","):
            _append(value)

        return candidates

    @staticmethod
    def _rpc_label(rpc_url: str) -> str:
        parsed = urlparse(rpc_url)
        if parsed.netloc:
            return parsed.netloc
        return rpc_url

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

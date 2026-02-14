"""Minimal JSON-RPC client for Sepolia network checks."""

from __future__ import annotations

import json
from urllib import error as url_error
from urllib import request as url_request


class SepoliaRpcError(RuntimeError):
    """Raised when Sepolia RPC requests fail."""


class SepoliaRpcClient:
    """JSON-RPC client for read-only Sepolia connectivity checks."""

    def __init__(self, *, rpc_url: str, timeout_seconds: float) -> None:
        self._rpc_url = rpc_url
        self._timeout_seconds = max(timeout_seconds, 0.1)

    def get_chain_id(self) -> int:
        raw = self._call("eth_chainId", [])
        return _parse_hex_int(raw, field_name="chain_id")

    def get_latest_block_number(self) -> int:
        raw = self._call("eth_blockNumber", [])
        return _parse_hex_int(raw, field_name="latest_block")

    def contract_is_deployed(self, contract_address: str) -> bool:
        raw = self._call("eth_getCode", [contract_address, "latest"])
        if not isinstance(raw, str):
            raise SepoliaRpcError("invalid contract code response from RPC")
        normalized = raw.lower()
        return normalized not in {"0x", "0x0", "0x00"}

    def _call(self, method: str, params: list[object]) -> object:
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": 1,
        }
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        request = url_request.Request(
            url=self._rpc_url,
            data=raw,
            method="POST",
            headers={"Content-Type": "application/json"},
        )

        try:
            with url_request.urlopen(request, timeout=self._timeout_seconds) as response:
                response_body = response.read().decode("utf-8")
        except url_error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="ignore")
            raise SepoliaRpcError(f"rpc_http_error status={exc.code} body={details[:200]}") from exc
        except url_error.URLError as exc:
            raise SepoliaRpcError(f"rpc_unreachable reason={exc.reason}") from exc

        try:
            body = json.loads(response_body)
        except json.JSONDecodeError as exc:
            raise SepoliaRpcError("rpc_invalid_json_response") from exc

        if not isinstance(body, dict):
            raise SepoliaRpcError("rpc_invalid_response_shape")

        if body.get("error"):
            rpc_error = body["error"]
            if isinstance(rpc_error, dict):
                code = rpc_error.get("code")
                message = rpc_error.get("message")
                raise SepoliaRpcError(f"rpc_error code={code} message={message}")
            raise SepoliaRpcError(f"rpc_error payload={rpc_error}")

        if "result" not in body:
            raise SepoliaRpcError("rpc_missing_result")

        return body["result"]


def _parse_hex_int(value: object, *, field_name: str) -> int:
    if not isinstance(value, str) or not value.startswith("0x"):
        raise SepoliaRpcError(f"invalid_hex_{field_name}")
    try:
        return int(value, 16)
    except ValueError as exc:
        raise SepoliaRpcError(f"invalid_{field_name}_value") from exc

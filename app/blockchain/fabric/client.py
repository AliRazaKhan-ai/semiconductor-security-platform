"""Production Hyperledger Fabric adapter implemented through the supported peer CLI."""
from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

from app.blockchain.fabric.identity import FabricIdentity

_TX_PATTERNS = (
    re.compile(r"txid \[([0-9a-fA-F]+)\]"),
    re.compile(r"txid[:=]\s*([0-9a-fA-F]+)", re.IGNORECASE),
)


@dataclass(frozen=True, slots=True)
class CommandResult:
    stdout: str
    stderr: str
    returncode: int


class FabricCommandError(RuntimeError):
    def __init__(self, message: str, result: CommandResult) -> None:
        super().__init__(message)
        self.result = result


Runner = Callable[[Sequence[str], dict[str, str], int], CommandResult]


def _default_runner(command: Sequence[str], environment: dict[str, str], timeout: int) -> CommandResult:
    process = subprocess.run(
        list(command),
        env=environment,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return CommandResult(process.stdout.strip(), process.stderr.strip(), process.returncode)


class FabricClient:
    def __init__(
        self,
        *,
        identity: FabricIdentity,
        channel: str,
        chaincode: str,
        timeout_seconds: int = 120,
        wait_for_event_timeout: str = "60s",
        runner: Runner | None = None,
    ) -> None:
        self.identity = identity
        self.channel = channel
        self.chaincode = chaincode
        self.timeout_seconds = timeout_seconds
        self.wait_for_event_timeout = wait_for_event_timeout
        self.runner = runner or _default_runner

    def _run(self, command: list[str]) -> CommandResult:
        env = dict(os.environ)
        env.update(self.identity.environment())
        result = self.runner(command, env, self.timeout_seconds)
        if result.returncode != 0:
            raise FabricCommandError(
                f"Fabric command failed with exit code {result.returncode}: {result.stderr or result.stdout}",
                result,
            )
        return result

    @staticmethod
    def _ctor(function: str, arguments: Sequence[str]) -> str:
        return json.dumps({"Args": [function, *map(str, arguments)]}, separators=(",", ":"))

    def evaluate(self, function: str, arguments: Sequence[str] = ()) -> Any:
        command = [
            self.identity.peer_binary, "chaincode", "query",
            "-C", self.channel,
            "-n", self.chaincode,
            "-c", self._ctor(function, arguments),
            "--tls",
            "--cafile", str(self.identity.orderer_tls_root_cert),
        ]
        result = self._run(command)
        if not result.stdout:
            return None
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return result.stdout

    def submit(
        self,
        function: str,
        arguments: Sequence[str] = (),
        *,
        transient: dict[str, str] | None = None,
    ) -> str:
        command = [
            self.identity.peer_binary, "chaincode", "invoke",
            "-o", self.identity.orderer_address,
            "--ordererTLSHostnameOverride", self.identity.orderer_address.split(":", 1)[0],
            "--tls",
            "--cafile", str(self.identity.orderer_tls_root_cert),
            "-C", self.channel,
            "-n", self.chaincode,
            "-c", self._ctor(function, arguments),
            "--peerAddresses", "localhost:7051",
            "--tlsRootCertFiles", str(Path.home() / "hyperledger/fabric-samples/test-network/organizations/peerOrganizations/org1.example.com/peers/peer0.org1.example.com/tls/ca.crt"),
            "--peerAddresses", "localhost:9051",
            "--tlsRootCertFiles", str(Path.home() / "hyperledger/fabric-samples/test-network/organizations/peerOrganizations/org2.example.com/peers/peer0.org2.example.com/tls/ca.crt"),
            "--waitForEvent",
            "--waitForEventTimeout", self.wait_for_event_timeout,
        ]
        if transient:
            command.extend(["--transient", json.dumps(transient, separators=(",", ":"))])
        result = self._run(command)
        combined = "\n".join(part for part in (result.stdout, result.stderr) if part)
        for pattern in _TX_PATTERNS:
            match = pattern.search(combined)
            if match:
                return match.group(1).lower()
        raise FabricCommandError("Fabric invoke completed but no transaction ID was returned", result)

    def health(self) -> dict[str, Any]:
        self.identity.validate()
        info = self.evaluate("GetNetworkMetadata")
        return {"connected": True, "metadata": info}

"""Hyperledger Fabric peer identity and TLS environment construction."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class FabricIdentity:
    msp_id: str
    msp_config_path: Path
    peer_address: str
    peer_tls_root_cert: Path
    orderer_address: str
    orderer_tls_root_cert: Path
    peer_binary: str = "peer"
    # Endorsing peers for submit(). The chaincode endorsement policy spans both
    # organisations, so an invoke must name every endorser and its TLS root cert.
    # These were previously hardcoded to localhost:7051, localhost:9051 and paths
    # under Path.home(), which tied the platform to one machine and one account.
    endorsers: tuple[tuple[str, Path], ...] = ()

    @classmethod
    def from_config(cls, root: Path, config: dict[str, Any]) -> "FabricIdentity":
        def resolved(key: str) -> Path:
            path = Path(str(config[key]))
            return path if path.is_absolute() else (root / path).resolve()

        def resolve_path(value: str) -> Path:
            path = Path(str(value))
            return path if path.is_absolute() else (root / path).resolve()

        endorsers = tuple(
            (str(entry["address"]), resolve_path(entry["tls_root_cert"]))
            for entry in config.get("endorsers", ())
        )

        identity = cls(
            msp_id=str(config["msp_id"]),
            msp_config_path=resolved("msp_config_path"),
            peer_address=str(config["peer_address"]),
            peer_tls_root_cert=resolved("peer_tls_root_cert"),
            orderer_address=str(config["orderer_address"]),
            orderer_tls_root_cert=resolved("orderer_tls_root_cert"),
            peer_binary=str(config.get("peer_binary", "peer")),
            endorsers=endorsers,
        )
        return identity

    def validate(self) -> None:
        for label, path in (
            ("msp_config_path", self.msp_config_path),
            ("peer_tls_root_cert", self.peer_tls_root_cert),
            ("orderer_tls_root_cert", self.orderer_tls_root_cert),
            *(
                (f"endorser {address} tls_root_cert", cert)
                for address, cert in self.endorsers
            ),
        ):
            if not path.exists():
                raise FileNotFoundError(f"Fabric {label} does not exist: {path}")

    def environment(self) -> dict[str, str]:
        return {
            "CORE_PEER_LOCALMSPID": self.msp_id,
            "CORE_PEER_MSPCONFIGPATH": str(self.msp_config_path),
            "CORE_PEER_ADDRESS": self.peer_address,
            "CORE_PEER_TLS_ENABLED": "true",
            "CORE_PEER_TLS_ROOTCERT_FILE": str(self.peer_tls_root_cert),
        }

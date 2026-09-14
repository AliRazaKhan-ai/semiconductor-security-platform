from pathlib import Path

import pytest

from app.blockchain.fabric.client import (
    CommandResult,
    FabricClient,
    FabricCommandError,
)
from app.blockchain.fabric.identity import FabricIdentity


def _identity(tmp_path, endorsers=None):
    msp = tmp_path / "msp"
    msp.mkdir(exist_ok=True)
    peer = tmp_path / "peer.crt"
    peer.write_text("x")
    orderer = tmp_path / "orderer.crt"
    orderer.write_text("x")
    return FabricIdentity(
        "LabMSP",
        msp,
        "localhost:7051",
        peer,
        "localhost:7050",
        orderer,
        endorsers=tuple(endorsers or ()),
    )


def test_submit_extracts_transaction_id(tmp_path):
    identity = _identity(
        tmp_path,
        [("localhost:7051", tmp_path / "peer.crt")],
    )

    def runner(command, environment, timeout):
        return CommandResult(
            "",
            "Chaincode invoke successful. result: status:200 txid [abcdef1234]",
            0,
        )

    client = FabricClient(
        identity=identity, channel="c", chaincode="cc", runner=runner
    )
    assert client.submit("F", ["a"]) == "abcdef1234"


def test_submit_names_every_configured_endorser(tmp_path):
    """The endorsement policy spans both orgs, so an invoke must name both peers."""
    org2 = tmp_path / "org2.crt"
    org2.write_text("x")
    identity = _identity(
        tmp_path,
        [
            ("localhost:7051", tmp_path / "peer.crt"),
            ("localhost:9051", org2),
        ],
    )

    captured: list[str] = []

    def runner(command, environment, timeout):
        captured.extend(command)
        return CommandResult("", "txid [abcdef1234]", 0)

    client = FabricClient(
        identity=identity, channel="c", chaincode="cc", runner=runner
    )
    client.submit("F", ["a"])

    assert captured.count("--peerAddresses") == 2
    assert "localhost:7051" in captured
    assert "localhost:9051" in captured
    assert str(org2) in captured


def test_submit_refuses_when_no_endorser_is_configured(tmp_path):
    """An invoke with no endorsers cannot satisfy the policy, so it must not run."""
    client = FabricClient(
        identity=_identity(tmp_path),
        channel="c",
        chaincode="cc",
        runner=lambda command, environment, timeout: CommandResult("", "", 0),
    )

    with pytest.raises(FabricCommandError, match="no endorsing peers"):
        client.submit("F", ["a"])

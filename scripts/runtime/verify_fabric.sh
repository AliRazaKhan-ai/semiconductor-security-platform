#!/usr/bin/env bash
set -Eeuo pipefail

FABRIC_ROOT="$HOME/hyperledger/fabric-samples"
NETWORK_ROOT="$FABRIC_ROOT/test-network"

export PATH="$FABRIC_ROOT/bin:$PATH"
export FABRIC_CFG_PATH="$FABRIC_ROOT/config"

export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_LOCALMSPID="Org1MSP"
export CORE_PEER_ADDRESS="localhost:7051"

export CORE_PEER_TLS_ROOTCERT_FILE="$NETWORK_ROOT/organizations/peerOrganizations/org1.example.com/peers/peer0.org1.example.com/tls/ca.crt"

export CORE_PEER_MSPCONFIGPATH="$NETWORK_ROOT/organizations/peerOrganizations/org1.example.com/users/Admin@org1.example.com/msp"

CHANNEL_NAME="semiconductor-channel"
CHAINCODE_NAME="semiconductor-provenance"
MAX_ATTEMPTS="${FABRIC_VERIFY_ATTEMPTS:-30}"
RETRY_DELAY="${FABRIC_VERIFY_DELAY_SECONDS:-2}"

required_paths=(
    "$CORE_PEER_TLS_ROOTCERT_FILE"
    "$CORE_PEER_MSPCONFIGPATH/signcerts"
    "$CORE_PEER_MSPCONFIGPATH/keystore"
)

for path in "${required_paths[@]}"
do
    if [[ ! -e "$path" ]]
    then
        echo "ERROR: required Fabric identity material is missing:"
        echo "$path"
        exit 1
    fi
done

last_error=""

for attempt in $(seq 1 "$MAX_ATTEMPTS")
do
    if ! timeout 2 bash -c '</dev/tcp/127.0.0.1/7051' \
        >/dev/null 2>&1
    then
        last_error="peer port 7051 is not reachable"
        echo "  Fabric verification attempt $attempt/$MAX_ATTEMPTS: $last_error"
        sleep "$RETRY_DELAY"
        continue
    fi

    if ! channels="$(
        peer channel list 2>&1
    )"
    then
        last_error="$channels"
        echo "  Fabric verification attempt $attempt/$MAX_ATTEMPTS: peer channel list failed"
        sleep "$RETRY_DELAY"
        continue
    fi

    if ! grep -Fxq "$CHANNEL_NAME" <<<"$channels"
    then
        last_error="channel $CHANNEL_NAME is not listed"
        echo "  Fabric verification attempt $attempt/$MAX_ATTEMPTS: $last_error"
        sleep "$RETRY_DELAY"
        continue
    fi

    if ! committed="$(
        peer lifecycle chaincode querycommitted \
            --channelID "$CHANNEL_NAME" \
            --name "$CHAINCODE_NAME" \
            2>&1
    )"
    then
        last_error="$committed"
        echo "  Fabric verification attempt $attempt/$MAX_ATTEMPTS: chaincode query failed"
        sleep "$RETRY_DELAY"
        continue
    fi

    if ! grep -q \
        "Committed chaincode definition for chaincode '$CHAINCODE_NAME'" \
        <<<"$committed"
    then
        last_error="$committed"
        echo "  Fabric verification attempt $attempt/$MAX_ATTEMPTS: chaincode is not committed"
        sleep "$RETRY_DELAY"
        continue
    fi

    if ! metadata="$(
        peer chaincode query \
            -C "$CHANNEL_NAME" \
            -n "$CHAINCODE_NAME" \
            -c '{"Args":["GetNetworkMetadata"]}' \
            2>&1
    )"
    then
        last_error="$metadata"
        echo "  Fabric verification attempt $attempt/$MAX_ATTEMPTS: chaincode is not ready"
        sleep "$RETRY_DELAY"
        continue
    fi

    if ! python - "$metadata" <<'PY'
import json
import sys

metadata = json.loads(sys.argv[1])

if metadata.get("chaincode") != "semiconductor-provenance":
    raise SystemExit("unexpected chaincode metadata")

if metadata.get("schema_version") != "1.0":
    raise SystemExit("unexpected schema version")

print(json.dumps(metadata, indent=2))
PY
    then
        last_error="chaincode metadata validation failed: $metadata"
        echo "  Fabric verification attempt $attempt/$MAX_ATTEMPTS: metadata invalid"
        sleep "$RETRY_DELAY"
        continue
    fi

    echo
    echo "FABRIC NETWORK VERIFIED"
    echo "$committed"
    exit 0
done

echo
echo "ERROR: Fabric did not become fully ready after $MAX_ATTEMPTS attempts."
echo "Last error:"
echo "$last_error"

echo
echo "Container status:"
docker ps -a \
    --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' \
    | grep -E \
        'NAMES|peer0\.org|orderer\.example|dev-peer' \
    || true

echo
echo "Org1 peer logs:"
docker logs \
    --tail 80 \
    peer0.org1.example.com \
    2>&1 || true

exit 1

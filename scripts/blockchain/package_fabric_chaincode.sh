#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-$(pwd)}"
LABEL="${2:-semiconductor-provenance_1.0}"
cd "$ROOT/blockchain/fabric/chaincode/semiconductor_provenance"
go mod download
go test ./...
peer lifecycle chaincode package "$ROOT/blockchain/fabric/packages/${LABEL}.tar.gz" --path . --lang golang --label "$LABEL"
echo "Created blockchain/fabric/packages/${LABEL}.tar.gz"

#!/usr/bin/env python3
"""Compile and deploy HashAnchor using solcx and web3."""
from __future__ import annotations
import argparse, json, os
from pathlib import Path
from solcx import compile_standard, install_solc
from web3 import Web3


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rpc-url", required=True)
    parser.add_argument("--private-key-env", default="SEMISURE_ETHEREUM_PRIVATE_KEY")
    parser.add_argument("--chain-id", required=True, type=int)
    parser.add_argument("--source", default="blockchain/ethereum/contracts/HashAnchor.sol")
    parser.add_argument("--output", default="blockchain/ethereum/deployments/hash_anchor.json")
    args = parser.parse_args()
    private_key = os.environ.get(args.private_key_env)
    if not private_key: raise SystemExit(f"missing environment variable {args.private_key_env}")
    source = Path(args.source).read_text(encoding="utf-8")
    install_solc("0.8.24")
    compiled = compile_standard({"language":"Solidity","sources":{"HashAnchor.sol":{"content":source}},"settings":{"outputSelection":{"*":{"*":["abi","evm.bytecode.object"]}}}}, solc_version="0.8.24")
    artifact = compiled["contracts"]["HashAnchor.sol"]["HashAnchor"]
    web3 = Web3(Web3.HTTPProvider(args.rpc_url))
    account = web3.eth.account.from_key(private_key)
    contract = web3.eth.contract(abi=artifact["abi"], bytecode=artifact["evm"]["bytecode"]["object"])
    tx = contract.constructor().build_transaction({"from":account.address,"nonce":web3.eth.get_transaction_count(account.address,"pending"),"chainId":args.chain_id,"gas":1_000_000,"gasPrice":web3.eth.gas_price})
    signed = account.sign_transaction(tx)
    tx_hash = web3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    if receipt.status != 1: raise SystemExit("deployment reverted")
    output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"address":receipt.contractAddress,"transaction_hash":tx_hash.hex(),"chain_id":args.chain_id,"abi":artifact["abi"]}, indent=2), encoding="utf-8")
    print(receipt.contractAddress)

if __name__ == "__main__": main()

# Network Architecture

Single host. Every address below was read from `ss -ltnp` and
`docker network inspect fabric_test` on the running system.

## Topology

```mermaid
flowchart TB
    subgraph host["VirtualBox guest — single host"]
        subgraph lo["Loopback 127.0.0.1 — not reachable off-host"]
            term["Terminal<br/>manage.py, make semi-*"]
            api["Flask / gunicorn<br/>127.0.0.1:5000<br/>1 worker, GeventWebSocket"]
            anvil["Anvil<br/>127.0.0.1:8545<br/>chain 31337"]
        end

        subgraph docker["Docker bridge fabric_test — 172.18.0.0/16"]
            ord["orderer.example.com<br/>172.18.0.2 · :7050"]
            p1["peer0.org1.example.com<br/>172.18.0.3 · :7051"]
            p2["peer0.org2.example.com<br/>172.18.0.4 · :9051"]
            cc1["dev-peer0.org1<br/>semiconductor-provenance 1.2<br/>172.18.0.5"]
            cc2["dev-peer0.org2<br/>semiconductor-provenance 1.2<br/>172.18.0.6"]
        end

        browser["Browser<br/>read-only dashboard"]
    end

    term -->|"mint, then run"| api
    browser -->|"GET only, CORS 127.0.0.1:5000"| api
    api -->|"peer CLI, TLS + MSP"| p1
    api -->|"peer CLI, TLS + MSP"| p2
    api -->|"JSON-RPC, eth_sendRawTransaction"| anvil
    p1 --- ord
    p2 --- ord
    p1 --- cc1
    p2 --- cc2
```

## Listening sockets, as measured

| Service | Bind | Reachable off-host |
|---|---|---|
| Flask / gunicorn | `127.0.0.1:5000` | No |
| Anvil | `127.0.0.1:8545` | No |
| Fabric orderer | `0.0.0.0:7050` | **Yes** |
| Fabric peer0.org1 | `0.0.0.0:7051` | **Yes** |
| Fabric peer0.org2 | `0.0.0.0:9051` | **Yes** |
| Fabric operations | `0.0.0.0:9443-9445` | **Yes** |

The application binds loopback in every environment: `configs/application/app.json`
and all three files under `configs/environments/`.

The Fabric containers publish to every interface. This is the `fabric-samples`
test-network default rather than a configured choice. Access is still gated by TLS
with MSP identity, but it is wider than the boundary `SECURITY.md` describes, and a
deployment outside a trusted network would bind these to loopback or place them on an
internal segment.

## Trust boundaries

Five, matching `docs/security/THREAT_MODEL.md`. Only one is a network edge.

1. **Terminal to platform.** The trust anchor. A user with shell access already holds
   `.env`, the data directory and the MSP material, so the operating-system account is
   the real perimeter. This is why there is no application login.
2. **Platform to external tool processes.** Yosys, Verilator and `peer` run as
   subprocesses through `CommandRunner`: argument lists rather than a shell, bounded
   timeouts, path validation.
3. **Platform to Fabric.** TLS to peer and orderer, MSP identity, endorsement across
   both organisations.
4. **Platform to Ethereum.** Loopback JSON-RPC. The signing key comes from the
   environment, never from configuration.
5. **Platform to browser.** One direction. GET-only client, server-side test, CORS
   restricted to `http://127.0.0.1:5000` and `http://localhost:5000`.

## What is not here

No load balancer, no reverse proxy, no TLS termination in front of the application,
no network segmentation between the application and the ledger, no firewall rules
beyond the host default, no ingress. The platform runs on one host and
`SECURITY.md` requires a controlled network around it.

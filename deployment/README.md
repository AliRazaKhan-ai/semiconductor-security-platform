# Deployment

Three deployments exist and have been run.

**Native.** `make semi-up` starts Docker, the Fabric test-network, the chaincode
runtime, Anvil, the contract and the backend.
`deployment/systemd/semisecure-backend.service` supervises the backend,
restarting it within about fifteen seconds of a failure and starting it at boot.

**Container.** The root Dockerfile builds semisecure:4.0.0, about 5.66 GB on disk
and 1.28 GB compressed, on python:3.12-slim-trixie. The build asserts Yosys 0.52
and Verilator 5.032, the versions this project's evidence was measured with, and
fails if they differ. Synthesising the reference RTL inside the image gives 8
cells, matching evidence/hardware/yosys_structural_delta_evidence.json.
docker-compose.yml runs it on port 5001, joining the existing fabric_test bridge
rather than duplicating Fabric.

**Kubernetes.** deployment/kubernetes holds manifests applied to a local kind
cluster: the pod reports 1/1 Running, readiness ready, no degraded subsystems.
They use hostPath mounts because the platform shells out to the Fabric peer CLI
and needs the binaries and MSP material on disk. That works on a single node; a
managed cluster would need them in a ConfigMap and Secret, or a Fabric gateway
client instead of the CLI.

There is no cloud deployment. LICENSE prohibits use in production, commercial,
governmental, military or critical-infrastructure environments without written
permission.

Evidence for the container and cluster runs is under evidence/deployment/.

Empty legacy Kubernetes, nested Docker, reverse-proxy, systemd and backup
placeholders were removed in 46966b0 and have been reintroduced only where tested
and executable.

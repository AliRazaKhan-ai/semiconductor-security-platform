"""Purpose: Validate local API, dashboard and hashing performance.
Directory: tests/performance.
Dependencies: Flask test client and integration hashing utilities.
Connection: Provides defensible Level 6 evidence for latency and scalability
trade-off discussion.
"""

from __future__ import annotations

import statistics
import time

import pytest

from app.integration.service import canonical_hash


def measure_request(client, path: str, repetitions: int = 20) -> list[float]:
    durations: list[float] = []

    for _ in range(repetitions):
        started = time.perf_counter()
        response = client.get(path)
        elapsed_ms = (time.perf_counter() - started) * 1000

        assert response.status_code == 200
        durations.append(elapsed_ms)

    return durations


@pytest.mark.performance
def test_liveness_p95_under_250_ms(client) -> None:
    durations = measure_request(client, "/health/live")

    p95 = sorted(durations)[int(len(durations) * 0.95) - 1]

    assert p95 < 250


@pytest.mark.performance
def test_system_status_median_under_500_ms(client) -> None:
    durations = measure_request(
        client,
        "/api/v1/system/status",
        repetitions=10,
    )

    assert statistics.median(durations) < 500


@pytest.mark.performance
def test_dashboard_median_under_1000_ms(client) -> None:
    durations = measure_request(
        client,
        "/dashboard",
        repetitions=10,
    )

    assert statistics.median(durations) < 1000


@pytest.mark.performance
def test_one_thousand_canonical_hashes_under_one_second() -> None:
    record = {
        "scan_id": "PERFORMANCE-SCAN",
        "chip_id": "CHIP-PERFORMANCE",
        "decision": "DEPLOY",
        "events": list(range(100)),
    }

    started = time.perf_counter()

    digests = [
        canonical_hash({**record, "sequence": sequence})
        for sequence in range(1000)
    ]

    elapsed = time.perf_counter() - started

    assert elapsed < 1.0
    assert len(set(digests)) == 1000


@pytest.mark.performance
def test_readiness_repeated_requests_are_stable(client) -> None:
    durations = measure_request(
        client,
        "/health/ready",
        repetitions=20,
    )

    assert max(durations) < 1500
    assert statistics.mean(durations) < 500

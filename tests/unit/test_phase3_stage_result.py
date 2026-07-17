from app.pipeline.stage_result import StageResult


def test_stage_result_completes_with_duration() -> None:
    result = StageResult(
        stage="PUF_AUTHENTICATION",
        status="RUNNING",
        risk_score=0.2,
        confidence=0.9,
    ).complete(status="PASSED")

    assert result.status == "PASSED"
    assert result.completed_at_utc is not None
    assert result.duration_ms is not None
    assert result.duration_ms >= 0


def test_stage_result_rejects_invalid_status() -> None:
    try:
        StageResult(
            stage="TEST",
            status="INVALID",
        )
    except ValueError:
        return

    raise AssertionError(
        "Invalid stage status was accepted"
    )

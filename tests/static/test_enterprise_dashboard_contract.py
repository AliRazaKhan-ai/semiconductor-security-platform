"""Purpose: Verify the enterprise dashboard contains all required read-only controls and panels.
Directory: tests/static.
Dependencies: pathlib and BeautifulSoup.
Connection: Guards the dashboard requirements without requiring a running Flask installation.
"""

from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "app" / "dashboard" / "templates" / "dashboard.html"
BASE = ROOT / "app" / "dashboard" / "templates" / "base.html"


def test_required_dashboard_panels_exist() -> None:
    soup = BeautifulSoup(TEMPLATE.read_text(encoding="utf-8"), "html.parser")
    required_ids = {
        "riskTrendChart",
        "goodBadChart",
        "supplierRiskChart",
        "pipelineTrack",
        "liveScanTableBody",
        "blockchain",
        "compliance",
        "hardwareModules",
        "aiModels",
        "notificationPanelList",
        "serviceHealthList",
    }
    assert not [item for item in required_ids if soup.find(id=item) is None]
    assert len(soup.select(".kpi-card")) == 8
    assert len(soup.select("[data-infrastructure]")) == 3


def test_dashboard_has_no_login_or_chip_selector() -> None:
    combined = f"{BASE.read_text(encoding='utf-8')}\n{TEMPLATE.read_text(encoding='utf-8')}".lower()
    assert "type=\"password\"" not in combined
    assert "name=\"chip_selector\"" not in combined
    assert "chip selection" not in combined
    assert "terminal controlled" in combined
    assert "read-only" in combined


def test_dashboard_javascript_uses_only_get_fetches() -> None:
    javascript = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "app" / "dashboard" / "static" / "js").glob("*.js")
    )
    assert 'method: "GET"' in javascript
    assert 'method: "POST"' not in javascript
    assert 'method: "PUT"' not in javascript
    assert 'method: "DELETE"' not in javascript

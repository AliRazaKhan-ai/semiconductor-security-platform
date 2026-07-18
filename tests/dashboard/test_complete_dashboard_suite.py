"""Purpose: Validate the read-only Flask dashboard.
Directory: tests/dashboard.
Dependencies: Flask client, HTML dashboard templates and static files.
Connection: Ensures pipeline results can be viewed but scans cannot be
initiated from the dashboard.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from flask.testing import FlaskClient


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("path", ("/", "/dashboard"))
def test_dashboard_routes_render_html(
    client: FlaskClient,
    path: str,
) -> None:
    response = client.get(path)

    assert response.status_code == 200
    assert response.content_type.startswith("text/html")
    assert len(response.data) > 500


def test_dashboard_has_application_identity(client: FlaskClient) -> None:
    response = client.get("/dashboard")
    text = response.get_data(as_text=True).lower()

    assert "semisecure" in text
    assert "dashboard" in text


def test_dashboard_html_is_structurally_valid(client: FlaskClient) -> None:
    response = client.get("/dashboard")
    soup = BeautifulSoup(response.get_data(as_text=True), "html.parser")

    assert soup.html is not None
    assert soup.head is not None
    assert soup.body is not None
    assert soup.title is not None


def test_dashboard_loads_javascript(client: FlaskClient) -> None:
    response = client.get("/dashboard")
    soup = BeautifulSoup(response.get_data(as_text=True), "html.parser")

    scripts = [
        tag.get("src")
        for tag in soup.find_all("script")
        if tag.get("src")
    ]

    assert scripts


def test_dashboard_is_read_only(client: FlaskClient) -> None:
    response = client.get("/dashboard")
    soup = BeautifulSoup(response.get_data(as_text=True), "html.parser")

    forms = soup.find_all("form")

    for form in forms:
        action = str(form.get("action") or "").lower()
        method = str(form.get("method") or "get").lower()

        assert not (
            method == "post"
            and any(
                token in action
                for token in (
                    "/scan",
                    "/integration/run",
                    "/compliance/evaluate",
                )
            )
        )


def test_dashboard_has_no_chip_selection_dropdown(
    client: FlaskClient,
) -> None:
    response = client.get("/dashboard")
    soup = BeautifulSoup(response.get_data(as_text=True), "html.parser")

    for select in soup.find_all("select"):
        combined = " ".join(
            (
                str(select.get("id") or ""),
                str(select.get("name") or ""),
                " ".join(select.get("class") or []),
            )
        ).lower()

        assert "chip" not in combined
        assert "scan" not in combined




def test_dashboard_referenced_assets_are_available(
    client: FlaskClient,
) -> None:
    """Ensure locally referenced dashboard assets can be retrieved."""
    response = client.get("/dashboard")

    assert response.status_code == 200

    soup = BeautifulSoup(
        response.get_data(as_text=True),
        "html.parser",
    )

    references: list[str] = []

    for script in soup.find_all("script"):
        source = script.get("src")

        if source:
            references.append(str(source))

    for link in soup.find_all("link"):
        href = link.get("href")

        if href:
            references.append(str(href))

    assert references, "Dashboard contains no script or stylesheet references"

    local_references = [
        reference
        for reference in references
        if (
            reference.startswith("/")
            and not reference.startswith("//")
        )
    ]

    for reference in local_references:
        asset_response = client.get(reference)

        assert asset_response.status_code == 200, (
            f"Dashboard asset could not be loaded: {reference}"
        )


def test_dashboard_contains_css_or_inline_styles(
    client: FlaskClient,
) -> None:
    """Confirm the dashboard includes visible styling."""
    response = client.get("/dashboard")
    soup = BeautifulSoup(
        response.get_data(as_text=True),
        "html.parser",
    )

    stylesheets = [
        link
        for link in soup.find_all("link")
        if "stylesheet" in [
            str(value).lower()
            for value in (
                link.get("rel")
                or []
            )
        ]
    ]

    inline_styles = soup.find_all("style")

    assert stylesheets or inline_styles

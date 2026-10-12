"""Edge cases found by probing the running API (2026-10-12), each a regression test."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from finintel.api import app as api_app
from finintel.parse.cached import cached_text_layer
from tests.api.conftest import EXCERPT, ROOT, upload

pytestmark = pytest.mark.network

ROOT_FIXTURE = ROOT / "tests" / "e2e" / "fixtures" / "pdfs" / "missing_unit.pdf"


def code(r: Any) -> str:
    return str(r.json()["detail"]["code"])


@pytest.mark.parametrize("name", ["..", ".", "/", "a/..", "../.."])
def test_an_upload_whose_name_has_no_base_name_is_stored_not_a_500(
    client: TestClient, name: str
) -> None:
    body = upload(client, EXCERPT, name=name)  # was a 500: the PDF was written onto a directory
    assert body["status"] == "ready"
    assert client.get(f"/reports/{body['id']}").json()["filename"] == "upload.pdf"


def test_a_very_long_upload_name_is_shortened_not_a_500(client: TestClient) -> None:
    body = upload(client, EXCERPT, name="é" * 300 + ".pdf")  # 600 bytes: was a 500 (name too long)
    stored = client.get(f"/reports/{body['id']}").json()["filename"]
    assert stored.endswith(".pdf") and len(stored.encode()) <= 200 and stored.startswith("é")


def test_a_damaged_pdf_is_refused_without_a_server_path(client: TestClient, tmp_path: Path) -> None:
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"%PDF-1.4 not really a pdf")
    with bad.open("rb") as f:
        r = client.post("/uploads", files={"file": ("bad.pdf", f, "application/pdf")})
    assert r.status_code == 422 and code(r) == "unreadable_pdf"
    message = r.json()["detail"]["message"]
    assert "bad.pdf" in message
    assert "/" not in message and str(tmp_path) not in message  # was: MuPDF's text with a temp path


def test_commentary_stored_in_an_older_format_is_not_served_as_current(
    client: TestClient, db: psycopg.Connection
) -> None:
    rid = upload(client)["id"]
    output = client.get(f"/reports/{rid}/commentary").json()["output"]
    for topic in output["topics"]:
        for paragraph in topic["paragraphs"]:
            paragraph.pop("figures", None)  # the shape written before ADR-012
    db.execute(
        "UPDATE commentaries SET output = %s WHERE document_id = %s", (json.dumps(output), rid)
    )
    r = client.get(f"/reports/{rid}/commentary")
    assert r.status_code == 404 and code(r) == "commentary_outdated"  # was 200: the UI crashed


def test_a_page_outside_the_document_is_refused_without_reading_the_text_layer(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    rid = upload(client)["id"]
    calls: list[str] = []
    real = cached_text_layer

    def counting(*args: Any, **kwargs: Any) -> Any:
        calls.append("read")
        return real(*args, **kwargs)

    monkeypatch.setattr(api_app, "cached_text_layer", counting)
    for n in (0, -1, 306, 9999):
        r = client.get(f"/reports/{rid}/pages/{n}")
        assert r.status_code == 404 and code(r) == "page_not_found"
    assert calls == []  # the page count is on the document row
    assert client.get(f"/reports/{rid}/pages/141").status_code == 200
    assert client.get(f"/reports/{rid}/pages/143").status_code == 200
    assert len(calls) <= 1  # one read per report, then from memory


def _override(client: TestClient, rid: object, tail: str) -> Any:
    body = (
        '{"action":"set_value","item":"revenue","period_id":"FY2024","raw_text":"60,761",'
        '"force":true,"reason":"probe",' + tail
    )
    return client.post(
        f"/reports/{rid}/overrides", content=body, headers={"content-type": "application/json"}
    )


@pytest.mark.parametrize(
    "tail", ['"value":NaN,"page":141}', '"value":Infinity,"page":141}', '"value":1e400,"page":141}']
)
def test_a_non_finite_override_value_is_a_422_not_a_500(
    client: TestClient, db: psycopg.Connection, tail: str
) -> None:
    rid = upload(client)["id"]
    r = _override(client, rid, tail)  # was a 500: Postgres rejects NaN, then the 422 echo did too
    assert r.status_code == 422 and r.json()["detail"][0]["type"] == "finite_number"
    assert db.execute("SELECT count(*) FROM overrides").fetchone() == (0,)


@pytest.mark.parametrize("page", [0, -5, 306, 99999])
def test_an_override_on_a_page_outside_the_document_is_refused(
    client: TestClient, db: psycopg.Connection, page: int
) -> None:
    rid = upload(client)["id"]
    r = _override(client, rid, f'"value":60761,"page":{page}}}')  # 0/-5 were 500s; 99999 was stored
    assert r.status_code == 422 and code(r) == "page_out_of_range"
    assert db.execute("SELECT count(*) FROM overrides").fetchone() == (0,)
    assert db.execute("SELECT count(*) FROM statement_packs").fetchone() == (1,)


def test_the_report_list_is_newest_first_with_status_and_no_figures(client: TestClient) -> None:
    assert client.get("/reports").json() == []
    first = upload(client)["id"]
    rows = client.get("/reports").json()
    assert [r["id"] for r in rows] == [first]
    row = rows[0]
    assert row["filename"] == EXCERPT.name and row["status"] == "ready"
    assert row["page_count"] == 305 and row["period_label"] == "2024"  # the label as printed
    assert row["currency"] == "EUR" and row["unit_scale"] == 1_000_000
    assert row["open_review_items"] >= 0 and row["stale"] is False
    assert not ({"pack", "ratios", "value"} & set(row))  # a list never carries figures
    second = upload(client, ROOT_FIXTURE, name="missing_unit.pdf")["id"]
    assert [r["id"] for r in client.get("/reports").json()] == [second, first]

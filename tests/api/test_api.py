"""M6.2 gate: every endpoint, plus the override, unit, location and document-type behaviours."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from evals.synthetic.render import render
from evals.synthetic.spec import load_spec
from finintel.api import create_app
from tests.api.conftest import EXCERPT, ROOT, encrypted_pdf, upload

pytestmark = pytest.mark.network


def code(response: Any) -> str:
    return str(response.json()["detail"]["code"])


def ready_report(client: TestClient) -> int:
    body = upload(client)
    report = client.get(f"/reports/{body['id']}").json()
    assert report["status"] == "ready", report["jobs"]
    return int(str(body["id"]))


def test_upload_report_commentary_pages_review_and_health(client: TestClient) -> None:
    body = upload(client)
    assert (
        body["status"] == "ready" and body["duplicate"] is False and len(str(body["sha256"])) == 64
    )
    rid = body["id"]
    report = client.get(f"/reports/{rid}").json()
    assert (
        report["document_type"] == "corporate" and report["page_count"] == 305
    )  # the excerpt keeps original page numbers
    assert report["pack_version"] == 1 and report["pack"]["items"]["revenue"]
    assert report["ratios"]["periods"][0]["ratios"]["operating_margin"]["value"] is not None
    assert [j["status"] for j in report["jobs"]] == ["done"] * 6
    assert report["stale"] is False and report["reduced_verification"] is True  # one engine family

    commentary = client.get(f"/reports/{rid}/commentary").json()
    assert commentary["output"]["mode"] == "extractive" and commentary["stale"] is False

    page = client.get(f"/reports/{rid}/pages/141").json()
    assert page["page"] == 141 and "60,761" in page["text"] and page["words"][0]["bbox"]
    assert client.get(f"/reports/{rid}/pages/9999").status_code == 404
    pdf = client.get(f"/reports/{rid}/original")
    assert pdf.status_code == 200 and pdf.content[:5] == b"%PDF-"

    review = client.get(f"/reports/{rid}/review").json()
    assert review["status"] == "ready" and isinstance(review["warnings"], list)
    assert (
        client.get("/reports/999").status_code == 404
        and code(client.get("/reports/999")) == "report_not_found"
    )
    assert client.get("/healthz").json() == {"status": "ok", "checks": {}}
    ready = client.get("/readyz").json()
    assert (
        ready["status"] == "ok"
        and ready["checks"]["database"] == "ok"
        and ready["checks"]["llm"] == "extractive"
    )


def test_a_duplicate_upload_returns_the_same_report(
    client: TestClient, db: psycopg.Connection
) -> None:
    first = upload(client)
    second = upload(client, name="renamed.pdf")
    assert second["id"] == first["id"] and second["duplicate"] is True
    assert db.execute("SELECT count(*) FROM documents").fetchone() == (1,)
    assert db.execute("SELECT count(*) FROM jobs").fetchone() == (6,)  # nothing was enqueued twice


def test_uploads_are_refused_with_the_statuses_the_spec_names(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    junk = client.post(
        "/uploads", files={"file": ("x.pdf", b"not a pdf at all", "application/pdf")}
    )
    assert junk.status_code == 415 and code(junk) == "not_a_pdf"

    locked = encrypted_pdf(tmp_path / "locked.pdf")
    with locked.open("rb") as f:
        enc = client.post("/uploads", files={"file": ("locked.pdf", f, "application/pdf")})
    assert enc.status_code == 422 and code(enc) == "encrypted_pdf"

    import finintel.api.app as app_module

    monkeypatch.setattr(app_module, "MAX_UPLOAD_BYTES", 100)
    with EXCERPT.open("rb") as f:
        big = client.post("/uploads", files={"file": ("big.pdf", f, "application/pdf")})
    assert big.status_code == 413 and code(big) == "file_too_large"


def override(client: TestClient, rid: int, **body: Any) -> Any:
    base = {"action": "set_value", "item": "revenue", "period_id": "FY2024"}
    return client.post(f"/reports/{rid}/overrides", json={**base, **body})


def test_an_anchored_override_recomputes_ratios_and_marks_commentary_stale(
    client: TestClient, db: psycopg.Connection
) -> None:
    rid = ready_report(client)
    before = client.get(f"/reports/{rid}").json()
    op_profit = before["pack"]["items"]["operating_profit"]["values"][0]["value"]
    r = override(
        client, rid, value=6369.0, raw_text="6,369", page=141, reason="net profit row used"
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert (
        body["anchored"] is True
        and body["pack_version"] == 2
        and body["ratios_recomputed"]
        and body["stale"]
    )
    assert body["warning_codes"] == ["human_override"]

    after = client.get(f"/reports/{rid}").json()
    assert (
        after["pack_version"] == 2
        and after["pack_sha"] != before["pack_sha"]
        and after["stale"] is True
    )
    value = after["pack"]["items"]["revenue"]["values"][0]
    assert (value["value"], value["engine"], value["confidence"], value["page"]) == (
        6369.0,
        "human_override",
        1.0,
        141,
    )
    margin = after["ratios"]["periods"][0]["ratios"]["operating_margin"]["value"]
    assert margin == pytest.approx(op_profit / 6369.0, rel=1e-9)  # recomputed from the new pack
    assert db.execute("SELECT stale FROM commentaries").fetchone() == (True,)

    trail = client.get(f"/reports/{rid}/overrides").json()
    assert [t["action"] for t in trail] == ["set_value"] and trail[0]["payload"]["before"][
        "value"
    ] == 60761.0


def test_an_unanchored_set_value_is_422_and_forced_it_is_recorded_unanchored(
    client: TestClient,
) -> None:
    rid = ready_report(client)
    bad = override(client, rid, value=12345.0, raw_text="12,345", page=141)
    assert bad.status_code == 422 and code(bad) == "unanchored_override"
    no_reason = override(client, rid, value=12345.0, raw_text="12,345", page=141, force=True)
    assert no_reason.status_code == 422 and code(no_reason) == "reason_required"
    forced = override(
        client,
        rid,
        value=12345.0,
        raw_text="12,345",
        page=141,
        force=True,
        reason="read from a scan",
    )
    assert forced.status_code == 200 and forced.json()["anchored"] is False
    assert forced.json()["warning_codes"] == ["human_override_unanchored"]
    pack = client.get(f"/reports/{rid}").json()["pack"]
    assert pack["items"]["revenue"]["values"][0]["engine"] == "human_override_unanchored"
    assert any(w["code"] == "human_override_unanchored" for w in pack["warnings"])
    assert client.get(f"/reports/{rid}/overrides").json()[0]["anchored"] is False


def test_refused_overrides_change_nothing(client: TestClient, db: psycopg.Connection) -> None:
    rid = ready_report(client)
    cases: list[tuple[dict[str, Any], str]] = [
        (dict(value=1.0, raw_text="60,761", page=141), "value_does_not_match_raw_text"),
        (dict(value=1.0, raw_text="n/a", page=141), "raw_text_not_a_number"),
        (dict(raw_text="60,761", page=141), "missing_field"),
        (dict(action="set_null"), "reason_required"),
        (dict(item="nonsense", value=60761.0, raw_text="60,761", page=141), "unknown_item"),
        (dict(period_id="FY1999", value=60761.0, raw_text="60,761", page=141), "unknown_period"),
    ]
    for body, expected in cases:
        r = override(client, rid, **body)
        assert r.status_code == 422 and code(r) == expected, (body, r.text)
    assert db.execute("SELECT count(*) FROM overrides").fetchone() == (0,)
    assert db.execute("SELECT count(*) FROM statement_packs").fetchone() == (1,)
    nulled = override(client, rid, action="set_null", reason="figure is not reliable")
    assert nulled.status_code == 200
    value = client.get(f"/reports/{rid}").json()["pack"]["items"]["revenue"]["values"][0]
    assert value["value"] is None and value["engine"] == "human_override"


def test_a_review_candidate_with_a_printed_value_can_be_accepted(
    client: TestClient, db: psycopg.Connection
) -> None:
    rid = ready_report(client)
    row = db.execute(
        "INSERT INTO review_items (document_id, item, period_id, kind, candidates) "
        "VALUES (%s, 'revenue', 'FY2024', 'disagreement', %s::jsonb) RETURNING id",
        (
            rid,
            json.dumps(
                [
                    {"engine": "x", "value": 6369.0, "raw_text": "6,369", "page": 141},
                    {"engine": "llm"},
                ]
            ),
        ),
    ).fetchone()
    assert row is not None
    ok = override(client, rid, action="accept_candidate", candidate_id=f"{row[0]}:0")
    assert ok.status_code == 200 and ok.json()["anchored"] is True
    pointer = override(client, rid, action="accept_candidate", candidate_id=f"{row[0]}:1")
    assert pointer.status_code == 422 and code(pointer) == "candidate_without_value"
    assert (
        code(override(client, rid, action="accept_candidate", candidate_id="999:0"))
        == "candidate_not_found"
    )
    assert len(client.get(f"/reports/{rid}/review").json()["items"]) == 1


def test_a_unit_ambiguous_report_stays_blocked_until_the_unit_is_confirmed(
    client: TestClient, tmp_path: Path
) -> None:
    pdf = render(
        load_spec(ROOT / "evals" / "synthetic" / "specs" / "missing_unit.yaml"),
        tmp_path / "missing_unit.pdf",
    )
    rid = upload(client, pdf)["id"]
    blocked = client.get(f"/reports/{rid}").json()
    assert blocked["status"] == "needs_unit_confirmation" and blocked["pack"] is None
    assert [j["status"] for j in blocked["jobs"]][:3] == ["done"] * 3 and blocked["jobs"][3][
        "status"
    ] == "queued"
    again = client.get(f"/reports/{rid}").json()  # nothing moves on its own
    assert again["status"] == "needs_unit_confirmation"

    far = client.post(
        f"/reports/{rid}/unit-confirmation",
        json={"currency": "GBP", "unit_scale": 1000, "evidence_page": 99},
    )
    assert far.status_code == 422 and code(far) == "page_out_of_range"
    ok = client.post(
        f"/reports/{rid}/unit-confirmation",
        json={"currency": "GBP", "unit_scale": 1000, "evidence_page": 2},
    )
    assert ok.status_code == 200 and ok.json()["status"] == "ready"
    done = client.get(f"/reports/{rid}").json()
    assert (done["pack"]["currency"], done["pack"]["unit_scale"]) == ("GBP", 1000)
    assert "unit_confirmed_manually" in {w["code"] for w in done["warnings"]}
    assert "unit_ambiguous" not in {w["code"] for w in done["warnings"]}
    not_blocked = client.post(
        f"/reports/{rid}/unit-confirmation",
        json={"currency": "GBP", "unit_scale": 1000, "evidence_page": 2},
    )
    assert not_blocked.status_code == 409 and code(not_blocked) == "not_blocked"


def test_statement_location_reruns_extraction_constrained_to_the_page(
    client: TestClient, executed: Counter[str]
) -> None:
    rid = ready_report(client)
    executed.clear()
    r = client.post(
        f"/reports/{rid}/statement-location",
        json={"statement_type": "income_statement", "page": 141},
    )
    assert r.status_code == 200 and r.json()["reran"] == [
        "extract",
        "ratios",
        "index",
        "commentary",
    ]
    assert executed == Counter(
        {"extract": 1, "ratios": 1, "index": 1, "commentary": 1}
    )  # ingest and text layer not
    report = client.get(f"/reports/{rid}").json()
    assert report["status"] == "ready" and report["pack_version"] == 2
    assert client.get(f"/reports/{rid}/overrides").json()[0]["action"] == "statement_location"
    far = client.post(
        f"/reports/{rid}/statement-location",
        json={"statement_type": "income_statement", "page": 500},
    )
    assert far.status_code == 422 and code(far) == "page_out_of_range"
    bad = client.post(
        f"/reports/{rid}/statement-location", json={"statement_type": "poem", "page": 1}
    )
    assert bad.status_code == 422


def test_document_type_reapplies_the_applicability_matrix_and_reruns_ratios_and_commentary(
    client: TestClient, executed: Counter[str]
) -> None:
    rid = ready_report(client)
    executed.clear()
    r = client.post(
        f"/reports/{rid}/document-type", json={"document_type": "bank", "reason": "UK bank"}
    )
    assert r.status_code == 200 and r.json()["reran"] == ["ratios", "commentary"]
    assert executed == Counter({"ratios": 1, "commentary": 1})
    report = client.get(f"/reports/{rid}").json()
    assert report["document_type"] == "bank" and report["pack"]["document_type"] == "bank"
    for ratio in report["ratios"]["periods"][0]["ratios"].values():
        assert ratio["applicability"] == "not_applicable"
    assert client.get(f"/reports/{rid}/overrides").json()[0]["action"] == "document_type"
    assert (
        client.post(f"/reports/{rid}/document-type", json={"document_type": "bank"}).status_code
        == 422
    )


def test_a_re_extraction_keeps_a_persons_value_override(client: TestClient) -> None:
    rid = ready_report(client)
    assert override(client, rid, value=6369.0, raw_text="6,369", page=141).status_code == 200
    client.post(
        f"/reports/{rid}/statement-location",
        json={"statement_type": "income_statement", "page": 141},
    )
    value = client.get(f"/reports/{rid}").json()["pack"]["items"]["revenue"]["values"][0]
    assert value["value"] == 6369.0 and value["engine"] == "human_override"


def test_the_openapi_document_names_every_endpoint() -> None:
    paths = create_app().openapi()["paths"]
    for path in ("/uploads", "/reports/{report_id}", "/reports/{report_id}/commentary", "/reports/{report_id}/pages/{n}",
                 "/reports/{report_id}/review", "/reports/{report_id}/overrides", "/reports/{report_id}/unit-confirmation",
                 "/reports/{report_id}/statement-location", "/reports/{report_id}/document-type"):  # fmt: skip
        assert path in paths

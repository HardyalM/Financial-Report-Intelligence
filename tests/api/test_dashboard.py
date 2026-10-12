"""GET /dashboard and the sample reports, over the real app and worker (Postgres)."""

from __future__ import annotations

import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import upload

pytestmark = pytest.mark.network


def test_the_dashboard_card_carries_the_engines_ratios_and_the_figure_counts(
    client: TestClient,
) -> None:
    assert client.get("/dashboard").json() == {"reports": [], "has_samples": False}
    rid = upload(client)["id"]
    [card] = client.get("/dashboard").json()["reports"]
    report = client.get(f"/reports/{rid}").json()
    assert card["id"] == rid and card["status"] == "ready" and card["is_sample"] is False
    assert card["document_type"] == "corporate"  # the pack's type, not the unset row's "other"
    assert card["period_label"] == "2024" and card["prior_label"] == "2023"
    counts = card["figures"]
    current = report["pack"]["periods"][0]["id"]
    settled = [
        v
        for i in report["pack"]["items"].values()
        for v in i["values"]
        if v["period_id"] == current
    ]
    assert sum(counts.values()) == len(settled)
    assert counts["empty"] == sum(v["value"] is None for v in settled)
    engine = report["ratios"]["periods"][0]["ratios"]
    for r in card["ratios"]:
        assert r["value"] == engine[r["name"]]["value"]  # exactly the engine's, nothing recomputed
    assert [r["name"] for r in card["ratios"]][:2] == ["operating_margin", "roce"]
    # the excerpt holds statement pages only: nothing to quote, so no citations, honestly
    assert card["commentary"]["mode"] == "extractive" and card["commentary"]["topics"] > 0
    assert card["waiting_for"] in (None, "review")


def test_samples_run_through_the_pipeline_marked_and_removed_as_a_set(
    client: TestClient, db: psycopg.Connection
) -> None:
    own = upload(client)["id"]  # a person's own upload of the same PDF as a sample
    seeded = client.post("/samples")
    assert seeded.status_code == 202
    body = seeded.json()
    assert own in body["skipped"] and own not in body["added"] and len(body["added"]) == 4
    cards = {c["id"]: c for c in client.get("/dashboard").json()["reports"]}
    assert cards[own]["is_sample"] is False  # never marked
    samples = [cards[i] for i in body["added"]]
    assert all(c["is_sample"] for c in samples)
    waits = {c["waiting_for"] for c in samples}
    assert {"unit", "document_type"} <= waits  # the blocked states are exercised
    bank = next(c for c in samples if c["document_type"] == "bank")
    assert bank["ratios"][0]["name"] in ("cost_to_income", "loan_to_deposit")
    assert all(c["commentary"] is None or c["commentary"]["mode"] == "extractive" for c in samples)
    listed = {r["id"]: r for r in client.get("/reports").json()}
    assert all(listed[i]["is_sample"] for i in body["added"]) and listed[own]["is_sample"] is False
    removed = client.delete("/samples").json()["removed"]
    assert sorted(removed) == sorted(body["added"])
    assert [c["id"] for c in client.get("/dashboard").json()["reports"]] == [own]
    assert db.execute(
        "SELECT count(*) FROM jobs WHERE document_id = ANY(%s)", (removed,)
    ).fetchone() == (0,)

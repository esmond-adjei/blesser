from fastapi.testclient import TestClient

from api.main import app


def _start(client, **body):
    res = client.post(
        "/api/app/scans",
        json={
            "categories": ["startup"],
            "region": "Ghana",
            "focus": "edtech grants",
            **body,
        },
    )
    assert res.status_code == 200, res.text
    return res.json()["id"]


def _stop(client, *ids):
    for scan_id in ids:
        client.post(f"/api/app/scans/{scan_id}/cancel")


def test_rerun_copies_the_brief_and_applies_changes():
    client = TestClient(app)
    first = _start(client)
    _stop(client, first)
    same = client.post(f"/api/app/scans/{first}/rerun", json={})
    assert same.status_code == 201, same.text
    assert same.json()["id"] != first
    assert (same.json()["region"], same.json()["focus"]) == ("Ghana", "edtech grants")
    changed = client.post(
        f"/api/app/scans/{first}/rerun",
        json={"focus": "health grants", "region": "Kenya"},
    )
    assert (changed.json()["region"], changed.json()["focus"]) == (
        "Kenya",
        "health grants",
    )
    cleared = client.post(f"/api/app/scans/{first}/rerun", json={"focus": ""})
    assert cleared.json()["focus"] == ""
    _stop(client, same.json()["id"], changed.json()["id"], cleared.json()["id"])


def test_rerun_rejects_unknown_fields_and_other_members_scans():
    client = TestClient(app)
    first = _start(client)
    _stop(client, first)
    assert (
        client.post(f"/api/app/scans/{first}/rerun", json={"repeat": True}).status_code
        == 422
    )
    assert client.post("/api/app/scans/nope/rerun", json={}).status_code == 404


def test_steer_waits_for_a_running_scan_then_queues_a_followup():
    client = TestClient(app)
    scan_id = _start(client)
    busy = client.post(f"/api/app/scans/{scan_id}/steer", json={"prompt": "Only Ghana"})
    assert busy.status_code == 409
    _stop(client, scan_id)
    steered = client.post(
        f"/api/app/scans/{scan_id}/steer", json={"prompt": "  Only Ghana  "}
    )
    assert steered.status_code == 200, steered.text
    body = steered.json()
    assert body["status"] == "running"
    assert [t["metrics"].get("steer") for t in body["tasks"]].count("Only Ghana") == 1
    assert all(
        t["metrics"].get("pipeline_complete")
        for t in body["tasks"]
        if t["metrics"].get("steer")
    )
    _stop(client, scan_id)


def test_steer_needs_a_prompt():
    client = TestClient(app)
    scan_id = _start(client)
    _stop(client, scan_id)
    assert (
        client.post(
            f"/api/app/scans/{scan_id}/steer", json={"prompt": "  "}
        ).status_code
        == 422
    )


def test_timing_follows_the_latest_run_after_a_steer():
    from datetime import datetime, timedelta
    from types import SimpleNamespace

    from api.scans.service import _timing

    t0 = datetime(2026, 11, 20, 10, 0, 0)
    first = SimpleNamespace(
        created_at=t0, started_at=t0, finished_at=t0 + timedelta(minutes=5)
    )
    later = t0 + timedelta(days=1)
    second = SimpleNamespace(created_at=later, started_at=later, finished_at=None)
    scan = SimpleNamespace(status="running")
    assert _timing(scan, [first, second]) == {"started_at": later, "finished_at": None}
    second.finished_at = later + timedelta(minutes=2)
    scan.status = "done"
    assert _timing(scan, [first, second]) == {
        "started_at": later,
        "finished_at": later + timedelta(minutes=2),
    }


def test_scan_keeps_its_listing_types_and_names_them():
    from api.scans.service import kinds_phrase, scan_kinds

    client = TestClient(app)
    first = _start(client, categories=["student"], kinds=["scholarship", "job"])
    _stop(client, first)
    again = client.post(f"/api/app/scans/{first}/rerun", json={}).json()
    assert again["kinds"] == ["scholarship", "job"]
    changed = client.post(f"/api/app/scans/{first}/rerun", json={"kinds": []}).json()
    assert changed["kinds"] == []
    _stop(client, again["id"], changed["id"])
    assert (
        client.post(
            "/api/app/scans", json={"categories": ["student"], "kinds": ["x"]}
        ).status_code
        == 422
    )

    assert scan_kinds([], "job applications in software engineering") == ["job"]
    assert (
        kinds_phrase(["scholarship", "job", "grant"]) == "scholarships, jobs and grants"
    )


def test_agent_brief_names_the_listing_types():
    from api.opportunities.tasks import user_message

    text = user_message(
        region="Ghana",
        category="student",
        focus="",
        today="2026-11-21",
        known=[],
        kinds=["internship"],
    )
    assert "Listing types the member wants: internship." in text


def test_crawler_skips_links_that_name_only_other_countries():
    from api.opportunities.triage import names_other_country

    nigerian = "https://example.org/trainee-programme-for-young-nigerian-graduates"
    assert names_other_country(nigerian, "Ghana")
    assert not names_other_country(nigerian, "Nigeria")
    assert not names_other_country(
        "https://example.org/ghana-and-nigeria-fund", "Ghana"
    )
    assert not names_other_country(nigerian, "Ghana / West Africa / pan-Africa")
    assert not names_other_country("https://example.org/bursary-2027", "Ghana")
    east = "https://example.org/east-and-southern-africa-incubator"
    assert names_other_country(east, "Ghana")
    assert not names_other_country(east, "Kenya")
    assert names_other_country("https://example.org/sadc-essay-competition", "Ghana")


def test_a_steered_run_hears_what_earlier_runs_tried():
    import json
    from types import SimpleNamespace

    from api.opportunities.tasks import _focus
    from api.scans.service import _tried

    log = json.dumps(
        [
            {"tool": "search_web", "input": {"query": "AI jobs Accra"}},
            {"tool": "fetch_page", "input": {"url": "https://zof.ai/careers"}},
            {"tool": "search_web", "input": {"query": "AI jobs Accra"}},
        ]
    )
    tried = _tried([SimpleNamespace(created_at=1, log=log)])
    assert tried == {"searches": ["AI jobs Accra"], "pages": ["https://zof.ai/careers"]}
    task = SimpleNamespace(metrics={"steer": "go deeper", "tried": tried})
    text = _focus(SimpleNamespace(focus="AI jobs"), task)
    assert "go deeper" in text and "- searched: AI jobs Accra" in text
    assert "- read: https://zof.ai/careers" in text

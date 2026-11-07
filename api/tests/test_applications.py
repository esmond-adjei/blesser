from fastapi.testclient import TestClient

from api.main import app


def test_tracker_crud_and_checklist():
    client = TestClient(app)
    created = client.post(
        "/api/applications",
        json={
            "title": "Hand-added Fellowship",
            "organization": "Example Trust",
            "kind": "Fellowship",
            "deadline": "15 March 2027",
            "requirements": [{"label": "CV"}, {"label": "Proposal"}],
        },
    )
    assert created.status_code == 200, created.text
    app_row = created.json()
    assert app_row["status"] == "saved"
    assert app_row["deadline_date"] == "2027-03-15"
    assert [r["done"] for r in app_row["requirements"]] == [False, False]

    patched = client.patch(
        f"/api/applications/{app_row['id']}",
        json={"status": "submitted", "requirements": [{"label": "CV", "done": True}]},
    ).json()
    assert patched["status"] == "submitted"
    assert patched["requirements"] == [{"label": "CV", "done": True}]
    assert client.patch(f"/api/applications/{app_row['id']}", json={"status": "nope"}).status_code == 422

    listed = [a["id"] for a in client.get("/api/applications").json()]
    assert app_row["id"] in listed
    assert client.delete(f"/api/applications/{app_row['id']}").status_code == 200
    assert client.get(f"/api/applications/{app_row['id']}").status_code == 404

from pathlib import Path

from atlas import db


def column(project: dict, name: str) -> dict:
    return next(c for c in project["columns"] if c["name"] == name)


def test_archive_hides_from_board(client):
    p = client.post("/api/projects", json={"name": "old thing"}).json()
    client.patch(f"/api/projects/{p['id']}/archive", json={"archived": True})

    assert client.get("/api/board").json()["projects"] == []
    everything = client.get("/api/board", params={"include_archived": True}).json()
    assert everything["projects"][0]["archived"] == 1

    client.patch(f"/api/projects/{p['id']}/archive", json={"archived": False})
    assert len(client.get("/api/board").json()["projects"]) == 1


def test_now_view_shows_active_in_progress(client):
    active = client.post("/api/projects", json={"name": "hot", "status": "active"}).json()
    client.post("/api/projects", json={"name": "cold", "status": "idea"})
    client.post(f"/api/columns/{column(active, 'Todo')['id']}/tasks", json={"title": "next"})
    done_task = client.post(
        f"/api/columns/{column(active, 'Todo')['id']}/tasks", json={"title": "finished"}
    ).json()
    client.patch(
        f"/api/tasks/{done_task['id']}/move",
        json={"column_id": column(active, "Done")["id"], "index": 0},
    )

    now = client.get("/api/now").json()
    assert [p["name"] for p in now] == ["hot"]
    assert [t["title"] for t in now[0]["tasks"]] == ["next"]  # done-column task excluded


def test_now_excludes_archived_active(client):
    p = client.post("/api/projects", json={"name": "shelved", "status": "active"}).json()
    client.patch(f"/api/projects/{p['id']}/archive", json={"archived": True})
    assert client.get("/api/now").json() == []


def test_backup_creates_and_prunes(tmp_path):
    db.create_project("something")
    for i in range(3):
        db.backup(Path(tmp_path), f"2026072{i}", keep=2)
    files = sorted(f.name for f in Path(tmp_path).glob("atlas-*.sqlite"))
    assert files == ["atlas-20260721.sqlite", "atlas-20260722.sqlite"]

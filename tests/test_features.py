from pathlib import Path

from atlas import db, sync
from tests.conftest import add_repo


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


def test_archive_with_github_writeback(client, monkeypatch):
    calls = []
    monkeypatch.setattr(sync, "set_repo_archived", lambda fn, a: calls.append((fn, a)))
    add_repo("fisherrjd/old1")
    add_repo("fisherrjd/old2")
    p = client.post(
        "/api/projects", json={"name": "grp", "repos": ["fisherrjd/old1", "fisherrjd/old2"]}
    ).json()
    r = client.patch(
        f"/api/projects/{p['id']}/archive", json={"archived": True, "github": True}
    )
    assert r.status_code == 200 and r.json()["archived"] == 1
    assert sorted(calls) == [("fisherrjd/old1", True), ("fisherrjd/old2", True)]
    assert all(x["archived"] == 1 for x in client.get("/api/repos").json())


def test_archive_github_failure_leaves_project_unarchived(client, monkeypatch):
    def boom(fn, a):
        raise sync.SyncError("gh archive failed", 502)

    monkeypatch.setattr(sync, "set_repo_archived", boom)
    add_repo("fisherrjd/x")
    p = client.post("/api/projects", json={"name": "solo", "repos": ["fisherrjd/x"]}).json()
    r = client.patch(f"/api/projects/{p['id']}/archive", json={"archived": True, "github": True})
    assert r.status_code == 502
    assert client.get(f"/api/projects/{p['id']}").json()["archived"] == 0


def test_backup_creates_and_prunes(tmp_path):
    db.create_project("something")
    for i in range(3):
        db.backup(Path(tmp_path), f"2026072{i}", keep=2)
    files = sorted(f.name for f in Path(tmp_path).glob("atlas-*.sqlite"))
    assert files == ["atlas-20260721.sqlite", "atlas-20260722.sqlite"]

from atlas import db, sync
from tests.conftest import add_repo


def gh_repo(full_name: str, pushed_at: str = "2026-07-01T00:00:00Z", **overrides) -> dict:
    owner, name = full_name.split("/")
    return {
        "name": name,
        "owner": {"login": owner},
        "description": overrides.get("description", f"{name} repo"),
        "pushedAt": pushed_at,
        "primaryLanguage": overrides.get("primaryLanguage", {"name": "Python"}),
        "isArchived": overrides.get("isArchived", False),
        "url": f"https://github.com/{full_name}",
    }


def test_project_task_flow(client):
    p = client.post("/api/projects", json={"name": "atlas"}).json()
    assert p["status"] == "idea"

    moved = client.patch(f"/api/projects/{p['id']}/move", json={"status": "active", "index": 0})
    assert moved.json()["status"] == "active"

    t = client.post(f"/api/projects/{p['id']}/tasks", json={"title": "build it"}).json()
    assert t["status"] == "todo"
    client.patch(f"/api/tasks/{t['id']}/move", json={"status": "doing", "index": 0})

    client.patch(f"/api/projects/{p['id']}", json={"notes": "remember the husk rule"})

    full = client.get(f"/api/projects/{p['id']}").json()
    assert full["notes"] == "remember the husk rule"
    assert full["tasks"][0]["status"] == "doing"

    board = client.get("/api/board").json()
    active = [x for x in board["projects"] if x["status"] == "active"]
    assert active[0]["task_counts"] == {"total": 1, "done": 0}


def test_invalid_status_rejected(client):
    p = client.post("/api/projects", json={"name": "x"}).json()
    r = client.patch(f"/api/projects/{p['id']}/move", json={"status": "bogus", "index": 0})
    assert r.status_code == 422
    assert "invalid status" in r.json()["detail"]


def test_sync_creates_projects_in_idea(client, monkeypatch):
    monkeypatch.setattr(
        sync,
        "fetch_repos",
        lambda: [
            gh_repo("fisherrjd/old", pushed_at="2026-01-01T00:00:00Z"),
            gh_repo("fisherrjd/new", pushed_at="2026-07-20T00:00:00Z"),
            gh_repo("fisherrjd/dusty", isArchived=True),
        ],
    )
    result = client.post("/api/sync").json()
    assert result["created"] == 3 and result["archived_count"] == 1

    board = client.get("/api/board").json()
    idea = [p for p in board["projects"] if p["status"] == "idea"]
    # archived repo gets no card; recent repo sorts first
    assert [p["name"] for p in idea] == ["new", "old"]
    assert board["last_synced_at"] is not None


def test_sync_never_clobbers_user_state(client, monkeypatch):
    monkeypatch.setattr(sync, "fetch_repos", lambda: [gh_repo("fisherrjd/thing")])
    client.post("/api/sync")
    p = client.get("/api/board").json()["projects"][0]
    client.patch(f"/api/projects/{p['id']}/move", json={"status": "active", "index": 0})
    client.patch(f"/api/projects/{p['id']}", json={"notes": "mine"})

    monkeypatch.setattr(
        sync, "fetch_repos", lambda: [gh_repo("fisherrjd/thing", description="changed upstream")]
    )
    result = client.post("/api/sync").json()
    assert result["created"] == 0 and result["updated"] == 1

    fresh = client.get(f"/api/projects/{p['id']}").json()
    assert fresh["status"] == "active" and fresh["notes"] == "mine"
    assert fresh["repos"][0]["description"] == "changed upstream"


def test_sync_gh_missing_returns_503(client, monkeypatch):
    def boom():
        raise sync.SyncError("gh not found on PATH — install the GitHub CLI", 503)

    monkeypatch.setattr(sync, "fetch_repos", boom)
    r = client.post("/api/sync")
    assert r.status_code == 503
    assert "gh not found" in r.json()["detail"]


def test_group_repos_deletes_husks(client, monkeypatch):
    monkeypatch.setattr(
        sync,
        "fetch_repos",
        lambda: [gh_repo("OldSchool-Market-Research/ge-data"), gh_repo("OldSchool-Market-Research/ge-mcp")],
    )
    client.post("/api/sync")
    assert len(client.get("/api/board").json()["projects"]) == 2

    grouped = client.post(
        "/api/projects",
        json={
            "name": "osrs-ge",
            "status": "active",
            "repos": ["OldSchool-Market-Research/ge-data", "OldSchool-Market-Research/ge-mcp"],
        },
    ).json()
    board = client.get("/api/board").json()
    assert [p["name"] for p in board["projects"]] == ["osrs-ge"]
    assert len(grouped["repos"]) == 2


def test_unassign_and_delete(client):
    add_repo("fisherrjd/a")
    p = client.post("/api/projects", json={"name": "keeper", "repos": ["fisherrjd/a"]}).json()
    r = client.delete(f"/api/projects/{p['id']}/repos/fisherrjd/a")
    assert r.status_code == 200
    assert client.get("/api/repos", params={"unassigned": True}).json()[0]["full_name"] == "fisherrjd/a"
    assert client.delete(f"/api/projects/{p['id']}").status_code == 200
    assert client.get(f"/api/projects/{p['id']}").status_code == 404

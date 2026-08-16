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


# ── task description + source ─────────────────────────────────────────────────

def test_task_description_and_source_roundtrip(client):
    p = client.post("/api/projects", json={"name": "proj"}).json()
    col = p["columns"][0]
    t = client.post(
        f"/api/columns/{col['id']}/tasks",
        json={"title": "fix it", "description": "## evidence\n- line", "source": "log-scan"},
    ).json()
    assert t["description"] == "## evidence\n- line"
    assert t["source"] == "log-scan"

    # patch description alone; title untouched, source immutable
    t2 = client.patch(f"/api/tasks/{t['id']}", json={"description": "updated"}).json()
    assert t2["description"] == "updated" and t2["title"] == "fix it"
    assert t2["source"] == "log-scan"

    # source survives a move
    done_col = p["columns"][-1]
    moved = client.patch(
        f"/api/tasks/{t['id']}/move", json={"column_id": done_col["id"], "index": 0}
    ).json()
    assert moved["source"] == "log-scan" and moved["description"] == "updated"


def test_task_defaults_empty_description_source(client):
    p = client.post("/api/projects", json={"name": "proj"}).json()
    t = client.post(
        f"/api/columns/{p['columns'][0]['id']}/tasks", json={"title": "plain"}
    ).json()
    assert t["description"] == "" and t["source"] == ""


# ── archived only on the Archived tab ─────────────────────────────────────────

def test_repos_default_excludes_archived(client):
    add_repo("o/live")
    add_repo("o/dead", archived=1)
    names = [r["full_name"] for r in client.get("/api/repos").json()]
    assert names == ["o/live"]

    only_archived = [r["full_name"] for r in client.get("/api/repos?archived=true").json()]
    assert only_archived == ["o/dead"]

    unassigned = [r["full_name"] for r in client.get("/api/repos?unassigned=true").json()]
    assert unassigned == ["o/live"]


def test_board_excludes_archived_repos_from_live_projects(client):
    p = client.post("/api/projects", json={"name": "proj"}).json()
    add_repo("o/live", project_id=p["id"])
    add_repo("o/dead", project_id=p["id"], archived=1)

    board = client.get("/api/board").json()
    proj = next(x for x in board["projects"] if x["id"] == p["id"])
    assert [r["full_name"] for r in proj["repos"]] == ["o/live"]

    # include_archived still returns everything (feeds the Archived tab)
    board_all = client.get("/api/board?include_archived=true").json()
    proj_all = next(x for x in board_all["projects"] if x["id"] == p["id"])
    assert {r["full_name"] for r in proj_all["repos"]} == {"o/live", "o/dead"}
# ── heimdall read-only proxy ───────────────────────────────────────────────────

def test_heimdall_proxy_allowlist_and_upstream(client, monkeypatch):
    import io
    import json as jsonlib
    import urllib.request

    class FakeResp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    calls = []

    def fake_urlopen(url, timeout=None):
        calls.append(url)
        return FakeResp(jsonlib.dumps([{"id": 1, "pulse_type": "log-scan"}]).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    r = client.get("/api/heimdall/pulses?limit=5")
    assert r.status_code == 200 and r.json()[0]["pulse_type"] == "log-scan"
    assert calls == ["http://10.42.0.1:3050/api/pulses?limit=5"]

    assert client.get("/api/heimdall/nope").status_code == 404


def test_heimdall_proxy_502_when_unreachable(client, monkeypatch):
    import urllib.error
    import urllib.request

    def fail(url, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", fail)
    r = client.get("/api/heimdall/health")
    assert r.status_code == 502


def test_heimdall_asset_proxy(client, monkeypatch):
    import io
    import urllib.request

    class FakeResp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    calls = []

    def fake_urlopen(url, timeout=None):
        calls.append(url)
        return FakeResp(b"\x89PNGfake")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    r = client.get("/api/heimdall/avatars/implementer.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content == b"\x89PNGfake"
    assert calls == ["http://10.42.0.1:3050/api/avatars/implementer.png"]

    r = client.get("/api/heimdall/sounds/ticket.wav")
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"

    # kind and basename are allowlisted before any upstream call
    n = len(calls)
    assert client.get("/api/heimdall/nope/x.png").status_code == 404
    assert client.get("/api/heimdall/avatars/x.gif").status_code == 404
    # encoded traversal never matches the route (SPA fallback answers instead)
    r = client.get("/api/heimdall/avatars/..%2Fsecret.png")
    assert "image/png" not in r.headers["content-type"]
    assert len(calls) == n


def test_heimdall_write_proxy(client, monkeypatch):
    import io
    import json as jsonlib
    import urllib.request

    from atlas import main as main_mod

    class FakeResp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(main_mod, "ORC_API_TOKEN", "sekrit")
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["auth"] = req.get_header("Authorization")
        captured["body"] = jsonlib.loads(req.data)
        return FakeResp(jsonlib.dumps({"detail": "ok", "git_warning": None}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    r = client.post("/api/heimdall/personas/implementer", json={"model": "opus"})
    assert r.status_code == 200 and r.json()["detail"] == "ok"
    assert captured["auth"] == "Bearer sekrit"
    assert captured["url"].endswith("/api/personas/implementer")
    assert captured["body"] == {"model": "opus"}

    # upstream refusal passes through with its detail
    def refuse(req, timeout=None):
        raise urllib.error.HTTPError(
            req.full_url, 403, "forbidden", {}, io.BytesIO(b'{"detail": "jail"}')
        )

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    r = client.post("/api/heimdall/personas/implementer", json={"tools": "Bash(*)"})
    assert r.status_code == 403 and r.json()["detail"] == "jail"

    assert client.post("/api/heimdall/personas/Bad Name", json={}).status_code == 404


def test_heimdall_write_disabled_without_token(client, monkeypatch):
    from atlas import main as main_mod

    monkeypatch.setattr(main_mod, "ORC_API_TOKEN", "")
    assert client.post("/api/heimdall/personas/x", json={}).status_code == 503

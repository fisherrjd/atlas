from atlas import db
from tests.conftest import add_repo


def test_create_project_defaults():
    p = db.create_project("thing")
    assert p["status"] == "idea"
    assert p["sort_order"] == 0
    assert p["notes"] == ""
    assert p["repos"] == [] and p["tasks"] == []


def test_new_projects_append_to_column():
    a = db.create_project("a")
    b = db.create_project("b")
    assert (a["sort_order"], b["sort_order"]) == (0, 1)


def test_move_reindexes_both_columns():
    a = db.create_project("a")
    b = db.create_project("b")
    c = db.create_project("c")
    moved = db.move("projects", b["id"], "active", 0)
    assert moved["status"] == "active" and moved["sort_order"] == 0
    idea = [
        (r["id"], r["sort_order"])
        for r in db.conn.execute(
            "SELECT id, sort_order FROM projects WHERE status = 'idea' ORDER BY sort_order"
        )
    ]
    assert idea == [(a["id"], 0), (c["id"], 1)]


def test_move_within_column_reorders():
    a = db.create_project("a")
    b = db.create_project("b")
    c = db.create_project("c")
    db.move("projects", c["id"], "idea", 0)
    order = [
        r["id"]
        for r in db.conn.execute(
            "SELECT id FROM projects WHERE status = 'idea' ORDER BY sort_order"
        )
    ]
    assert order == [c["id"], a["id"], b["id"]]


def test_task_move_scoped_to_project():
    p1 = db.create_project("p1")
    p2 = db.create_project("p2")
    t1 = db.create_task(p1["id"], "one")
    t2 = db.create_task(p2["id"], "other")
    db.move("tasks", t1["id"], "doing", 0)
    # p2's task untouched
    row = db.conn.execute("SELECT * FROM tasks WHERE id = ?", (t2["id"],)).fetchone()
    assert row["status"] == "todo" and row["sort_order"] == 0


def test_delete_project_cascades_tasks_and_unlinks_repos():
    p = db.create_project("p")
    db.create_task(p["id"], "t")
    add_repo("fisherrjd/thing", project_id=p["id"])
    assert db.delete_project(p["id"])
    assert db.conn.execute("SELECT COUNT(*) AS n FROM tasks").fetchone()["n"] == 0
    repo = db.conn.execute("SELECT * FROM repos WHERE full_name = 'fisherrjd/thing'").fetchone()
    assert repo["project_id"] is None


def test_husk_deleted_when_repo_moves_away():
    add_repo("fisherrjd/solo")
    husk = db.create_project("solo", repo_full_names=["fisherrjd/solo"])
    target = db.create_project("group")
    db.assign_repo(target["id"], "fisherrjd/solo")
    assert db.get_project(husk["id"]) is None


def test_user_touched_project_survives_repo_move():
    add_repo("fisherrjd/solo")
    kept = db.create_project("solo", repo_full_names=["fisherrjd/solo"])
    db.update_project(kept["id"], {"notes": "important thoughts"})
    target = db.create_project("group")
    db.assign_repo(target["id"], "fisherrjd/solo")
    assert db.get_project(kept["id"]) is not None

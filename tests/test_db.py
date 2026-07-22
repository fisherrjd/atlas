import pytest

from atlas import db
from tests.conftest import add_repo


def col(project: dict, name: str) -> dict:
    return next(c for c in project["columns"] if c["name"] == name)


def test_create_project_defaults():
    p = db.create_project("thing")
    assert p["status"] == "idea"
    assert p["sort_order"] == 0
    assert p["notes"] == ""
    assert p["repos"] == []
    assert [c["name"] for c in p["columns"]] == ["Todo", "Doing", "Done"]
    assert [c["is_done"] for c in p["columns"]] == [0, 0, 1]


def test_new_projects_append_within_status():
    a = db.create_project("a")
    b = db.create_project("b")
    assert (a["sort_order"], b["sort_order"]) == (0, 1)


def test_set_project_status():
    p = db.create_project("p")
    moved = db.set_project_status(p["id"], "active")
    assert moved["status"] == "active"


def test_task_move_reindexes_both_columns():
    p = db.create_project("p")
    todo, doing = col(p, "Todo"), col(p, "Doing")
    t1 = db.create_task(todo["id"], "one")
    t2 = db.create_task(todo["id"], "two")
    t3 = db.create_task(todo["id"], "three")

    moved = db.move_task(t2["id"], doing["id"], 0)
    assert moved["column_id"] == doing["id"] and moved["sort_order"] == 0

    remaining = [
        (r["id"], r["sort_order"])
        for r in db.conn.execute(
            "SELECT id, sort_order FROM tasks WHERE column_id = ? ORDER BY sort_order",
            (todo["id"],),
        )
    ]
    assert remaining == [(t1["id"], 0), (t3["id"], 1)]


def test_task_move_within_column_reorders():
    p = db.create_project("p")
    todo = col(p, "Todo")
    t1 = db.create_task(todo["id"], "one")
    t2 = db.create_task(todo["id"], "two")
    db.move_task(t2["id"], todo["id"], 0)
    order = [
        r["id"]
        for r in db.conn.execute(
            "SELECT id FROM tasks WHERE column_id = ? ORDER BY sort_order", (todo["id"],)
        )
    ]
    assert order == [t2["id"], t1["id"]]


def test_cross_project_task_move_rejected():
    p1 = db.create_project("p1")
    p2 = db.create_project("p2")
    t = db.create_task(col(p1, "Todo")["id"], "task")
    with pytest.raises(db.CrossProjectMove):
        db.move_task(t["id"], col(p2, "Todo")["id"], 0)


def test_column_lifecycle():
    p = db.create_project("p")
    review = db.create_column(p["id"], "Review")
    assert review["sort_order"] == 3

    db.move_column(review["id"], 1)
    fresh = db.get_project(p["id"])
    assert [c["name"] for c in fresh["columns"]] == ["Todo", "Review", "Doing", "Done"]

    db.rename_column(review["id"], "In review")
    assert db.get_column(review["id"])["name"] == "In review"

    assert db.delete_column(review["id"])


def test_column_delete_guards():
    p = db.create_project("p")
    todo = col(p, "Todo")
    db.create_task(todo["id"], "t")
    with pytest.raises(db.ColumnNotDeletable):
        db.delete_column(todo["id"])

    solo = db.create_project("solo")
    for c in solo["columns"][1:]:
        db.delete_column(c["id"])
    with pytest.raises(db.ColumnNotDeletable):
        db.delete_column(solo["columns"][0]["id"])


def test_delete_project_cascades_and_unlinks():
    p = db.create_project("p")
    db.create_task(col(p, "Todo")["id"], "t")
    add_repo("fisherrjd/thing", project_id=p["id"])
    assert db.delete_project(p["id"])
    assert db.conn.execute("SELECT COUNT(*) AS n FROM tasks").fetchone()["n"] == 0
    assert db.conn.execute("SELECT COUNT(*) AS n FROM columns").fetchone()["n"] == 0
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
    db.create_task(col(kept, "Todo")["id"], "keep me")
    target = db.create_project("group")
    db.assign_repo(target["id"], "fisherrjd/solo")
    assert db.get_project(kept["id"]) is not None

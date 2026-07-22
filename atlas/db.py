"""SQLite persistence for atlas.

Single module-level connection (single-user app; all FastAPI routes are async
and run on one event-loop thread, so access is serialized). Schema is created
at import. ``ATLAS_DB`` picks the database file; migrations are by hand —
this app's state is cheap to rebuild (delete the file and resync).

Hierarchy: projects (grid on the main page) → columns (each project's own
kanban, default Todo/Doing/Done) → tasks.

Invariant: sync only ever writes repo metadata columns — ``repos.project_id``
and everything in ``projects``/``columns``/``tasks`` belong to the user.
"""
import os
import sqlite3
from pathlib import Path

BASE_DIR = Path(os.environ.get("ATLAS_BASE", Path.cwd()))
DB_PATH = Path(os.environ.get("ATLAS_DB", BASE_DIR / "atlas.sqlite"))

PROJECT_STATUSES = ("idea", "backlog", "active", "paused", "done")

DEFAULT_COLUMNS = (("Todo", 0), ("Doing", 0), ("Done", 1))  # (name, is_done)

_TASKS_DDL = """
CREATE TABLE IF NOT EXISTS tasks (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  column_id   INTEGER NOT NULL REFERENCES columns(id) ON DELETE CASCADE,
  title       TEXT NOT NULL,
  sort_order  INTEGER NOT NULL DEFAULT 0,
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
)
"""

_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS projects (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  name        TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  status      TEXT NOT NULL DEFAULT 'idea'
              CHECK (status IN ('idea','backlog','active','paused','done')),
  sort_order  INTEGER NOT NULL DEFAULT 0,
  notes       TEXT NOT NULL DEFAULT '',
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS repos (
  full_name   TEXT PRIMARY KEY,
  project_id  INTEGER REFERENCES projects(id) ON DELETE SET NULL,
  name        TEXT NOT NULL,
  owner       TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  language    TEXT,
  pushed_at   TEXT,
  url         TEXT NOT NULL,
  archived    INTEGER NOT NULL DEFAULT 0,
  synced_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS columns (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  name        TEXT NOT NULL,
  sort_order  INTEGER NOT NULL DEFAULT 0,
  is_done     INTEGER NOT NULL DEFAULT 0
);

{_TASKS_DDL};

CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
conn.row_factory = sqlite3.Row
conn.execute("PRAGMA journal_mode = WAL")
conn.execute("PRAGMA foreign_keys = ON")
conn.executescript(_SCHEMA)


def _ensure_default_columns_tx(project_id: int) -> None:
    n = conn.execute(
        "SELECT COUNT(*) AS n FROM columns WHERE project_id = ?", (project_id,)
    ).fetchone()["n"]
    if n == 0:
        for i, (name, is_done) in enumerate(DEFAULT_COLUMNS):
            conn.execute(
                "INSERT INTO columns (project_id, name, sort_order, is_done) VALUES (?, ?, ?, ?)",
                (project_id, name, i, is_done),
            )


def _migrate() -> None:
    """One-time migration from the v0 schema (tasks with project_id + status)."""
    task_cols = {r["name"] for r in conn.execute("PRAGMA table_info(tasks)")}
    with conn:
        if "status" in task_cols:
            old = conn.execute("SELECT * FROM tasks").fetchall()
            conn.execute("DROP TABLE tasks")
            conn.execute(_TASKS_DDL)
            for t in old:
                _ensure_default_columns_tx(t["project_id"])
                target = {"todo": "Todo", "doing": "Doing", "done": "Done"}[t["status"]]
                col = conn.execute(
                    "SELECT id FROM columns WHERE project_id = ? AND name = ?",
                    (t["project_id"], target),
                ).fetchone()
                conn.execute(
                    "INSERT INTO tasks (column_id, title, sort_order, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (col["id"], t["title"], t["sort_order"], t["created_at"], t["updated_at"]),
                )
        # every project has a kanban
        for p in conn.execute("SELECT id FROM projects").fetchall():
            _ensure_default_columns_tx(p["id"])


_migrate()


# ---------------------------------------------------------------- projects

def _next_sort_order(table: str, where: str, args: tuple) -> int:
    row = conn.execute(
        f"SELECT COALESCE(MAX(sort_order) + 1, 0) AS n FROM {table} WHERE {where}", args
    ).fetchone()
    return row["n"]


def _insert_project_tx(name: str, description: str, status: str) -> int:
    cur = conn.execute(
        "INSERT INTO projects (name, description, status, sort_order) VALUES (?, ?, ?, ?)",
        (name, description, status, _next_sort_order("projects", "status = ?", (status,))),
    )
    _ensure_default_columns_tx(cur.lastrowid)
    return cur.lastrowid


def create_project(
    name: str,
    description: str = "",
    status: str = "idea",
    repo_full_names: list[str] | None = None,
) -> dict:
    with conn:
        project_id = _insert_project_tx(name, description, status)
        for full_name in repo_full_names or []:
            _assign_repo_tx(project_id, full_name)
    return get_project(project_id)


def get_project(project_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        return None
    project = dict(row)
    project["repos"] = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM repos WHERE project_id = ? ORDER BY pushed_at DESC", (project_id,)
        )
    ]
    columns = [
        dict(c)
        for c in conn.execute(
            "SELECT * FROM columns WHERE project_id = ? ORDER BY sort_order", (project_id,)
        )
    ]
    for col in columns:
        col["tasks"] = [
            dict(t)
            for t in conn.execute(
                "SELECT * FROM tasks WHERE column_id = ? ORDER BY sort_order", (col["id"],)
            )
        ]
    project["columns"] = columns
    return project


def update_project(project_id: int, fields: dict) -> dict | None:
    allowed = {k: v for k, v in fields.items() if k in ("name", "description", "notes")}
    if allowed:
        sets = ", ".join(f"{k} = ?" for k in allowed)
        with conn:
            conn.execute(
                f"UPDATE projects SET {sets}, updated_at = datetime('now') WHERE id = ?",
                (*allowed.values(), project_id),
            )
    return get_project(project_id)


def delete_project(project_id: int) -> bool:
    with conn:
        cur = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    return cur.rowcount > 0


def set_project_status(project_id: int, status: str) -> dict | None:
    row = conn.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        return None
    with conn:
        conn.execute(
            "UPDATE projects SET status = ?, sort_order = ?, updated_at = datetime('now')"
            " WHERE id = ?",
            (status, _next_sort_order("projects", "status = ?", (status,)), project_id),
        )
    return dict(conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone())


def board() -> dict:
    projects = [
        dict(r) for r in conn.execute("SELECT * FROM projects ORDER BY status, sort_order")
    ]
    repos_by_project: dict[int, list[dict]] = {}
    for r in conn.execute(
        "SELECT * FROM repos WHERE project_id IS NOT NULL ORDER BY pushed_at DESC"
    ):
        repos_by_project.setdefault(r["project_id"], []).append(dict(r))
    counts = {
        r["project_id"]: {"total": r["total"], "done": r["done"]}
        for r in conn.execute(
            "SELECT c.project_id, COUNT(*) AS total,"
            " COALESCE(SUM(c.is_done), 0) AS done"
            " FROM tasks t JOIN columns c ON t.column_id = c.id"
            " GROUP BY c.project_id"
        )
    }
    for p in projects:
        p["repos"] = repos_by_project.get(p["id"], [])
        p["task_counts"] = counts.get(p["id"], {"total": 0, "done": 0})
    return {"projects": projects, "last_synced_at": get_meta("last_synced_at")}


# ---------------------------------------------------------------- columns

def get_column(column_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM columns WHERE id = ?", (column_id,)).fetchone()
    return dict(row) if row else None


def create_column(project_id: int, name: str) -> dict:
    with conn:
        cur = conn.execute(
            "INSERT INTO columns (project_id, name, sort_order) VALUES (?, ?, ?)",
            (project_id, name, _next_sort_order("columns", "project_id = ?", (project_id,))),
        )
    return get_column(cur.lastrowid)


def rename_column(column_id: int, name: str) -> dict | None:
    with conn:
        conn.execute("UPDATE columns SET name = ? WHERE id = ?", (name, column_id))
    return get_column(column_id)


def move_column(column_id: int, index: int) -> dict | None:
    with conn:
        col = conn.execute("SELECT * FROM columns WHERE id = ?", (column_id,)).fetchone()
        if col is None:
            return None
        ids = [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM columns WHERE project_id = ? ORDER BY sort_order",
                (col["project_id"],),
            )
            if r["id"] != column_id
        ]
        ids.insert(max(0, min(index, len(ids))), column_id)
        for i, cid in enumerate(ids):
            conn.execute("UPDATE columns SET sort_order = ? WHERE id = ?", (i, cid))
    return get_column(column_id)


class ColumnNotDeletable(Exception):
    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


def delete_column(column_id: int) -> bool:
    with conn:
        col = conn.execute("SELECT * FROM columns WHERE id = ?", (column_id,)).fetchone()
        if col is None:
            return False
        tasks = conn.execute(
            "SELECT COUNT(*) AS n FROM tasks WHERE column_id = ?", (column_id,)
        ).fetchone()["n"]
        if tasks:
            raise ColumnNotDeletable("column still has tasks — move or delete them first")
        siblings = conn.execute(
            "SELECT COUNT(*) AS n FROM columns WHERE project_id = ?", (col["project_id"],)
        ).fetchone()["n"]
        if siblings <= 1:
            raise ColumnNotDeletable("a project needs at least one column")
        conn.execute("DELETE FROM columns WHERE id = ?", (column_id,))
    return True


# ---------------------------------------------------------------- repos

def list_repos(unassigned: bool = False) -> list[dict]:
    where = "WHERE project_id IS NULL AND archived = 0" if unassigned else ""
    return [
        dict(r)
        for r in conn.execute(f"SELECT * FROM repos {where} ORDER BY pushed_at DESC")
    ]


def _maybe_delete_husk(project_id: int | None, repo_name: str) -> bool:
    """Delete a sync-auto-created card left empty after its repo moved away.

    Guarded so nothing user-authored is deletable: the project must have no
    repos, no tasks, empty notes, and still carry the repo's own name.
    """
    if project_id is None:
        return False
    row = conn.execute(
        """
        SELECT p.id FROM projects p
        WHERE p.id = ? AND p.name = ? AND p.notes = ''
          AND NOT EXISTS (SELECT 1 FROM repos r WHERE r.project_id = p.id)
          AND NOT EXISTS (
            SELECT 1 FROM tasks t JOIN columns c ON t.column_id = c.id
            WHERE c.project_id = p.id
          )
        """,
        (project_id, repo_name),
    ).fetchone()
    if row is None:
        return False
    conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    return True


def _assign_repo_tx(project_id: int, full_name: str) -> None:
    repo = conn.execute("SELECT * FROM repos WHERE full_name = ?", (full_name,)).fetchone()
    if repo is None:
        raise KeyError(full_name)
    conn.execute(
        "UPDATE repos SET project_id = ? WHERE full_name = ?", (project_id, full_name)
    )
    old_project_id = repo["project_id"]
    if old_project_id is not None and old_project_id != project_id:
        _maybe_delete_husk(old_project_id, repo["name"])


def assign_repo(project_id: int, full_name: str) -> None:
    with conn:
        _assign_repo_tx(project_id, full_name)


def unassign_repo(project_id: int, full_name: str) -> bool:
    with conn:
        cur = conn.execute(
            "UPDATE repos SET project_id = NULL WHERE full_name = ? AND project_id = ?",
            (full_name, project_id),
        )
    return cur.rowcount > 0


# ---------------------------------------------------------------- tasks

def get_task(task_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return dict(row) if row else None


def create_task(column_id: int, title: str) -> dict | None:
    if get_column(column_id) is None:
        return None
    with conn:
        cur = conn.execute(
            "INSERT INTO tasks (column_id, title, sort_order) VALUES (?, ?, ?)",
            (column_id, title, _next_sort_order("tasks", "column_id = ?", (column_id,))),
        )
    return get_task(cur.lastrowid)


def update_task(task_id: int, title: str) -> dict | None:
    with conn:
        conn.execute(
            "UPDATE tasks SET title = ?, updated_at = datetime('now') WHERE id = ?",
            (title, task_id),
        )
    return get_task(task_id)


class CrossProjectMove(Exception):
    pass


def move_task(task_id: int, column_id: int, index: int) -> dict | None:
    """Move a task to (column, position); reindex both affected columns 0..n."""
    with conn:
        task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if task is None:
            return None
        target = conn.execute("SELECT * FROM columns WHERE id = ?", (column_id,)).fetchone()
        if target is None:
            return None
        source = conn.execute(
            "SELECT * FROM columns WHERE id = ?", (task["column_id"],)
        ).fetchone()
        if target["project_id"] != source["project_id"]:
            raise CrossProjectMove()

        def column_task_ids(cid: int) -> list[int]:
            return [
                r["id"]
                for r in conn.execute(
                    "SELECT id FROM tasks WHERE column_id = ? ORDER BY sort_order", (cid,)
                )
                if r["id"] != task_id
            ]

        src = column_task_ids(task["column_id"])
        dst = src if column_id == task["column_id"] else column_task_ids(column_id)
        dst.insert(max(0, min(index, len(dst))), task_id)

        conn.execute(
            "UPDATE tasks SET column_id = ?, updated_at = datetime('now') WHERE id = ?",
            (column_id, task_id),
        )
        if column_id != task["column_id"]:
            for i, tid in enumerate(src):
                conn.execute("UPDATE tasks SET sort_order = ? WHERE id = ?", (i, tid))
        for i, tid in enumerate(dst):
            conn.execute("UPDATE tasks SET sort_order = ? WHERE id = ?", (i, tid))
    return get_task(task_id)


def delete_task(task_id: int) -> bool:
    with conn:
        cur = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    return cur.rowcount > 0


# ---------------------------------------------------------------- meta

def get_meta(key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_meta(key: str, value: str) -> None:
    with conn:
        conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

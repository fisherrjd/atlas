"""SQLite persistence for atlas.

Single module-level connection (single-user app; all FastAPI routes are async
and run on one event-loop thread, so access is serialized). Schema is created
at import. ``ATLAS_DB`` picks the database file; migrations are by hand —
this app's state is cheap to rebuild (delete the file and resync).

Invariant: sync only ever writes repo metadata columns — ``repos.project_id``
and everything in ``projects``/``tasks`` belong to the user.
"""
import os
import sqlite3
from pathlib import Path

BASE_DIR = Path(os.environ.get("ATLAS_BASE", Path.cwd()))
DB_PATH = Path(os.environ.get("ATLAS_DB", BASE_DIR / "atlas.sqlite"))

PROJECT_STATUSES = ("idea", "backlog", "active", "paused", "done")
TASK_STATUSES = ("todo", "doing", "done")

_SCHEMA = """
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

CREATE TABLE IF NOT EXISTS tasks (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  title       TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'todo' CHECK (status IN ('todo','doing','done')),
  sort_order  INTEGER NOT NULL DEFAULT 0,
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

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


# ---------------------------------------------------------------- projects

def _next_sort_order(table: str, status: str, project_id: int | None = None) -> int:
    scope, args = "", [status]
    if project_id is not None:
        scope = "project_id = ? AND "
        args = [project_id, status]
    row = conn.execute(
        f"SELECT COALESCE(MAX(sort_order) + 1, 0) AS n FROM {table} WHERE {scope}status = ?",
        args,
    ).fetchone()
    return row["n"]


def create_project(
    name: str,
    description: str = "",
    status: str = "idea",
    repo_full_names: list[str] | None = None,
) -> dict:
    with conn:
        cur = conn.execute(
            "INSERT INTO projects (name, description, status, sort_order) VALUES (?, ?, ?, ?)",
            (name, description, status, _next_sort_order("projects", status)),
        )
        project_id = cur.lastrowid
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
    project["tasks"] = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM tasks WHERE project_id = ? ORDER BY status, sort_order", (project_id,)
        )
    ]
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
            "SELECT project_id, COUNT(*) AS total, COALESCE(SUM(status = 'done'), 0) AS done"
            " FROM tasks GROUP BY project_id"
        )
    }
    for p in projects:
        p["repos"] = repos_by_project.get(p["id"], [])
        p["task_counts"] = counts.get(p["id"], {"total": 0, "done": 0})
    return {"projects": projects, "last_synced_at": get_meta("last_synced_at")}


# ---------------------------------------------------------------- move/reorder

def move(table: str, item_id: int, new_status: str, new_index: int) -> dict | None:
    """Move a project/task to (column, position); reindex affected columns 0..n."""
    assert table in ("projects", "tasks")
    with conn:
        row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (item_id,)).fetchone()
        if row is None:
            return None
        old_status = row["status"]
        scope, scope_args = "", ()
        if table == "tasks":
            scope, scope_args = "project_id = ? AND ", (row["project_id"],)

        def column_ids(status: str) -> list[int]:
            return [
                r["id"]
                for r in conn.execute(
                    f"SELECT id FROM {table} WHERE {scope}status = ? ORDER BY sort_order",
                    (*scope_args, status),
                )
                if r["id"] != item_id
            ]

        src = column_ids(old_status)
        dst = src if new_status == old_status else column_ids(new_status)
        dst.insert(max(0, min(new_index, len(dst))), item_id)

        conn.execute(
            f"UPDATE {table} SET status = ?, updated_at = datetime('now') WHERE id = ?",
            (new_status, item_id),
        )
        if new_status != old_status:
            for i, iid in enumerate(src):
                conn.execute(f"UPDATE {table} SET sort_order = ? WHERE id = ?", (i, iid))
        for i, iid in enumerate(dst):
            conn.execute(f"UPDATE {table} SET sort_order = ? WHERE id = ?", (i, iid))

    fresh = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (item_id,)).fetchone()
    return dict(fresh)


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
          AND NOT EXISTS (SELECT 1 FROM tasks t WHERE t.project_id = p.id)
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

def create_task(project_id: int, title: str) -> dict:
    with conn:
        cur = conn.execute(
            "INSERT INTO tasks (project_id, title, sort_order) VALUES (?, ?, ?)",
            (project_id, title, _next_sort_order("tasks", "todo", project_id)),
        )
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (cur.lastrowid,)).fetchone()
    return dict(row)


def update_task(task_id: int, title: str) -> dict | None:
    with conn:
        conn.execute(
            "UPDATE tasks SET title = ?, updated_at = datetime('now') WHERE id = ?",
            (title, task_id),
        )
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return dict(row) if row else None


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

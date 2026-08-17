"""SQLite persistence for atlas.

Single module-level connection (single-user app; all FastAPI routes are async
and run on one event-loop thread, so access is serialized). Schema is created
at import. ``ATLAS_DB`` picks the database file; migrations are by hand —
this app's state is cheap to rebuild (delete the file and resync).

Hierarchy: projects (grid on the main page) → columns (each project's own
kanban, default Triage/Todo/Staffed/In PR/Done) → tasks.

Invariant: sync writes repo metadata columns and may auto-create a project
card for an unassigned repo — but it never overwrites a user-set
``repos.project_id`` and never modifies existing
``projects``/``columns``/``tasks``; those belong to the user.
"""
import os
import sqlite3
from pathlib import Path

BASE_DIR = Path(os.environ.get("ATLAS_BASE", Path.cwd()))
DB_PATH = Path(os.environ.get("ATLAS_DB", BASE_DIR / "atlas.sqlite"))

PROJECT_STATUSES = ("idea", "backlog", "active", "paused", "done")

# The agent-loop lifecycle: Triage = findings land / failed attempts bounce back,
# Staffed = drag here to hand to the loop, In PR / Done = loop-managed.
# Todo stays the human backlog (loop pickup is opt-in per task).
DEFAULT_COLUMNS = (
    ("Triage", 0),
    ("Todo", 0),
    ("Staffed", 0),
    ("In PR", 0),
    ("Done", 1),
)  # (name, is_done)

_TASKS_DDL = """
CREATE TABLE IF NOT EXISTS tasks (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  column_id   INTEGER NOT NULL REFERENCES columns(id) ON DELETE CASCADE,
  title       TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  source      TEXT NOT NULL DEFAULT '',
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
  archived    INTEGER NOT NULL DEFAULT 0,
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

CREATE TABLE IF NOT EXISTS task_comments (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id    INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  author     TEXT NOT NULL,
  body       TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
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
    """One-time migrations. v0: tasks with project_id + status. v1: no archived flag."""
    project_cols = {r["name"] for r in conn.execute("PRAGMA table_info(projects)")}
    if "archived" not in project_cols:
        with conn:
            conn.execute(
                "ALTER TABLE projects ADD COLUMN archived INTEGER NOT NULL DEFAULT 0"
            )
    task_cols = {r["name"] for r in conn.execute("PRAGMA table_info(tasks)")}
    with conn:
        if "status" in task_cols:
            old = conn.execute("SELECT * FROM tasks").fetchall()
            conn.execute("DROP TABLE tasks")
            conn.execute(_TASKS_DDL)
            for t in old:
                _ensure_default_columns_tx(t["project_id"])
                # v0's "doing" has no column in the loop-era defaults; Todo is the
                # human backlog, so migrated WIP lands there rather than Staffed
                # (which would hand it straight to the agent loop).
                target = {"todo": "Todo", "doing": "Todo", "done": "Done"}[t["status"]]
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
    # v2: task body + filing source (agent tickets carry evidence + a persona badge)
    task_cols = {r["name"] for r in conn.execute("PRAGMA table_info(tasks)")}
    with conn:
        if "description" not in task_cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN description TEXT NOT NULL DEFAULT ''")
        if "source" not in task_cols:
            conn.execute("ALTER TABLE tasks ADD COLUMN source TEXT NOT NULL DEFAULT ''")


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
    comment_counts = {
        r["task_id"]: r["n"]
        for r in conn.execute(
            "SELECT tc.task_id AS task_id, COUNT(*) AS n FROM task_comments tc"
            " JOIN tasks t ON tc.task_id = t.id JOIN columns c ON t.column_id = c.id"
            " WHERE c.project_id = ? GROUP BY tc.task_id",
            (project_id,),
        )
    }
    for col in columns:
        col["tasks"] = [
            dict(t) | {"comment_count": comment_counts.get(t["id"], 0)}
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


def set_archived(project_id: int, archived: bool) -> dict | None:
    with conn:
        cur = conn.execute(
            "UPDATE projects SET archived = ?, updated_at = datetime('now') WHERE id = ?",
            (1 if archived else 0, project_id),
        )
    if cur.rowcount == 0:
        return None
    return get_project(project_id)


def now_view() -> list[dict]:
    """Active, unarchived projects with their in-progress (non-done-column) tasks."""
    projects = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM projects WHERE status = 'active' AND archived = 0"
            " ORDER BY sort_order"
        )
    ]
    for p in projects:
        p["tasks"] = [
            dict(t)
            for t in conn.execute(
                """
                SELECT t.*, c.name AS column_name FROM tasks t
                JOIN columns c ON t.column_id = c.id
                WHERE c.project_id = ? AND c.is_done = 0
                ORDER BY c.sort_order DESC, t.sort_order
                """,
                (p["id"],),
            )
        ]
    return projects


def backup(backup_dir: Path, stamp: str, keep: int = 14) -> Path:
    """Copy the live database to backup_dir/atlas-<stamp>.sqlite; prune old copies."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"atlas-{stamp}.sqlite"
    dest = sqlite3.connect(target)
    try:
        conn.backup(dest)
    finally:
        dest.close()
    old = sorted(backup_dir.glob("atlas-*.sqlite"))[:-keep]
    for f in old:
        f.unlink()
    return target


def board(include_archived: bool = False) -> dict:
    where = "" if include_archived else "WHERE archived = 0"
    projects = [
        dict(r)
        for r in conn.execute(f"SELECT * FROM projects {where} ORDER BY status, sort_order")
    ]
    repo_where = "" if include_archived else "AND archived = 0"
    repos_by_project: dict[int, list[dict]] = {}
    for r in conn.execute(
        f"SELECT * FROM repos WHERE project_id IS NOT NULL {repo_where} ORDER BY pushed_at DESC"
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


def update_column(
    column_id: int, name: str | None = None, is_done: bool | None = None
) -> dict | None:
    """Marking a column done unmarks any sibling — reconcile picks *the* done
    column per project, so two would make merge targeting ambiguous."""
    with conn:
        col = conn.execute(
            "SELECT * FROM columns WHERE id = ?", (column_id,)
        ).fetchone()
        if col is None:
            return None
        if name is not None:
            conn.execute("UPDATE columns SET name = ? WHERE id = ?", (name, column_id))
        if is_done is not None:
            if is_done:
                conn.execute(
                    "UPDATE columns SET is_done = 0 WHERE project_id = ?",
                    (col["project_id"],),
                )
            conn.execute(
                "UPDATE columns SET is_done = ? WHERE id = ?",
                (int(is_done), column_id),
            )
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

def list_repos(unassigned: bool = False, archived: bool = False) -> list[dict]:
    """Archived repos exist only on the Archived tab: default responses exclude
    them; ``archived=True`` returns only them."""
    clauses = ["archived = 1" if archived else "archived = 0"]
    if unassigned:
        clauses.append("project_id IS NULL")
    where = "WHERE " + " AND ".join(clauses)
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


def set_repo_archived_flag(full_name: str, archived: bool) -> None:
    with conn:
        conn.execute(
            "UPDATE repos SET archived = ? WHERE full_name = ?",
            (1 if archived else 0, full_name),
        )


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


def create_task(
    column_id: int, title: str, description: str = "", source: str = ""
) -> dict | None:
    if get_column(column_id) is None:
        return None
    with conn:
        cur = conn.execute(
            "INSERT INTO tasks (column_id, title, description, source, sort_order)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                column_id,
                title,
                description,
                source,
                _next_sort_order("tasks", "column_id = ?", (column_id,)),
            ),
        )
    return get_task(cur.lastrowid)


def update_task(task_id: int, fields: dict) -> dict | None:
    # source is set at creation and immutable — it records who filed the task
    allowed = {k: v for k, v in fields.items() if k in ("title", "description")}
    if allowed:
        sets = ", ".join(f"{k} = ?" for k in allowed)
        with conn:
            conn.execute(
                f"UPDATE tasks SET {sets}, updated_at = datetime('now') WHERE id = ?",
                (*allowed.values(), task_id),
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


# ---------------------------------------------------------------- comments

def list_comments(task_id: int) -> list[dict] | None:
    """Thread for a task, oldest first. None if the task doesn't exist."""
    if get_task(task_id) is None:
        return None
    return [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM task_comments WHERE task_id = ? ORDER BY id", (task_id,)
        )
    ]


def add_comment(task_id: int, author: str, body: str) -> dict | None:
    if get_task(task_id) is None:
        return None
    with conn:
        cur = conn.execute(
            "INSERT INTO task_comments (task_id, author, body) VALUES (?, ?, ?)",
            (task_id, author, body),
        )
    row = conn.execute(
        "SELECT * FROM task_comments WHERE id = ?", (cur.lastrowid,)
    ).fetchone()
    return dict(row)


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

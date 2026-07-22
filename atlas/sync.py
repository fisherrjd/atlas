"""GitHub sync via the `gh` CLI.

Uses `gh` rather than the REST API directly: it's already authed on the host,
so there's no token to provision or rotate, and no extra dependencies. Sync is
user-triggered and infrequent — subprocess overhead is irrelevant.

Rules (the invariant lives in db.py too): sync upserts repo *metadata* only.
It never writes ``repos.project_id`` and never touches projects or tasks —
kanban status, grouping, notes, and tasks are user state.
"""
import json
import subprocess
from datetime import datetime, timezone

from . import db

OWNERS = ["fisherrjd", "OldSchool-Market-Research"]

_GH_FIELDS = "name,description,pushedAt,primaryLanguage,isArchived,url,owner"


class SyncError(Exception):
    def __init__(self, detail: str, status_code: int = 502):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def fetch_repos() -> list[dict]:
    """Fetch repo metadata for all OWNERS. Blocking — call via asyncio.to_thread."""
    repos: list[dict] = []
    for owner in OWNERS:
        try:
            proc = subprocess.run(
                ["gh", "repo", "list", owner, "--limit", "200", "--json", _GH_FIELDS],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except FileNotFoundError:
            raise SyncError("gh not found on PATH — install the GitHub CLI", 503)
        except subprocess.TimeoutExpired:
            raise SyncError(f"gh timed out listing repos for {owner}", 502)
        if proc.returncode != 0:
            stderr = (proc.stderr or "gh failed").strip().splitlines()
            raise SyncError(f"gh error for {owner}: {stderr[-1] if stderr else 'unknown'}", 502)
        repos.extend(json.loads(proc.stdout))
    return repos


def apply(fetched: list[dict]) -> dict:
    """Upsert repo metadata; auto-create projects for new, non-archived repos."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    created = updated = archived_count = 0

    # Most-recently-pushed first so first-sync auto-created cards land in
    # Idea with active repos on top.
    fetched = sorted(fetched, key=lambda r: r.get("pushedAt") or "", reverse=True)

    with db.conn:
        for r in fetched:
            owner = r["owner"]["login"] if isinstance(r.get("owner"), dict) else r.get("owner", "")
            full_name = f"{owner}/{r['name']}"
            language = (r.get("primaryLanguage") or {}).get("name")
            archived = 1 if r.get("isArchived") else 0
            existing = db.conn.execute(
                "SELECT full_name FROM repos WHERE full_name = ?", (full_name,)
            ).fetchone()
            db.conn.execute(
                """
                INSERT INTO repos (full_name, name, owner, description, language,
                                   pushed_at, url, archived, synced_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(full_name) DO UPDATE SET
                  name = excluded.name, owner = excluded.owner,
                  description = excluded.description, language = excluded.language,
                  pushed_at = excluded.pushed_at, url = excluded.url,
                  archived = excluded.archived, synced_at = excluded.synced_at
                """,
                (
                    full_name,
                    r["name"],
                    owner,
                    r.get("description") or "",
                    language,
                    r.get("pushedAt"),
                    r["url"],
                    archived,
                    now,
                ),
            )
            if existing is None:
                created += 1
            else:
                updated += 1
            if archived:
                archived_count += 1

        # Auto-create a project card for every unassigned, non-archived repo.
        for repo in db.conn.execute(
            "SELECT * FROM repos WHERE project_id IS NULL AND archived = 0"
            " ORDER BY pushed_at DESC"
        ).fetchall():
            project_id = db._insert_project_tx(repo["name"], repo["description"], "idea")
            db.conn.execute(
                "UPDATE repos SET project_id = ? WHERE full_name = ?",
                (project_id, repo["full_name"]),
            )

    db.set_meta("last_synced_at", now)
    return {"created": created, "updated": updated, "archived_count": archived_count}

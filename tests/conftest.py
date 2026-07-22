"""Shared fixtures.

``atlas.db`` reads ``ATLAS_BASE``/``ATLAS_DB`` and connects at *import time*,
so both env vars are set before anything from ``atlas`` is imported. Tests run
against a throwaway temp database, never the real ``atlas.sqlite``.
"""
import os
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent

os.environ["ATLAS_BASE"] = str(PROJECT_ROOT)

# Guarded so a stray re-import can never repoint at a second temp dir.
if "ATLAS_DB" not in os.environ:
    _TMP_DIR = Path(tempfile.mkdtemp(prefix="atlas-tests-"))
    os.environ["ATLAS_DB"] = str(_TMP_DIR / "atlas-test.sqlite")

from starlette.testclient import TestClient  # noqa: E402

from atlas import db  # noqa: E402
from atlas.main import app  # noqa: E402

# Sanity: the app must be using the temp database, not the real one.
assert str(db.DB_PATH) == os.environ["ATLAS_DB"], db.DB_PATH


@pytest.fixture(autouse=True)
def fresh_db():
    with db.conn:
        db.conn.execute("DELETE FROM tasks")
        db.conn.execute("DELETE FROM columns")
        db.conn.execute("DELETE FROM repos")
        db.conn.execute("DELETE FROM projects")
        db.conn.execute("DELETE FROM meta")
    yield


@pytest.fixture
def client():
    return TestClient(app)


def add_repo(full_name: str, project_id: int | None = None, **overrides) -> None:
    """Insert a repo row directly (sync-shaped defaults)."""
    owner, name = full_name.split("/")
    row = {
        "full_name": full_name,
        "project_id": project_id,
        "name": name,
        "owner": owner,
        "description": overrides.get("description", ""),
        "language": overrides.get("language"),
        "pushed_at": overrides.get("pushed_at", "2026-07-01T00:00:00Z"),
        "url": f"https://github.com/{full_name}",
        "archived": overrides.get("archived", 0),
        "synced_at": "2026-07-21T00:00:00Z",
    }
    with db.conn:
        db.conn.execute(
            "INSERT INTO repos (full_name, project_id, name, owner, description,"
            " language, pushed_at, url, archived, synced_at)"
            " VALUES (:full_name, :project_id, :name, :owner, :description,"
            " :language, :pushed_at, :url, :archived, :synced_at)",
            row,
        )

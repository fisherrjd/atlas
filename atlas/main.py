import asyncio
import json
import logging
import os
import re
import urllib.error
import urllib.request
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db, sync

BASE_DIR = Path(os.environ.get("ATLAS_BASE", Path.cwd()))
DIST = BASE_DIR / "frontend" / "dist"
BACKUP_DIR = Path(os.environ.get("ATLAS_BACKUP_DIR", db.BASE_DIR / "backups"))

log = logging.getLogger("atlas")

scheduler = AsyncIOScheduler()


async def _scheduled_sync() -> None:
    try:
        fetched = await asyncio.to_thread(sync.fetch_repos)
        result = sync.apply(fetched)
        log.info("autosync: %s", result)
    except sync.SyncError as e:
        log.warning("autosync failed: %s", e.detail)


async def _scheduled_backup() -> None:
    stamp = datetime.now().strftime("%Y%m%d")
    target = await asyncio.to_thread(db.backup, BACKUP_DIR, stamp)
    log.info("backup: %s", target)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # hourly repo sync + nightly db backup; disable with ATLAS_AUTOSYNC=0
    if os.environ.get("ATLAS_AUTOSYNC", "1") != "0":
        scheduler.add_job(_scheduled_sync, "interval", hours=1)
        scheduler.add_job(_scheduled_backup, "cron", hour=3, minute=15)
        scheduler.start()
    yield
    if scheduler.running:
        scheduler.shutdown()


app = FastAPI(title="Atlas", lifespan=lifespan)

# Serve built frontend assets; absent during dev/tests — skip gracefully.
if (DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


# ── Request models ────────────────────────────────────────────────────────────

class CreateProjectReq(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    status: str = "idea"
    repos: list[str] = []


class UpdateProjectReq(BaseModel):
    name: str | None = None
    description: str | None = None
    notes: str | None = None


class StatusReq(BaseModel):
    status: str


class AssignRepoReq(BaseModel):
    full_name: str


class NameReq(BaseModel):
    name: str = Field(min_length=1)


class UpdateColumnReq(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    is_done: bool | None = None


class MoveColumnReq(BaseModel):
    index: int = Field(ge=0)


class CreateTaskReq(BaseModel):
    title: str = Field(min_length=1)
    description: str = ""
    source: str = ""
    agent: str = ""


class UpdateTaskReq(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    description: str | None = None
    agent: str | None = None  # "" unassigns


class MoveTaskReq(BaseModel):
    column_id: int
    index: int = Field(ge=0)


class CreateCommentReq(BaseModel):
    author: str = Field(min_length=1)
    body: str = Field(min_length=1)


def _check_status(status: str) -> None:
    if status not in db.PROJECT_STATUSES:
        raise HTTPException(
            422, detail=f"invalid status {status!r}; allowed: {', '.join(db.PROJECT_STATUSES)}"
        )


# ── Health / board ────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/api/board")
async def get_board(include_archived: bool = False) -> dict:
    return db.board(include_archived=include_archived)


@app.get("/api/now")
async def get_now() -> list[dict]:
    return db.now_view()


# ── Projects ─────────────────────────────────────────────────────────────────

@app.post("/api/projects", status_code=201)
async def create_project(req: CreateProjectReq) -> dict:
    _check_status(req.status)
    try:
        return db.create_project(req.name, req.description, req.status, req.repos)
    except KeyError as e:
        raise HTTPException(404, detail=f"unknown repo {e.args[0]!r}")


@app.get("/api/projects/{project_id}")
async def get_project(project_id: int) -> dict:
    project = db.get_project(project_id)
    if project is None:
        raise HTTPException(404, detail="project not found")
    return project


@app.patch("/api/projects/{project_id}")
async def update_project(project_id: int, req: UpdateProjectReq) -> dict:
    fields = {k: v for k, v in req.model_dump().items() if v is not None}
    project = db.update_project(project_id, fields)
    if project is None:
        raise HTTPException(404, detail="project not found")
    return project


@app.patch("/api/projects/{project_id}/status")
async def set_project_status(project_id: int, req: StatusReq) -> dict:
    _check_status(req.status)
    project = db.set_project_status(project_id, req.status)
    if project is None:
        raise HTTPException(404, detail="project not found")
    return project


class ArchiveReq(BaseModel):
    archived: bool
    github: bool = False  # opt-in: also archive/unarchive the repos on GitHub


@app.patch("/api/projects/{project_id}/archive")
async def archive_project(project_id: int, req: ArchiveReq) -> dict:
    project = db.get_project(project_id)
    if project is None:
        raise HTTPException(404, detail="project not found")
    if req.github:
        failures = []
        for repo in project["repos"]:
            if bool(repo["archived"]) == req.archived:
                continue
            try:
                await asyncio.to_thread(sync.set_repo_archived, repo["full_name"], req.archived)
                db.set_repo_archived_flag(repo["full_name"], req.archived)
            except sync.SyncError as e:
                failures.append(f"{repo['full_name']}: {e.detail}")
        if failures:
            raise HTTPException(502, detail="; ".join(failures[:3]))
    return db.set_archived(project_id, req.archived)


@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: int) -> dict:
    if not db.delete_project(project_id):
        raise HTTPException(404, detail="project not found")
    return {"detail": "deleted"}


# ── Columns ──────────────────────────────────────────────────────────────────

@app.post("/api/projects/{project_id}/columns", status_code=201)
async def create_column(project_id: int, req: NameReq) -> dict:
    if db.get_project(project_id) is None:
        raise HTTPException(404, detail="project not found")
    return db.create_column(project_id, req.name)


@app.patch("/api/columns/{column_id}")
async def update_column(column_id: int, req: UpdateColumnReq) -> dict:
    column = db.update_column(column_id, name=req.name, is_done=req.is_done)
    if column is None:
        raise HTTPException(404, detail="column not found")
    return column


@app.patch("/api/columns/{column_id}/move")
async def move_column(column_id: int, req: MoveColumnReq) -> dict:
    column = db.move_column(column_id, req.index)
    if column is None:
        raise HTTPException(404, detail="column not found")
    return column


@app.delete("/api/columns/{column_id}")
async def delete_column(column_id: int) -> dict:
    try:
        if not db.delete_column(column_id):
            raise HTTPException(404, detail="column not found")
    except db.ColumnNotDeletable as e:
        raise HTTPException(400, detail=e.detail)
    return {"detail": "deleted"}


# ── Repos ────────────────────────────────────────────────────────────────────

@app.get("/api/repos")
async def list_repos(unassigned: bool = False, archived: bool = False) -> list[dict]:
    return db.list_repos(unassigned=unassigned, archived=archived)


@app.post("/api/projects/{project_id}/repos")
async def assign_repo(project_id: int, req: AssignRepoReq) -> dict:
    if db.get_project(project_id) is None:
        raise HTTPException(404, detail="project not found")
    try:
        db.assign_repo(project_id, req.full_name)
    except KeyError:
        raise HTTPException(404, detail=f"unknown repo {req.full_name!r}")
    return db.get_project(project_id)


@app.delete("/api/projects/{project_id}/repos/{full_name:path}")
async def unassign_repo(project_id: int, full_name: str) -> dict:
    if not db.unassign_repo(project_id, full_name):
        raise HTTPException(404, detail="repo not linked to this project")
    return {"detail": "unassigned"}


# ── Tasks ────────────────────────────────────────────────────────────────────

@app.post("/api/columns/{column_id}/tasks", status_code=201)
async def create_task(column_id: int, req: CreateTaskReq) -> dict:
    task = db.create_task(column_id, req.title, req.description, req.source, req.agent)
    if task is None:
        raise HTTPException(404, detail="column not found")
    return task


@app.patch("/api/tasks/{task_id}")
async def update_task(task_id: int, req: UpdateTaskReq) -> dict:
    fields = {k: v for k, v in req.model_dump().items() if v is not None}
    task = db.update_task(task_id, fields)
    if task is None:
        raise HTTPException(404, detail="task not found")
    return task


@app.patch("/api/tasks/{task_id}/move")
async def move_task(task_id: int, req: MoveTaskReq) -> dict:
    try:
        moved = db.move_task(task_id, req.column_id, req.index)
    except db.CrossProjectMove:
        raise HTTPException(400, detail="cannot move a task to another project's column")
    if moved is None:
        raise HTTPException(404, detail="task or column not found")
    return moved


@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: int) -> dict:
    if not db.delete_task(task_id):
        raise HTTPException(404, detail="task not found")
    return {"detail": "deleted"}


@app.get("/api/tasks/{task_id}/comments")
async def list_comments(task_id: int) -> list[dict]:
    comments = db.list_comments(task_id)
    if comments is None:
        raise HTTPException(404, detail="task not found")
    return comments


@app.post("/api/tasks/{task_id}/comments", status_code=201)
async def create_comment(task_id: int, req: CreateCommentReq) -> dict:
    comment = db.add_comment(task_id, req.author, req.body)
    if comment is None:
        raise HTTPException(404, detail="task not found")
    return comment


# ── Heimdall (proxy to the orchestrator's display/editor API) ────────────────
#
# The orchestrator runs on the host; pods reach it via the flannel gateway
# (10.42.0.1), same pattern as postgres. GETs are an open allowlist; persona
# writes forward with a shared bearer token (ORC_API_TOKEN) that never reaches
# the browser — atlas's own auth gates who can call them.

ORC_API = os.environ.get("ORC_API", "http://10.42.0.1:3050")
ORC_API_TOKEN = os.environ.get("ORC_API_TOKEN", "")
_HEIMDALL_ROUTES = {"health", "pulses", "tickets", "suppressions", "personas", "avatars"}
_HEIMDALL_NAME = re.compile(r"^[a-z0-9-]+$")


_HEIMDALL_ASSETS = {"avatars": "image/png", "sounds": "audio/wav"}
_HEIMDALL_ASSET_NAME = re.compile(r"^[a-z0-9-]+\.(png|wav)$")


@app.get("/api/heimdall/{route}")
async def heimdall(route: str, limit: int = 50):
    if route not in _HEIMDALL_ROUTES:
        raise HTTPException(404, detail="unknown heimdall route")

    def fetch():
        with urllib.request.urlopen(f"{ORC_API}/api/{route}?limit={limit}", timeout=5) as r:
            return json.loads(r.read())

    try:
        return await asyncio.to_thread(fetch)
    except (urllib.error.URLError, TimeoutError) as e:
        raise HTTPException(502, detail=f"heimdall api unreachable: {e}")


@app.get("/api/heimdall/{kind}/{filename}")
async def heimdall_asset(kind: str, filename: str):
    # persona avatars / event chimes, streamed from the orchestrator's asset
    # library — same GET-only posture, orc validates the basename again upstream
    if kind == "agent-jobs" and _HEIMDALL_NAME.match(filename):

        def fetch_job():
            with urllib.request.urlopen(
                f"{ORC_API}/api/agent-jobs/{filename}", timeout=5
            ) as r:
                return json.loads(r.read())

        try:
            return await asyncio.to_thread(fetch_job)
        except urllib.error.HTTPError as e:
            raise HTTPException(e.code, detail="unknown job")
        except (urllib.error.URLError, TimeoutError) as e:
            raise HTTPException(502, detail=f"heimdall api unreachable: {e}")
    if kind not in _HEIMDALL_ASSETS or not _HEIMDALL_ASSET_NAME.match(filename):
        raise HTTPException(404, detail="unknown heimdall asset")

    def fetch():
        with urllib.request.urlopen(f"{ORC_API}/api/{kind}/{filename}", timeout=5) as r:
            return r.read()

    try:
        data = await asyncio.to_thread(fetch)
    except urllib.error.HTTPError as e:
        raise HTTPException(e.code, detail="asset not found")
    except (urllib.error.URLError, TimeoutError) as e:
        raise HTTPException(502, detail=f"heimdall api unreachable: {e}")
    return Response(
        content=data,
        media_type=_HEIMDALL_ASSETS[kind],
        headers={"Cache-Control": "max-age=86400"},
    )


def _heimdall_post(path: str, payload: dict):
    req = urllib.request.Request(
        f"{ORC_API}/api/{path}",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {ORC_API_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


async def _heimdall_write(path: str, payload: dict):
    if not ORC_API_TOKEN:
        raise HTTPException(503, detail="ORC_API_TOKEN not configured")
    try:
        return await asyncio.to_thread(_heimdall_post, path, payload)
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read()).get("detail", "write refused")
        except Exception:
            detail = "write refused"
        raise HTTPException(e.code, detail=detail)
    except (urllib.error.URLError, TimeoutError) as e:
        raise HTTPException(502, detail=f"heimdall api unreachable: {e}")


@app.post("/api/heimdall/personas")
async def heimdall_create_persona(payload: dict):
    return await _heimdall_write("personas", payload)


@app.post("/api/heimdall/personas/{name}")
async def heimdall_edit_persona(name: str, payload: dict):
    if not _HEIMDALL_NAME.match(name):
        raise HTTPException(404, detail="bad persona name")
    return await _heimdall_write(f"personas/{name}", payload)


# ── Sync ─────────────────────────────────────────────────────────────────────

@app.post("/api/sync")
async def run_sync() -> dict:
    try:
        fetched = await asyncio.to_thread(sync.fetch_repos)
    except sync.SyncError as e:
        raise HTTPException(e.status_code, detail=e.detail)
    return sync.apply(fetched)


# ── SPA catch-all (registered last) ──────────────────────────────────────────

@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    index = DIST / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse({"detail": "Frontend not built"}, status_code=404)

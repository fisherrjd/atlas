import asyncio
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db, sync

BASE_DIR = Path(os.environ.get("ATLAS_BASE", Path.cwd()))
DIST = BASE_DIR / "frontend" / "dist"

app = FastAPI(title="Atlas")

# Serve built frontend assets; absent during dev/tests — skip gracefully.
if (DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


# ── Request models ────────────────────────────────────────────────────────────

ProjectStatus = str
TaskStatus = str


class CreateProjectReq(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    status: str = "idea"
    repos: list[str] = []


class UpdateProjectReq(BaseModel):
    name: str | None = None
    description: str | None = None
    notes: str | None = None


class MoveReq(BaseModel):
    status: str
    index: int = Field(ge=0)


class AssignRepoReq(BaseModel):
    full_name: str


class CreateTaskReq(BaseModel):
    title: str = Field(min_length=1)


class UpdateTaskReq(BaseModel):
    title: str = Field(min_length=1)


def _check_status(status: str, allowed: tuple[str, ...]) -> None:
    if status not in allowed:
        raise HTTPException(422, detail=f"invalid status {status!r}; allowed: {', '.join(allowed)}")


# ── Health / board ────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/api/board")
async def get_board() -> dict:
    return db.board()


# ── Projects ─────────────────────────────────────────────────────────────────

@app.post("/api/projects", status_code=201)
async def create_project(req: CreateProjectReq) -> dict:
    _check_status(req.status, db.PROJECT_STATUSES)
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


@app.patch("/api/projects/{project_id}/move")
async def move_project(project_id: int, req: MoveReq) -> dict:
    _check_status(req.status, db.PROJECT_STATUSES)
    moved = db.move("projects", project_id, req.status, req.index)
    if moved is None:
        raise HTTPException(404, detail="project not found")
    return moved


@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: int) -> dict:
    if not db.delete_project(project_id):
        raise HTTPException(404, detail="project not found")
    return {"detail": "deleted"}


# ── Repos ────────────────────────────────────────────────────────────────────

@app.get("/api/repos")
async def list_repos(unassigned: bool = False) -> list[dict]:
    return db.list_repos(unassigned=unassigned)


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

@app.post("/api/projects/{project_id}/tasks", status_code=201)
async def create_task(project_id: int, req: CreateTaskReq) -> dict:
    if db.get_project(project_id) is None:
        raise HTTPException(404, detail="project not found")
    return db.create_task(project_id, req.title)


@app.patch("/api/tasks/{task_id}")
async def update_task(task_id: int, req: UpdateTaskReq) -> dict:
    task = db.update_task(task_id, req.title)
    if task is None:
        raise HTTPException(404, detail="task not found")
    return task


@app.patch("/api/tasks/{task_id}/move")
async def move_task(task_id: int, req: MoveReq) -> dict:
    _check_status(req.status, db.TASK_STATUSES)
    moved = db.move("tasks", task_id, req.status, req.index)
    if moved is None:
        raise HTTPException(404, detail="task not found")
    return moved


@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: int) -> dict:
    if not db.delete_task(task_id):
        raise HTTPException(404, detail="task not found")
    return {"detail": "deleted"}


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

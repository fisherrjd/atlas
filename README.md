# atlas

Personal project tracker: a kanban board of all my side projects, synced from
GitHub, with per-project task boards and notes. Single-user, runs on the
tailnet, SQLite on disk.

**Stack:** FastAPI + uv (Python 3.13) · SQLite (stdlib, WAL) · Vue 3 + Vite +
Tailwind v4 + shadcn-vue (from [app-template](https://github.com/fisherrjd/app-template)) ·
vuedraggable · nix devshell

## Ports

| what | port |
| --- | --- |
| backend (serves the SPA in prod) | **3040** |
| vite dev server (proxies `/api` → 3040) | **3041** |

Both bind `0.0.0.0`, so `eldo:3040` / `eldo:3041` over the tailnet.

## Run it

```sh
direnv allow   # nix devshell: uv env + bun + scripts
dev            # backend :3040 + frontend :3041 together
```

Other scripts: `api` / `web` (each side alone), `build` (SPA → `frontend/dist`),
`serve` (prod mode: backend serving the built SPA on :3040), `check`
(typecheck + pytest), `sync-now` (curl the sync endpoint).

## How it works

The hierarchy: **projects** (grid on the main page) → each project's **own
kanban** (custom columns) → **tasks**.

- **Projects** (`/`): a searchable grid of every project, filterable by status
  (Idea / Backlog / Active / Paused / Done — change it from the badge on each
  card). A project groups **one or more GitHub repos** (e.g. `osrs-ge` holds
  the five `ge-*` repos) or none at all (pure ideas). Sorted by most recent
  push.
- **Project page** (`/p/:id`): repo chips linking to GitHub, freeform notes
  with autosave, and the project's own kanban — starts as Todo / Doing / Done,
  but columns can be added, renamed, reordered (drag the grip), and deleted
  (only when empty; a column flagged ✓ counts its tasks as "done" for the
  card's progress badge).
- **Sync** (header button, or `POST /api/sync`): runs `gh repo list` for
  `fisherrjd` + `OldSchool-Market-Research` (needs an authed `gh` on the
  server's PATH) and upserts repo metadata. **Sync never touches your kanban:**
  status, ordering, grouping, tasks, and notes are user state; sync only
  refreshes repo rows. New repos auto-create a card in **Idea**; archived
  repos are flagged, never deleted.
- **Column = intent, dot = reality.** Each card shows a freshness dot derived
  from the repos' last push (green <30d, amber <90d, grey dormant), plus a
  hint icon when they disagree — dormant project sitting in Active, or a
  fresh one parked in Idea/Paused.
- **Husk rule:** moving a repo out of an untouched auto-created card (no other
  repos, no tasks, no notes, still named after the repo) deletes that husk, so
  grouping repos into a real project leaves no litter. Anything you've
  renamed, noted, or tasked is never auto-deleted.

## Data

SQLite at `./atlas.sqlite` (override with `ATLAS_DB`; a future deploy mounts
`/data/atlas.sqlite`). Migrations are by hand — this state is cheap: worst
case, delete the file, resync, and redo your columns.

Seeding the repo groups (the UI's "New project" dialog does the same):

```sh
curl -X POST localhost:3040/api/projects -H 'Content-Type: application/json' \
  -d '{"name":"osrs-ge","status":"active","repos":["OldSchool-Market-Research/ge-data", "..."]}'
```

## Out of v1

Auth (tailnet-only by deployment), websockets/live updates, markdown rendering
in notes, Docker/CI/hex deploy (chore-tracker's pattern ports over directly),
a `missing` flag for repos deleted on GitHub, owner list as env var.

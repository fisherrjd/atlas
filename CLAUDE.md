# atlas — architecture notes

Personal project tracker (kanban of projects synced from GitHub). Single-user,
no auth, deployed nowhere yet (tailnet host runs it directly).

## Shape

Mirrors chore-tracker: root `main.py` launcher → uvicorn `atlas.main:app` on
**:3040** (reload in dev); flat package `atlas/` (`main.py` routes, `db.py`
persistence, `sync.py` GitHub); `frontend/` is a Vue 3 SPA from app-template,
vite dev on **:3041** proxying `/api` → 3040. In prod the backend serves
`frontend/dist` same-origin (StaticFiles `/assets` mount + SPA catch-all
registered last) — no CORS anywhere, keep it that way.

## Conventions / gotchas

- `atlas/db.py` reads `ATLAS_BASE` / `ATLAS_DB` and connects **at import
  time**. Tests must set env vars before importing anything from `atlas`
  (see `tests/conftest.py`). One module-level connection; all routes are
  async on one event loop, so access is serialized. Writes go through
  `with conn:` transactions.
- **The sync invariant:** `sync.apply()` upserts `repos` metadata columns
  only — it never writes `repos.project_id` and never touches `projects` or
  `tasks`. Kanban status, ordering, grouping, notes, tasks are user state.
  Any future sync feature must preserve this.
- **Husk rule** (`db._maybe_delete_husk`): when a repo is reassigned away,
  its old project is deleted only if it has no repos, no tasks, empty notes,
  AND still carries the repo's name (i.e. an untouched sync-auto-created
  card). Don't loosen these guards.
- Move/reorder: `db.move(table, id, status, index)` rewrites `sort_order`
  0..n for both affected columns in one transaction. Tasks are scoped per
  project; projects are global per column.
- Sync uses the `gh` CLI via subprocess (authed on the host) — not the REST
  API. Owners list is `sync.OWNERS`.
- Migrations: none. `CREATE TABLE IF NOT EXISTS` at import; schema changes are
  hand-run `ALTER TABLE` (or delete `atlas.sqlite` and resync — state is cheap).
- Frontend inherits app-template conventions: HSL triplet tokens (don't let
  the shadcn CLI rewrite `src/assets/index.css`), icons from `@lucide/vue`,
  theme presets in `src/assets/themes/`. Drag-and-drop is `vuedraggable`
  (`:list` mode — it mutates the arrays in place; that IS the optimistic
  update, the `@change` handler just PATCHes and refetches on error).
- `tsconfig` has `erasableSyntaxOnly` — no TS constructor parameter
  properties / enums.

## Dev

`direnv allow`, then `dev` (both servers), `check` (vue-tsc + pytest),
`build` + `serve` (prod mode on :3040). Tests: `pytest` — API tests
monkeypatch `sync.fetch_repos`, nothing hits the network.

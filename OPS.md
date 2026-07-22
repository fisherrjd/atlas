# atlas — ops

## Release flow

Version lives in `pyproject.toml` (single source of truth).

- push any branch → CI publishes `ghcr.io/fisherrjd/atlas:X.Y.Z-b<sha>` (pre-release)
- merge/push to `main` → publishes `:X.Y.Z`, tags `vX.Y.Z`, auto-bumps patch

## Deploy (k3s via hex)

Spec: `~/github/jade/ops/svc/atlas.nix`, registered in `specs.nix`.

- **Image:** `ghcr.io/fisherrjd/atlas:<pinned tag>` (bump the pin to release)
- **Port:** 3040, LoadBalancer `10.0.0.71`
- **Data:** hostPath `/var/lib/atlas` → `/data` (`ATLAS_DB=/data/atlas.sqlite`,
  `ATLAS_BACKUP_DIR=/data/backups`). Nightly backup at 03:15 keeps 14 copies.
- **Sync auth:** the pod mounts eldo's `/home/jade/.config/gh` read-only at
  `/gh-config` with `GH_CONFIG_DIR=/gh-config` — the container shells out to
  `gh` using the host's existing auth. Token never leaves eldo. The container
  runs as uid 1001 (= jade on eldo) so it can read the config and write
  `/var/lib/atlas`. If gh auth is ever re-scoped, `GH_TOKEN` as an env/secret
  works too.
- **Auto-sync:** hourly, in-process (APScheduler). `ATLAS_AUTOSYNC=0` disables.
- **Singleton:** replicas 1 (SQLite + in-process scheduler); keep it that way.

```sh
cd ~/github/jade/ops
hex --dryrun -t specs.nix   # preview
hex -t specs.nix            # apply
kubectl get pods -l app=atlas
```

Host prep (one-time, already done): `/var/lib/atlas` exists, owned by uid 1001.

## Access

- LAN / tailnet subnet: `http://10.0.0.71:3040`
- Optional public: add a Caddy virtualHost on bifrost → eldo tailnet IP:3040
  (not configured; do this only when wanted).

# TrueNAS deployment

Use one stable deployment directory (replace the example pool name below).
The default state directory is the checkout's parent; use `--state-dir` to override it. The date in an old folder name is not
an application version; `release.json` and the image revision identify production.

```text
/mnt/pool/apps/fetchshelf/
  repo/          this Git checkout
  .env           production configuration, mode 0600
  release.json   deployed commit, image ID, paths, rollback reference
  backups/       latest two verified settings/configuration backups
```

Media, settings, and the identity key remain at their existing absolute paths.
Set these paths in your private `.env`. The application root stays `/mnt/data`.
Keep the existing API token and identity key unchanged. Copy `env.example`
to the deployment directory and supply the existing values; never commit it.

## Build and update

Run on the NAS with Docker access, from a clean, committed checkout:

```bash
cd /mnt/pool/apps/fetchshelf/repo
git pull --ff-only
sudo python3 deploy/truenas/deploy.py --build-only
# Pause active collection tasks in the WebUI and wait for the queue to drain.
sudo python3 deploy/truenas/deploy.py --image fetchshelf-local:git-COMMIT_PREFIX
```

Use the 12-character prefix printed by the build. The deployer verifies the
image's full revision against the checkout. It refuses to change existing
settings, media, or identity-key mounts, and refuses active/pending tasks.
It stops the app gracefully, backs up settings while writes are stopped,
starts the replacement, checks Docker health and authenticated API access,
then records the release. A failed replacement restores the prior image.
The two media aliases share one bind mount so replacements do not accumulate
anonymous download volumes.

For initial migration from a different Compose project,
add `--adopt-existing` after preparing the stable `.env`. The old container
is stopped before removal, and no second writer starts against the same data.
The previous Compose file, environment, settings, and key are saved together.

Build mirrors can be selected explicitly with `--build-arg NODE_IMAGE=...`,
`PYTHON_BUILD_IMAGE=...`, `PYTHON_RUNTIME_IMAGE=...`, and `UV_IMAGE=...`. The default Dockerfile
builds from the locked Python/Node dependencies and tracked vendor snapshot;
it never requires a dated local FetchShelf image.

If the NAS uses a loopback HTTP proxy for downloads, add `--build-network host`
and `--build-arg http_proxy=http://127.0.0.1:7890`
`--build-arg https_proxy=http://127.0.0.1:7890`. These are build-only options;
they do not change the application's network or proxy configuration.

## Status and rollback

```bash
cat /mnt/pool/apps/fetchshelf/release.json
docker inspect fetchshelf --format '{{.State.Health.Status}} {{.Image}}'
```

The release record points to a rollback backup. Its `backup.json` records
the previous image and Compose project. Use that backup's `environment` and
`compose.yaml` with the recorded project and previous image to roll back.
Pause tasks first. If project names differ, stop and remove the replacement
container before creating the old one. Settings restoration from
`settings.tar.gz` is a separate deliberate recovery action with the service
stopped; it can discard new task history. Never restore the old key alone.

Backups contain credentials and have private permissions. The deployer keeps
the newest two complete backups it created, leaves unrelated directories
alone, and never deletes media, ZFS snapshots, Docker volumes, or images.
Keep the current and previous Docker images until rollback is no longer needed.
Do not save another full image tarball on every update.

## Tests

`uv sync --frozen` and `uv run pytest` run FetchShelf's own offline contracts.
`vendor/TikTok-Api/tests` is preserved upstream material and is not the
application's default test suite; it needs its own browser/network environment
and contains mocks from before the recovered local integration changes.

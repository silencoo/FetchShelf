#!/usr/bin/env python3
"""Deploy a clean FetchShelf checkout to one stable TrueNAS location."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
from datetime import datetime, timezone

REPO = Path(__file__).resolve().parents[2]
PROJECT = "fetchshelf"
CONTAINER = "fetchshelf"
PRODUCT = "FetchShelf"
BUSY_PROBE = """import json,os,urllib.request
r=urllib.request.Request("http://127.0.0.1:5555/ui/api/tasks?limit=1",headers={"token":os.environ["FETCHSHELF_API_TOKEN"]})
with urllib.request.urlopen(r,timeout=60) as f:
 d=json.load(f)
print(json.dumps({k:d.get(k,0) for k in ("running","pending","paused")}))"""


def run(*args, capture=False, env=None):
    result = subprocess.run(
        [str(a) for a in args], check=True, text=True,
        stdout=subprocess.PIPE if capture else None, env=env,
    )
    return result.stdout.strip() if capture else ""


def inspect_container():
    result = subprocess.run(
        ["docker", "container", "inspect", CONTAINER],
        text=True, capture_output=True,
    )
    if result.returncode:
        if "No such" in result.stderr:
            return None
        raise RuntimeError(result.stderr.strip())
    return json.loads(result.stdout)[0]


def atomic_json(path, data):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, indent=2) + "\n")
    temp.replace(path)


def prune_backups(root, keep=2):
    """Only prune verified backups created here; never follow symlinks."""
    if keep < 1:
        raise ValueError("Keep at least one rollback backup")
    entries = []
    for path in root.iterdir():
        if path.is_symlink() or not path.is_dir() or not path.name.startswith("release-"):
            continue
        marker = path / "backup.json"
        try:
            data = json.loads(marker.read_text())
        except (OSError, ValueError):
            continue
        if data.get("product") == PRODUCT and data.get("complete") is True:
            entries.append(path)
    for path in sorted(entries, reverse=True)[keep:]:
        shutil.rmtree(path)


def validate_mounts(config, existing):
    volumes = config["services"][CONTAINER]["volumes"]
    mounts = {v["target"]: v for v in volumes}
    for target in ("/app/settings", "/mnt/data", "/app/downloads"):
        item = mounts[target]
        source = Path(item["source"])
        if item["type"] != "bind" or not source.is_absolute() or not source.is_dir():
            raise ValueError(f"Existing absolute bind directory required for {target}")
        if source == Path("/"):
            raise ValueError("Refusing a filesystem-root bind")
    if mounts["/app/downloads"]["source"] != mounts["/mnt/data"]["source"]:
        raise ValueError("The two media paths must point at the same data directory")
    key = Path(config["secrets"]["fetchshelf_identity_key"]["file"])
    if not key.is_absolute() or not key.is_file():
        raise ValueError("Existing absolute identity-key file required")
    if existing:
        old = {m["Destination"]: m["Source"] for m in existing["Mounts"]}
        for target in ("/app/settings", "/mnt/data"):
            if Path(old.get(target, "")).resolve() != Path(mounts[target]["source"]).resolve():
                raise ValueError(f"Refusing to change production data mount {target}")
        if Path(old.get("/run/secrets/fetchshelf_identity_key", "")).resolve() != key.resolve():
            raise ValueError("Refusing to change the production identity key")
    return Path(mounts["/app/settings"]["source"]), key


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, default=REPO.parent)
    parser.add_argument("--image", help="Use an already built image labeled with this Git commit")
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--adopt-existing", action="store_true", help="One-time migration from the old Compose project")
    parser.add_argument("--build-arg", action="append", default=[])
    parser.add_argument("--build-network", choices=("default", "host", "none"), default="default")
    args = parser.parse_args()
    os.umask(0o077)
    state = args.state_dir.resolve()
    state.mkdir(parents=True, exist_ok=True)
    with (state / "deploy.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        deploy(args, state)


def deploy(args, state):
    git = ["git", "--no-optional-locks", "-c", f"safe.directory={REPO}", "-C", REPO]
    revision = run(*git, "rev-parse", "HEAD", capture=True)
    if run(*git, "status", "--porcelain", "--untracked-files=normal", capture=True):
        raise RuntimeError("Commit all source changes before deployment")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    image = args.image or f"fetchshelf-local:git-{revision[:12]}"
    if not args.image:
        command = ["docker", "build", "--network", args.build_network, "--build-arg", f"VCS_REF={revision}",
                   "--build-arg", f"BUILD_DATE={datetime.now(timezone.utc).isoformat()}"]
        for value in args.build_arg:
            command += ["--build-arg", value]
        run(*command, "-t", image, REPO)
    image_info = json.loads(run("docker", "image", "inspect", image, capture=True))[0]
    if image_info["Config"].get("Labels", {}).get("org.opencontainers.image.revision") != revision:
        raise RuntimeError("Image revision does not match the checked-out source")
    if args.build_only:
        print(json.dumps({"revision": revision, "image": image, "image_id": image_info["Id"]}))
        return
    env_file = state / ".env"
    if not env_file.is_file() or env_file.stat().st_mode & 0o077:
        raise RuntimeError("Create the deployment .env with mode 0600 before deploying")
    env = {**os.environ, "FETCHSHELF_IMAGE": image}
    compose_file = REPO / "deploy/truenas/compose.yaml"
    compose = ["docker", "compose", "--project-name", PROJECT, "--env-file", str(env_file), "-f", str(compose_file)]
    config = json.loads(run(*compose, "config", "--format", "json", capture=True, env=env))
    existing = inspect_container()
    settings, key = validate_mounts(config, existing)
    prior_project = PROJECT
    prior_compose = compose_file
    if existing:
        labels = existing["Config"].get("Labels", {})
        prior_project = labels.get("com.docker.compose.project", "")
        if prior_project != PROJECT and not args.adopt_existing:
            raise RuntimeError("Existing container belongs to another project; use --adopt-existing once")
        configured_files = labels.get("com.docker.compose.project.config_files", "")
        if not prior_project or "," in configured_files or not Path(configured_files).is_file():
            raise RuntimeError("Cannot establish the previous Compose file for rollback")
        prior_compose = Path(configured_files)
        if existing["State"]["Running"]:
            tasks = json.loads(run("docker", "exec", CONTAINER, "python", "-c", BUSY_PROBE, capture=True))
            if tasks["running"] or tasks["pending"]:
                raise RuntimeError("Pause running collection tasks and wait for an empty pending queue before deploying")
    backups = state / "backups"
    backups.mkdir(mode=0o700, exist_ok=True)
    backup = backups / f"release-{stamp}-{revision[:12]}"
    backup.mkdir(mode=0o700)
    shutil.copyfile(env_file, backup / "environment")
    shutil.copyfile(key, backup / "identity.key")
    shutil.copyfile(prior_compose, backup / "compose.yaml")
    previous_image = existing["Config"]["Image"] if existing else None
    previous = {"product": PRODUCT, "complete": False, "image": previous_image,
                "image_id": existing["Image"] if existing else None,
                "project": prior_project, "created_at": stamp}
    atomic_json(backup / "backup.json", previous)
    if (state / "release.json").is_file():
        shutil.copyfile(state / "release.json", backup / "previous-release.json")
    stopped = False
    try:
        if existing and existing["State"]["Running"]:
            run("docker", "stop", "--time", "120", CONTAINER)
            stopped = True
        with tarfile.open(backup / "settings.tar.gz", "w:gz") as archive:
            archive.add(settings, arcname="settings")
        with tarfile.open(backup / "settings.tar.gz") as archive:
            archive.getmembers()
        previous["complete"] = True
        atomic_json(backup / "backup.json", previous)
        if existing and prior_project != PROJECT:
            run("docker", "rm", CONTAINER)
        run(*compose, "up", "-d", "--wait", "--wait-timeout", "180", env=env)
        current = inspect_container()
        if not current or current["Image"] != image_info["Id"] or current["State"].get("Health", {}).get("Status") != "healthy":
            raise RuntimeError("Deployment did not start the verified image")
        # Also check authenticated access; /docs alone does not verify tokens.
        json.loads(run("docker", "exec", CONTAINER, "python", "-c", BUSY_PROBE, capture=True))
        atomic_json(state / "release.json", {
            "product": PRODUCT, "revision": revision, "image": image,
            "image_id": image_info["Id"], "deployed_at": datetime.now(timezone.utc).isoformat(),
            "repository": "https://github.com/silencoo/FetchShelf",
            "compose": str(compose_file), "source": str(REPO), "project": PROJECT,
            "settings": str(settings), "media": next(v["source"] for v in config["services"][CONTAINER]["volumes"] if v["target"] == "/mnt/data"),
            "rollback_backup": str(backup), "previous_image": previous_image,
        })
    except BaseException:
        if existing and stopped:
            new = inspect_container()
            if new and new["Config"].get("Labels", {}).get("com.docker.compose.project") != prior_project:
                run("docker", "rm", "-f", CONTAINER)
            rollback_env = {**os.environ, "FETCHSHELF_IMAGE": previous_image}
            run("docker", "compose", "--project-name", prior_project,
                "--env-file", backup / "environment", "-f", backup / "compose.yaml",
                "up", "-d", "--wait", "--wait-timeout", "180", env=rollback_env)
            print("Deployment failed; previous image restored. Settings backup retained.")
        raise
    # Housekeeping failures must not roll back an already healthy deployment.
    try:
        prune_backups(backups, keep=2)
    except OSError as error:
        print(f"Deployment healthy; backup cleanup needs attention: {error}")
    print(json.dumps({"healthy": True, "revision": revision, "image": image, "backup": str(backup)}))


if __name__ == "__main__":
    main()

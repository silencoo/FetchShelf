import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location("nas_deploy", Path(__file__).parents[1] / "deploy/truenas/deploy.py")
nas = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nas)


def fixture_config(tmp_path):
    settings = tmp_path / "settings"
    media = tmp_path / "media"
    key = tmp_path / "identity.key"
    settings.mkdir()
    media.mkdir()
    key.write_text("test-key")
    (settings / "record.txt").write_text("preserve this")
    volumes = [{"type": "bind", "source": str(source), "target": target}
               for source, target in [(settings, "/app/settings"), (media, "/mnt/data"), (media, "/app/downloads")]]
    config = {"services": {"fetchshelf": {"volumes": volumes}}, "secrets": {"fetchshelf_identity_key": {"file": str(key)}}}
    mounts = [{"Source": str(source), "Destination": target}
              for source, target in [(settings, "/app/settings"), (media, "/mnt/data"), (key, "/run/secrets/fetchshelf_identity_key")]]
    return config, mounts


def test_existing_data_mounts_cannot_be_changed(tmp_path):
    config, mounts = fixture_config(tmp_path)
    nas.validate_mounts(config, {"Mounts": mounts})
    replacement = tmp_path / "empty-new-media"
    replacement.mkdir()
    config["services"]["fetchshelf"]["volumes"][1]["source"] = str(replacement)
    config["services"]["fetchshelf"]["volumes"][2]["source"] = str(replacement)
    with pytest.raises(ValueError, match="production data mount"):
        nas.validate_mounts(config, {"Mounts": mounts})


def test_identity_key_cannot_be_replaced(tmp_path):
    config, mounts = fixture_config(tmp_path)
    replacement = tmp_path / "different.key"
    replacement.write_text("different-key")
    config["secrets"]["fetchshelf_identity_key"]["file"] = str(replacement)
    with pytest.raises(ValueError, match="identity key"):
        nas.validate_mounts(config, {"Mounts": mounts})


def test_pruning_keeps_two_and_never_follows_links_or_deletes_unmanaged_backups(tmp_path):
    backups = tmp_path / "backups"
    backups.mkdir()
    for i in range(4):
        p = backups / f"release-2026102{i}"
        p.mkdir()
        (p / "backup.json").write_text(json.dumps({"product": "FetchShelf", "complete": True}))
    unknown = backups / "release-unmanaged"
    unknown.mkdir()
    incomplete = backups / "release-incomplete"
    incomplete.mkdir()
    (incomplete / "backup.json").write_text(json.dumps({"product": "FetchShelf", "complete": False}))
    external = tmp_path / "external"
    external.mkdir()
    (external / "backup.json").write_text(json.dumps({"product": "FetchShelf", "complete": True}))
    (backups / "release-link").symlink_to(external, target_is_directory=True)
    nas.prune_backups(backups)
    assert sorted(p.name for p in backups.iterdir()) == [
        "release-20261022", "release-20261023", "release-incomplete", "release-link", "release-unmanaged"
    ]
    assert external.is_dir()


def test_failed_cutover_restores_previous_image_and_preserves_snapshot(tmp_path, monkeypatch):
    config, mounts = fixture_config(tmp_path)
    state = tmp_path / "state"
    state.mkdir()
    (state / ".env").write_text("FETCHSHELF_API_TOKEN=test-value\n")
    (state / ".env").chmod(0o600)
    compose_file = tmp_path / "prior-compose.yaml"
    compose_file.write_text("services: {}\n")
    existing = {"Mounts": mounts, "Image": "sha256:old", "State": {"Running": True},
                "Config": {"Image": "fetchshelf-local:previous", "Labels": {
                    "com.docker.compose.project": "fetchshelf",
                    "com.docker.compose.project.config_files": str(compose_file)}}}
    monkeypatch.setattr(nas, "inspect_container", lambda: existing)
    calls = []
    def fake_run(*command, capture=False, env=None):
        args = list(map(str, command))
        calls.append((args, env))
        if args[:3] == ["docker", "image", "inspect"]:
            return json.dumps([{"Id": "sha256:new", "Config": {"Labels": {"org.opencontainers.image.revision": "a" * 40}}}])
        if args[0] == "git":
            return "a" * 40 if "rev-parse" in args else ""
        if "config" in args:
            return json.dumps(config)
        if args[:2] == ["docker", "exec"]:
            return '{"running": 0, "pending": 0, "paused": 1}'
        if "up" in args and env["FETCHSHELF_IMAGE"] == "fetchshelf-local:new":
            raise subprocess.CalledProcessError(1, args)
        return ""
    monkeypatch.setattr(nas, "run", fake_run)
    args = SimpleNamespace(image="fetchshelf-local:new", build_only=False, adopt_existing=False, build_arg=[])
    with pytest.raises(subprocess.CalledProcessError):
        nas.deploy(args, state)
    ups = [(cmd, env["FETCHSHELF_IMAGE"]) for cmd, env in calls if "up" in cmd]
    assert [image for _, image in ups] == ["fetchshelf-local:new", "fetchshelf-local:previous"]
    snapshot = next((state / "backups").glob("release-*/settings.tar.gz"))
    assert snapshot.is_file()
    assert not (state / "release.json").exists()
    assert (tmp_path / "settings/record.txt").read_text() == "preserve this"

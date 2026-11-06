from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.application.main_server import APIServer
from src.webui.preferences import BoardPreferences, BoardPreferenceStore


def client_for(tmp_path):
    server = APIServer.__new__(APIServer)
    server.server = FastAPI()
    server.parameter = SimpleNamespace(settings=SimpleNamespace(path=tmp_path / "settings.json"))
    server.setup_routes()
    return TestClient(server.server)


def test_shared_preferences_survive_restart_and_patch_only_changed_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("FETCHSHELF_API_TOKEN", "fixture-token")
    client = client_for(tmp_path)
    path = "/ui/api/preferences/account-board"
    headers = {"token": "fixture-token"}
    assert client.get(path).status_code == 403
    assert client.patch(path, json={"columns": 8}).status_code == 403
    assert client.get(path, headers=headers).json() == {"preferences": {}}
    assert client.patch(path, headers=headers, json={"columns": 8, "viewMode": "immersive"}).status_code == 200
    # A second device edits only its page size; it must not reset display mode.
    second = client_for(tmp_path)
    response = second.patch(path, headers=headers, json={"pageSize": 36})
    assert response.json()["preferences"] == {"columns": 8, "viewMode": "immersive", "pageSize": 36}
    response = client_for(tmp_path).get(path, headers=headers)
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["preferences"]["columns"] == 8
    # Stale local-storage migration must never replace server preferences.
    response = client.patch(path + "?initialize=true", headers=headers,
                            json={"columns": 2, "viewMode": "avatar", "sort": "latest_desc"})
    assert response.json()["preferences"]["columns"] == 8
    assert response.json()["preferences"]["sort"] == "latest_desc"
    for patch in ({"columns": 99}, {"columns": True}, {"pageSize": 1000},
                  {"viewMode": "invalid"}, {"token": "private-value"}, {"search": "private-query"}):
        assert client.patch(path, headers=headers, json=patch).status_code == 422
    persisted = (tmp_path / "ui_board_preferences.json").read_text()
    assert "private" not in persisted and "token" not in persisted


def test_concurrent_partial_updates_preserve_both_fields(tmp_path):
    store = BoardPreferenceStore(tmp_path / "ui_board_preferences.json")
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(store.update, [BoardPreferences(columns=8), BoardPreferences(viewMode="immersive")]))
    assert store.read() == {"columns": 8, "viewMode": "immersive"}
    assert not list(tmp_path.glob(".ui-preferences-*"))

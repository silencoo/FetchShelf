import shutil
import subprocess
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from src.application.main_server import APIServer


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="requires ffmpeg")
def test_video_thumbnail_uses_file_permissions_and_tracks_replacements(tmp_path, monkeypatch):
    monkeypatch.setenv("FETCHSHELF_API_TOKEN", "fixture")
    server = APIServer.__new__(APIServer)
    server.server = FastAPI()
    server.parameter = SimpleNamespace(root=tmp_path)
    server.setup_routes()
    client = TestClient(server.server)
    path = tmp_path / "short.mp4"
    subprocess.run([
        "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=blue:s=360x640",
        "-t", "0.12", "-c:v", "mpeg4", str(path),
    ], check=True)
    url = "/ui/api/file?scope=download&path=short.mp4"
    assert client.get(url + "&thumbnail=true").status_code == 403
    client.headers["token"] = "fixture"
    preview = client.get(url + "&thumbnail=true")
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "image/jpeg"
    with Image.open(BytesIO(preview.content)) as image:
        assert image.size == (270, 480)
    assert client.get(url).content == path.read_bytes()
    path.write_bytes(b"broken video")
    assert client.get(url + "&thumbnail=true").status_code == 422
    assert client.get(url.replace("short.mp4", "../outside.mp4") + "&thumbnail=true").status_code == 400

import sys
from types import ModuleType, SimpleNamespace

import pytest

from src.webui.profile_avatar import _detect_faces


class _DummyArray:
    shape = (120, 200, 3)


class _FakeFaceDetection:
    def __init__(self, model_selection: int, min_detection_confidence: float):
        self.model_selection = model_selection
        self.min_detection_confidence = min_detection_confidence

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def process(self, rgb_array):
        return SimpleNamespace(
            detections=[
                SimpleNamespace(
                    location_data=SimpleNamespace(
                        relative_bounding_box=SimpleNamespace(
                            xmin=0.1,
                            ymin=0.2,
                            width=0.4,
                            height=0.5,
                        )
                    ),
                    score=[0.9],
                )
            ]
        )


def _install_fake_mediapipe_without_top_level_solutions(
    monkeypatch: pytest.MonkeyPatch,
):
    mp_module = ModuleType("mediapipe")
    mp_module.__version__ = "0.10.32"
    monkeypatch.setitem(sys.modules, "mediapipe", mp_module)

    mp_python = ModuleType("mediapipe.python")
    mp_solutions = ModuleType("mediapipe.python.solutions")
    mp_face_detection = ModuleType("mediapipe.python.solutions.face_detection")
    mp_face_detection.FaceDetection = _FakeFaceDetection

    monkeypatch.setitem(sys.modules, "mediapipe.python", mp_python)
    monkeypatch.setitem(sys.modules, "mediapipe.python.solutions", mp_solutions)
    monkeypatch.setitem(
        sys.modules,
        "mediapipe.python.solutions.face_detection",
        mp_face_detection,
    )


def test_detect_faces_supports_legacy_mediapipe_import_path(
    monkeypatch: pytest.MonkeyPatch,
):
    _install_fake_mediapipe_without_top_level_solutions(monkeypatch)
    boxes = _detect_faces(_DummyArray(), min_confidence=0.5)
    assert len(boxes) == 1
    assert boxes[0]["x1"] == 20
    assert boxes[0]["y1"] == 24


def test_detect_faces_raises_runtime_error_when_api_missing(
    monkeypatch: pytest.MonkeyPatch,
):
    mp_module = ModuleType("mediapipe")
    mp_module.__version__ = "0.10.32"
    monkeypatch.setitem(sys.modules, "mediapipe", mp_module)
    for key in (
        "mediapipe.python",
        "mediapipe.python.solutions",
        "mediapipe.python.solutions.face_detection",
    ):
        sys.modules.pop(key, None)
    with pytest.raises(RuntimeError, match="不支持当前的人脸检测 API"):
        _detect_faces(_DummyArray(), min_confidence=0.5)

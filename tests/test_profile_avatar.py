import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from src.webui import profile_avatar
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


def test_detect_faces_falls_back_to_opencv_when_api_missing(
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
    called: dict[str, float] = {}

    def _fake_opencv_detector(rgb_array, min_confidence: float):
        called["min_confidence"] = min_confidence
        return [
            {
                "x1": 1,
                "y1": 2,
                "x2": 21,
                "y2": 22,
                "width": 20,
                "height": 20,
                "area": 400,
                "score": 0.0,
            }
        ]

    monkeypatch.setattr(
        profile_avatar,
        "_detect_faces_with_opencv",
        _fake_opencv_detector,
    )
    boxes = _detect_faces(_DummyArray(), min_confidence=0.5)
    assert len(boxes) == 1
    assert boxes[0]["x1"] == 1
    assert called["min_confidence"] == 0.5


def test_video_avatar_checks_multiple_frames_and_selects_best_face(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    video_path = tmp_path / "account.mp4"
    video_path.write_bytes(b"video")
    first_frame = tmp_path / "frame-1.jpg"
    second_frame = tmp_path / "frame-2.jpg"
    first_frame.write_bytes(b"first")
    second_frame.write_bytes(b"second")
    output_path = tmp_path / "avatar.jpg"
    detection_calls = []
    saved = {}

    monkeypatch.setattr(
        profile_avatar,
        "_extract_video_frames",
        lambda path: [first_frame, second_frame],
    )
    monkeypatch.setattr(
        profile_avatar,
        "_load_rgb_array",
        lambda path: _DummyArray(),
    )

    def detect(rgb_array, min_confidence: float):
        detection_calls.append(min_confidence)
        if len(detection_calls) == 1:
            return [
                {
                    "x1": 0,
                    "y1": 0,
                    "x2": 20,
                    "y2": 20,
                    "width": 20,
                    "height": 20,
                    "area": 400,
                    "score": 0.6,
                }
            ]
        return [
            {
                "x1": 55,
                "y1": 20,
                "x2": 145,
                "y2": 110,
                "width": 90,
                "height": 90,
                "area": 8100,
                "score": 0.95,
            }
        ]

    def save(source, output_path, face_box, padding_ratio, output_size):
        saved["source"] = source
        saved["face"] = face_box

    monkeypatch.setattr(profile_avatar, "_detect_faces", detect)
    monkeypatch.setattr(profile_avatar, "_save_face_crop", save)

    result = profile_avatar.generate_face_avatar(video_path, output_path)

    assert result["source_kind"] == "video"
    assert result["frames_checked"] == 2
    assert result["selected_frame"] == 2
    assert result["faces_detected"] == 2
    assert saved["source"] == second_frame
    assert len(detection_calls) == 2
    assert not first_frame.exists()
    assert not second_frame.exists()


def test_runtime_probe_mediapipe_with_profile_webp():
    image_path = Path("profile.webp")
    if not image_path.exists():
        pytest.skip("profile.webp 不存在，跳过运行时探针。")

    try:
        import mediapipe as mp
    except ImportError as error:
        pytest.fail(f"mediapipe 不可导入：{error}")

    tasks_vision = getattr(getattr(mp, "tasks", None), "vision", None)
    has_tasks_face_detector = hasattr(tasks_vision, "FaceDetector")
    has_top_level_face_detection = hasattr(
        getattr(mp, "solutions", None),
        "face_detection",
    )
    print(
        (
            "mediapipe_probe: "
            f"version={getattr(mp, '__version__', 'unknown')}, "
            f"has_solutions={hasattr(mp, 'solutions')}, "
            f"has_top_level_face_detection={has_top_level_face_detection}, "
            f"has_tasks_face_detector={has_tasks_face_detector}"
        )
    )
    assert has_tasks_face_detector is True

    rgb_array = profile_avatar._load_rgb_array(image_path)
    if has_top_level_face_detection:
        boxes = profile_avatar._detect_faces_with_mediapipe(
            rgb_array,
            min_confidence=0.5,
        )
        print(f"mediapipe_probe: legacy_solutions_boxes={len(boxes)}")
    else:
        with pytest.raises(RuntimeError, match="未提供 solutions.face_detection"):
            profile_avatar._detect_faces_with_mediapipe(
                rgb_array,
                min_confidence=0.5,
            )


def test_runtime_probe_mediapipe_tasks_with_profile_webp():
    image_path = Path("profile.webp")
    if not image_path.exists():
        pytest.skip("profile.webp 不存在，跳过 mediapipe tasks 运行时探针。")

    model_path = profile_avatar._resolve_mediapipe_face_model_path()
    if not model_path:
        pytest.skip(
            "未找到 detector.tflite（或配置环境变量），"
            "跳过 mediapipe tasks FaceDetector 探针。"
        )

    rgb_array = profile_avatar._load_rgb_array(image_path)
    boxes = profile_avatar._detect_faces_with_mediapipe_tasks(
        rgb_array,
        min_confidence=0.5,
    )
    print(
        (
            "mediapipe_tasks_probe: "
            f"model={model_path}, "
            f"boxes={len(boxes)}"
        )
    )
    assert isinstance(boxes, list)

import os
from pathlib import Path
from shutil import which
from subprocess import DEVNULL, CalledProcessError, run
from tempfile import NamedTemporaryFile
from typing import Any

from .files import VIDEO_SUFFIXES

__all__ = ["generate_face_avatar"]

_MEDIAPIPE_FACE_MODEL_ENV_KEYS = (
    "TIKTOKDOWNLOADER_FACE_DETECTOR_MODEL",
    "MEDIAPIPE_FACE_DETECTOR_MODEL",
)
_MEDIAPIPE_FACE_MODEL_CANDIDATES = (
    "detector.tflite",
    "face_detector.tflite",
    "models/detector.tflite",
    "models/face_detector.tflite",
    "static/models/detector.tflite",
    "static/models/face_detector.tflite",
)


def _load_rgb_array(path: Path):
    try:
        import numpy as np
        from PIL import Image
    except ImportError as error:
        raise RuntimeError(
            "缺少图像依赖，请安装 pillow（例如：uv add pillow）。"
        ) from error
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        array = np.asarray(rgb)
    return array


def _extract_video_frame(path: Path) -> Path:
    frames = _extract_video_frames(path, frame_count=1)
    return frames[0]


def _video_duration(path: Path) -> float:
    ffprobe = which("ffprobe")
    if not ffprobe:
        return 0.0
    command = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        result = run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
        return max(0.0, float(result.stdout.strip() or 0))
    except (CalledProcessError, TypeError, ValueError):
        return 0.0


def _extract_video_frames(path: Path, frame_count: int = 4) -> list[Path]:
    ffmpeg = which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("处理视频头像需要 ffmpeg，请先安装 ffmpeg。")
    count = max(1, min(int(frame_count or 1), 8))
    duration = _video_duration(path)
    if duration > 0.5 and count > 1:
        ratios = (0.12, 0.35, 0.58, 0.82)
        timestamps = [duration * ratio for ratio in ratios[:count]]
    else:
        timestamps = [0.0]

    frames = []
    for timestamp in timestamps:
        with NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            frame_path = Path(tmp.name)
        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
        ]
        if timestamp > 0:
            command.extend(["-ss", f"{timestamp:.3f}"])
        command.extend(
            [
                "-i",
                str(path),
                "-frames:v",
                "1",
                str(frame_path),
            ]
        )
        try:
            run(command, check=True, stdout=DEVNULL, stderr=DEVNULL)
        except CalledProcessError:
            frame_path.unlink(missing_ok=True)
            continue
        if not frame_path.exists() or frame_path.stat().st_size <= 0:
            frame_path.unlink(missing_ok=True)
            continue
        frames.append(frame_path)
    if not frames:
        raise RuntimeError("视频抽帧失败，无法生成人脸头像。")
    return frames


def _resolve_mediapipe_face_model_path() -> Path | None:
    roots = [Path.cwd(), Path(__file__).resolve().parents[2]]
    unique_roots = []
    for root in roots:
        resolved = root.resolve()
        if resolved not in unique_roots:
            unique_roots.append(resolved)

    for env_key in _MEDIAPIPE_FACE_MODEL_ENV_KEYS:
        raw = os.environ.get(env_key, "").strip()
        if not raw:
            continue
        candidate = Path(raw).expanduser()
        if candidate.is_absolute():
            absolute_candidates = [candidate.resolve()]
        else:
            absolute_candidates = [
                (root / candidate).resolve() for root in unique_roots
            ]
        for item in absolute_candidates:
            if item.exists() and item.is_file():
                return item

    for root in unique_roots:
        for relative in _MEDIAPIPE_FACE_MODEL_CANDIDATES:
            candidate = (root / relative).resolve()
            if candidate.exists() and candidate.is_file():
                return candidate
    return None


def _detect_faces_with_mediapipe_tasks(
    rgb_array,
    min_confidence: float,
) -> list[dict[str, Any]]:
    try:
        import mediapipe as mp
    except ImportError as error:
        detail = str(error).strip() or error.__class__.__name__
        raise RuntimeError(
            "导入 mediapipe 失败："
            f"{detail}。请确认已安装 mediapipe，并在容器中安装运行时库 "
            "(如 libglib2.0-0、libx11-6、libxcb1、libgl1)。"
        ) from error

    try:
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision as mp_vision
    except Exception as error:
        version = getattr(mp, "__version__", "unknown")
        detail = str(error).strip() or error.__class__.__name__
        raise RuntimeError(
            "不支持当前的 mediapipe tasks API："
            f"mediapipe=={version} 无法导入 FaceDetector（{detail}）。"
        ) from error

    model_path = _resolve_mediapipe_face_model_path()
    if not model_path:
        env_names = " / ".join(_MEDIAPIPE_FACE_MODEL_ENV_KEYS)
        candidates = ", ".join(_MEDIAPIPE_FACE_MODEL_CANDIDATES[:2])
        raise RuntimeError(
            "mediapipe tasks FaceDetector 需要模型文件（例如 detector.tflite）。"
            f"未找到可用模型，请设置环境变量 {env_names} "
            f"或在项目目录放置 {candidates}。"
        )

    detector_options = mp_vision.FaceDetectorOptions(
        base_options=mp_python.BaseOptions(model_asset_path=str(model_path)),
        min_detection_confidence=min_confidence,
    )
    try:
        detector = mp_vision.FaceDetector.create_from_options(detector_options)
    except Exception as error:
        detail = str(error).strip() or error.__class__.__name__
        raise RuntimeError(
            f"mediapipe tasks FaceDetector 初始化失败：{detail}。"
        ) from error

    try:
        mp_image = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=rgb_array,
        )
        results = detector.detect(mp_image)
    except Exception as error:
        detail = str(error).strip() or error.__class__.__name__
        raise RuntimeError(
            f"mediapipe tasks FaceDetector 识别失败：{detail}。"
        ) from error
    finally:
        detector.close()

    height, width = rgb_array.shape[:2]
    if width <= 1 or height <= 1:
        return []

    boxes = []
    detections = list(getattr(results, "detections", []) or [])
    for item in detections:
        bounding_box = getattr(item, "bounding_box", None)
        if not bounding_box:
            continue
        x1 = max(0, int(getattr(bounding_box, "origin_x", 0)))
        y1 = max(0, int(getattr(bounding_box, "origin_y", 0)))
        box_w = int(getattr(bounding_box, "width", 0))
        box_h = int(getattr(bounding_box, "height", 0))
        if box_w <= 2 or box_h <= 2:
            continue
        x2 = min(width, x1 + box_w)
        y2 = min(height, y1 + box_h)
        if x2 - x1 <= 2 or y2 - y1 <= 2:
            continue
        score = 0.0
        categories = list(getattr(item, "categories", []) or [])
        if categories:
            score = float(getattr(categories[0], "score", 0.0) or 0.0)
        boxes.append(
            {
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "width": x2 - x1,
                "height": y2 - y1,
                "area": (x2 - x1) * (y2 - y1),
                "score": score,
            }
        )
    return sorted(boxes, key=lambda item: item["area"], reverse=True)


def _detect_faces_with_mediapipe_legacy(
    rgb_array,
    min_confidence: float,
) -> list[dict[str, Any]]:
    try:
        import mediapipe as mp
    except ImportError as error:
        detail = str(error).strip() or error.__class__.__name__
        raise RuntimeError(
            "导入 mediapipe 失败："
            f"{detail}。请确认已安装 mediapipe，并在容器中安装运行时库 "
            "(如 libglib2.0-0、libx11-6、libxcb1、libgl1)。"
        ) from error

    face_detection = getattr(getattr(mp, "solutions", None), "face_detection", None)
    if not face_detection:
        try:
            from mediapipe.python.solutions import (  # type: ignore[attr-defined]
                face_detection as mp_face_detection,
            )
        except Exception as error:
            version = getattr(mp, "__version__", "unknown")
            raise RuntimeError(
                "不支持当前的人脸检测 API："
                f"mediapipe=={version} 未提供 solutions.face_detection。"
            ) from error
        face_detection = mp_face_detection

    height, width = rgb_array.shape[:2]
    if width <= 1 or height <= 1:
        return []

    boxes = []
    with face_detection.FaceDetection(
        model_selection=1,
        min_detection_confidence=min_confidence,
    ) as detector:
        results = detector.process(rgb_array)
    detections = list(getattr(results, "detections", []) or [])
    for item in detections:
        rel_box = item.location_data.relative_bounding_box
        x1 = max(0, int(rel_box.xmin * width))
        y1 = max(0, int(rel_box.ymin * height))
        box_w = int(rel_box.width * width)
        box_h = int(rel_box.height * height)
        if box_w <= 2 or box_h <= 2:
            continue
        x2 = min(width, x1 + box_w)
        y2 = min(height, y1 + box_h)
        if x2 - x1 <= 2 or y2 - y1 <= 2:
            continue
        score = 0.0
        if getattr(item, "score", None):
            score = float(item.score[0] or 0.0)
        boxes.append(
            {
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "width": x2 - x1,
                "height": y2 - y1,
                "area": (x2 - x1) * (y2 - y1),
                "score": score,
            }
        )
    return sorted(boxes, key=lambda item: item["area"], reverse=True)


def _detect_faces_with_opencv(rgb_array, min_confidence: float) -> list[dict[str, Any]]:
    try:
        import cv2
    except ImportError as error:
        detail = str(error).strip() or error.__class__.__name__
        raise RuntimeError(f"导入 OpenCV 失败：{detail}。") from error

    cascade_root = Path(getattr(getattr(cv2, "data", None), "haarcascades", ""))
    cascade_path = cascade_root / "haarcascade_frontalface_default.xml"
    if not cascade_path.exists():
        raise RuntimeError(
            "OpenCV 未提供人脸检测模型 haarcascade_frontalface_default.xml。"
        )

    detector = cv2.CascadeClassifier(str(cascade_path))
    if detector.empty():
        raise RuntimeError("OpenCV 人脸检测模型加载失败。")

    gray = cv2.cvtColor(rgb_array, cv2.COLOR_RGB2GRAY)
    if gray.size <= 0:
        return []

    min_neighbors = 3 if min_confidence < 0.45 else 4 if min_confidence < 0.7 else 5
    detections = detector.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=min_neighbors,
        minSize=(24, 24),
    )
    boxes = []
    for x, y, box_w, box_h in detections:
        x1 = max(0, int(x))
        y1 = max(0, int(y))
        x2 = x1 + int(box_w)
        y2 = y1 + int(box_h)
        if x2 - x1 <= 2 or y2 - y1 <= 2:
            continue
        boxes.append(
            {
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "width": x2 - x1,
                "height": y2 - y1,
                "area": (x2 - x1) * (y2 - y1),
                "score": 0.0,
            }
        )
    return sorted(boxes, key=lambda item: item["area"], reverse=True)


def _detect_faces_with_mediapipe(
    rgb_array,
    min_confidence: float,
) -> list[dict[str, Any]]:
    errors = []
    for detector in (
        _detect_faces_with_mediapipe_tasks,
        _detect_faces_with_mediapipe_legacy,
    ):
        try:
            return detector(rgb_array, min_confidence=min_confidence)
        except RuntimeError as error:
            errors.append(str(error))
    raise RuntimeError("；".join(errors))


def _detect_faces(rgb_array, min_confidence: float) -> list[dict[str, Any]]:
    try:
        return _detect_faces_with_mediapipe(
            rgb_array,
            min_confidence=min_confidence,
        )
    except RuntimeError as mediapipe_error:
        try:
            return _detect_faces_with_opencv(
                rgb_array,
                min_confidence=min_confidence,
            )
        except RuntimeError as opencv_error:
            raise RuntimeError(
                f"{mediapipe_error}；OpenCV 回退也失败：{opencv_error}"
            ) from opencv_error


def _save_face_crop(
    source_path: Path,
    output_path: Path,
    face_box: dict[str, Any],
    padding_ratio: float,
    output_size: int,
) -> None:
    try:
        from PIL import Image
    except ImportError as error:
        raise RuntimeError(
            "缺少图像依赖，请安装 pillow（例如：uv add pillow）。"
        ) from error

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source_path) as image:
        rgb = image.convert("RGB")
        width, height = rgb.size
        pad_x = int(face_box["width"] * max(0.0, padding_ratio))
        pad_y = int(face_box["height"] * max(0.0, padding_ratio))
        x1 = max(0, face_box["x1"] - pad_x)
        y1 = max(0, face_box["y1"] - pad_y)
        x2 = min(width, face_box["x2"] + pad_x)
        y2 = min(height, face_box["y2"] + pad_y)
        cropped = rgb.crop((x1, y1, x2, y2))
        edge = max(cropped.width, cropped.height)
        canvas = Image.new("RGB", (edge, edge), (0, 0, 0))
        offset = ((edge - cropped.width) // 2, (edge - cropped.height) // 2)
        canvas.paste(cropped, offset)
        avatar = canvas.resize((output_size, output_size))
        avatar.save(output_path, format="JPEG", quality=92, optimize=True)


def _face_candidate_quality(face_box: dict[str, Any], rgb_array) -> float:
    height, width = rgb_array.shape[:2]
    if width <= 0 or height <= 0:
        return 0.0
    frame_area = width * height
    area_ratio = min(1.0, float(face_box.get("area", 0)) / frame_area * 8)
    confidence = max(0.0, min(1.0, float(face_box.get("score", 0.0) or 0.0)))
    center_x = (float(face_box.get("x1", 0)) + float(face_box.get("x2", 0))) / 2
    center_y = (float(face_box.get("y1", 0)) + float(face_box.get("y2", 0))) / 2
    distance = (
        ((center_x - width / 2) / max(width / 2, 1)) ** 2
        + ((center_y - height / 2) / max(height / 2, 1)) ** 2
    ) ** 0.5
    centered = max(0.0, 1.0 - min(1.0, distance))
    return confidence * 0.42 + area_ratio * 0.4 + centered * 0.18


def generate_face_avatar(
    media_path: Path,
    output_path: Path,
    min_confidence: float = 0.55,
    padding_ratio: float = 0.22,
    output_size: int = 512,
) -> dict[str, Any]:
    source = Path(media_path).expanduser().resolve()
    if not source.exists() or not source.is_file():
        raise RuntimeError("源媒体文件不存在。")
    suffix = source.suffix.lower()
    temporary_frames: list[Path] = []
    detect_sources = [source]
    source_kind = "image"
    if suffix in VIDEO_SUFFIXES:
        source_kind = "video"
        temporary_frames = _extract_video_frames(source)
        detect_sources = temporary_frames
    try:
        best_candidate = None
        faces_detected = 0
        for frame_index, detect_source in enumerate(detect_sources):
            rgb_array = _load_rgb_array(detect_source)
            faces = _detect_faces(rgb_array, min_confidence=min_confidence)
            faces_detected += len(faces)
            for face in faces:
                quality = _face_candidate_quality(face, rgb_array)
                if best_candidate is None or quality > best_candidate["quality"]:
                    best_candidate = {
                        "source": detect_source,
                        "face": face,
                        "quality": quality,
                        "frame_index": frame_index,
                    }
        if not best_candidate:
            raise RuntimeError("未识别到人脸，请尝试换一张图片/视频。")
        _save_face_crop(
            best_candidate["source"],
            output_path=output_path,
            face_box=best_candidate["face"],
            padding_ratio=padding_ratio,
            output_size=max(128, int(output_size)),
        )
        return {
            "faces_detected": faces_detected,
            "score": round(
                float(best_candidate["face"].get("score", 0.0)),
                4,
            ),
            "quality": round(float(best_candidate["quality"]), 4),
            "frames_checked": len(detect_sources),
            "selected_frame": int(best_candidate["frame_index"]) + 1,
            "source_kind": source_kind,
            "source_name": source.name,
            "output_name": output_path.name,
        }
    finally:
        for temporary_frame in temporary_frames:
            temporary_frame.unlink(missing_ok=True)

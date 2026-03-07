from pathlib import Path
from shutil import which
from subprocess import DEVNULL, CalledProcessError, run
from tempfile import NamedTemporaryFile
from typing import Any

from .files import VIDEO_SUFFIXES

__all__ = ["generate_face_avatar"]


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
    ffmpeg = which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("处理视频头像需要 ffmpeg，请先安装 ffmpeg。")
    with NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        frame_path = Path(tmp.name)
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(path),
        "-frames:v",
        "1",
        str(frame_path),
    ]
    try:
        run(command, check=True, stdout=DEVNULL, stderr=DEVNULL)
    except CalledProcessError as error:
        frame_path.unlink(missing_ok=True)
        raise RuntimeError("视频首帧提取失败，无法生成人脸头像。") from error
    if not frame_path.exists() or frame_path.stat().st_size <= 0:
        frame_path.unlink(missing_ok=True)
        raise RuntimeError("视频首帧为空，无法生成人脸头像。")
    return frame_path


def _detect_faces(rgb_array, min_confidence: float) -> list[dict[str, Any]]:
    try:
        import mediapipe as mp
    except ImportError as error:
        detail = str(error).strip() or error.__class__.__name__
        raise RuntimeError(
            "导入 mediapipe/cv2 失败："
            f"{detail}。请确认已安装 mediapipe，并在容器中安装运行时库 "
            "(如 libglib2.0-0、libx11-6、libxcb1、libgl1)。"
        ) from error

    height, width = rgb_array.shape[:2]
    if width <= 1 or height <= 1:
        return []

    boxes = []
    with mp.solutions.face_detection.FaceDetection(
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
    temporary_frame = None
    detect_source = source
    source_kind = "image"
    if suffix in VIDEO_SUFFIXES:
        source_kind = "video"
        temporary_frame = _extract_video_frame(source)
        detect_source = temporary_frame
    try:
        rgb_array = _load_rgb_array(detect_source)
        faces = _detect_faces(rgb_array, min_confidence=min_confidence)
        if not faces:
            raise RuntimeError("未识别到人脸，请尝试换一张图片/视频。")
        _save_face_crop(
            detect_source,
            output_path=output_path,
            face_box=faces[0],
            padding_ratio=padding_ratio,
            output_size=max(128, int(output_size)),
        )
        return {
            "faces_detected": len(faces),
            "score": round(float(faces[0].get("score", 0.0)), 4),
            "source_kind": source_kind,
            "source_name": source.name,
            "output_name": output_path.name,
        }
    finally:
        if temporary_frame:
            temporary_frame.unlink(missing_ok=True)

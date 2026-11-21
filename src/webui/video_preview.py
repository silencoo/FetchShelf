from functools import lru_cache
from io import BytesIO
from json import loads
from os import stat_result
from pathlib import Path
from subprocess import DEVNULL, PIPE, SubprocessError, run

from .files import IMAGE_SUFFIXES, VIDEO_SUFFIXES


def preview_revision(stat: stat_result) -> str:
    return f"{stat.st_mtime_ns:x}-{stat.st_size:x}"


def preview_metadata(path: Path) -> dict[str, int | str]:
    stat = path.stat()
    dimensions = _preview_dimensions(path, stat.st_mtime_ns, stat.st_size)
    metadata: dict[str, int | str] = {"version": preview_revision(stat)}
    if dimensions:
        width, height = dimensions
        metadata.update(width=width, height=height)
    return metadata


@lru_cache(maxsize=4096)
def _preview_dimensions(path: Path, mtime_ns: int, size: int) -> tuple[int, int] | None:
    from PIL import Image

    try:
        if path.suffix.lower() in IMAGE_SUFFIXES:
            with Image.open(path) as image:
                width, height = image.size
                if image.getexif().get(274) in (5, 6, 7, 8):
                    width, height = height, width
                return width, height
        if path.suffix.lower() in VIDEO_SUFFIXES:
            result = run(
                [
                    "ffprobe", "-v", "error", "-protocol_whitelist", "file",
                    "-format_whitelist", "mov,matroska,webm,avi,flv",
                    "-select_streams", "v:0",
                    "-show_entries", "stream=width,height:stream_side_data=rotation",
                    "-of", "json", str(path),
                ],
                stdout=PIPE, stderr=DEVNULL, timeout=1, check=True,
            )
            for stream in loads(result.stdout).get("streams", []):
                width, height = stream.get("width", 0), stream.get("height", 0)
                for side_data in stream.get("side_data_list", []):
                    if abs(side_data.get("rotation", 0)) % 180 == 90:
                        width, height = height, width
                        break
                if width > 0 and height > 0:
                    return width, height
    except (Image.DecompressionBombError, OSError, SubprocessError, SyntaxError, ValueError):
        pass
    return None


@lru_cache(maxsize=192)
def video_preview(path: Path, mtime_ns: int, size: int, second: int = 0) -> bytes:
    """Cache a small JPEG per source revision, without writing into the library."""
    result = run(
        [
            "ffmpeg", "-nostdin", "-loglevel", "error",
            "-protocol_whitelist", "file",
            "-format_whitelist", "mov,matroska,webm,avi,flv",
            *(["-ss", str(second)] if second else []),
            "-threads", "1", "-i", str(path), "-map", "0:v:0",
            "-frames:v", "1", "-vf",
            "scale=480:480:force_original_aspect_ratio=decrease",
            "-threads", "1", "-c:v", "mjpeg", "-q:v", "4",
            "-f", "image2pipe", "pipe:1",
        ],
        stdout=PIPE, stderr=DEVNULL, timeout=12, check=True,
    )
    if not result.stdout:
        raise ValueError("No video frame available.")
    return result.stdout


@lru_cache(maxsize=256)
def image_preview(path: Path, mtime_ns: int, size: int, width: int = 480) -> bytes:
    """Downscale a photo for grids, so phones never decode full-size originals."""
    from PIL import Image, ImageOps

    try:
        with Image.open(path) as image:
            # DCT scaling makes large JPEGs cheap to decode at thumbnail size.
            image.draft("RGB", (width * 2, width * 2))
            upright = ImageOps.exif_transpose(image)
            upright.thumbnail((width, width * 2))
            output = BytesIO()
            upright.convert("RGB").save(output, "JPEG", quality=80)
    except Image.DecompressionBombError as error:
        raise ValueError("Image is too large to preview.") from error
    return output.getvalue()

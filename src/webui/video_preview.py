from functools import lru_cache
from io import BytesIO
from pathlib import Path
from subprocess import DEVNULL, PIPE, run


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

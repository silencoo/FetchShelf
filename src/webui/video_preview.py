from functools import lru_cache
from pathlib import Path
from subprocess import DEVNULL, PIPE, run


@lru_cache(maxsize=192)
def video_preview(path: Path, mtime_ns: int, size: int) -> bytes:
    """Cache a small JPEG per source revision, without writing into the library."""
    result = run(
        [
            "ffmpeg", "-nostdin", "-loglevel", "error",
            "-protocol_whitelist", "file",
            "-format_whitelist", "mov,matroska,webm,avi,flv",
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

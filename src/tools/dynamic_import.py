import importlib.util
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.translation import _

if TYPE_CHECKING:
    from src.tools import ColorfulConsole


def get_base_dir() -> Path:
    """Return the directory that may contain a trusted external signer."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent.parent / "_internal"
    return Path(__file__).resolve().parent.parent.parent


def load_objects_from_external_py(
    file_name: str,
    object_names: list[str],
    console: "ColorfulConsole",
) -> dict[str, Any]:
    """Load named objects from a trusted local Python module.

    External signer code executes with the same permissions as the application.
    Import and execution errors are reported and treated as an empty module so the
    caller can fall back to the built-in implementations.
    """
    base_dir = get_base_dir()
    configured_path = os.environ.get("FETCHSHELF_ENCIPHER_PATH", "").strip()
    candidates = []
    if configured_path:
        candidates.append(Path(configured_path).expanduser())
    candidates.extend((base_dir / file_name, base_dir / "settings" / file_name))
    normalized_candidates = [
        path if path.suffix else path.with_suffix(".py") for path in candidates
    ]
    file_path = next((path for path in normalized_candidates if path.is_file()), None)
    if file_path is None:
        console.info(_("未检测到外部加密参数代码，将使用项目内置实现。"))
        return {}

    try:
        spec = importlib.util.spec_from_file_location(
            "fetchshelf_external_encipher",
            file_path,
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"Unable to create import spec for {file_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as error:
        console.error(
            _("外部加密参数代码加载失败，将使用项目内置实现：{error}").format(
                error=error
            )
        )
        return {}

    return {
        object_name: getattr(module, object_name)
        for object_name in object_names
        if hasattr(module, object_name)
    }

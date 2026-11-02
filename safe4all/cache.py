"""Live-first caching for Colab Shared Drives and local Jupyter sessions."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Callable


def is_colab() -> bool:
    try:
        import google.colab  # noqa: F401
    except ImportError:
        return False
    return True


def cache_root() -> Path:
    """Return the workshop cache, mounting the configured Shared Drive in Colab.

    Set ``SAFE4ALL_SHARED_DRIVE`` to the exact Shared Drive name before a
    workshop. If it is unavailable, a persistent local fallback is used.
    """
    project_root = Path(__file__).resolve().parents[1]
    local_root = Path(os.environ.get("SAFE4ALL_CACHE_DIR", project_root / ".safe4all-cache"))
    if not is_colab():
        local_root.mkdir(parents=True, exist_ok=True)
        return local_root

    from google.colab import drive

    drive.mount("/content/drive", force_remount=False)
    drive_name = os.environ.get("SAFE4ALL_SHARED_DRIVE", "SAFE4ALL-workshop")
    shared_root = Path("/content/drive/Shareddrives") / drive_name
    if shared_root.exists():
        root = shared_root / "Climate_Risk_Assessment"
    else:
        print(f"Shared Drive '{drive_name}' was not found; using MyDrive fallback.")
        root = Path("/content/drive/MyDrive/SAFE4ALL_Climate_Risk_Assessment")
    root.mkdir(parents=True, exist_ok=True)
    return root


def cached_file(relative_name: str, build: Callable[[Path], None]) -> Path:
    """Return a cached file, building it once from an approved live source."""
    target = cache_root() / relative_name
    if target.exists():
        print(f"Cache hit: {target}")
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    build(target)
    if not target.exists():
        raise RuntimeError(f"The data build did not create {target}")
    print(f"Cached: {target}")
    return target


def copy_to_cache(source: str | Path, relative_name: str) -> Path:
    """Copy a manually downloaded, approved dataset into the shared cache."""
    source = Path(source)
    if not source.is_file():
        raise FileNotFoundError(source)
    target = cache_root() / relative_name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return target

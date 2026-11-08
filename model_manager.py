from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

import requests

from config import AVAILABLE_MODELS, DEFAULT_MODEL, get_models_dir

HF_URL = "https://huggingface.co/{repo}/resolve/main/{filename}?download=true"
_CHUNK = 1024 * 512


class DownloadCancelled(Exception):
    pass


def _is_model(p: Path) -> bool:
    # Skip helper files (vision projectors, speculative-decoding heads)
    return p.suffix == ".gguf" and not p.name.startswith(("mmproj", "mtp-"))


def list_local_models() -> list[Path]:
    d = get_models_dir()
    if not d.exists():
        return []
    return sorted(p for p in d.glob("*.gguf") if _is_model(p))


def has_any_model() -> bool:
    return bool(list_local_models())


def models_dir_size_gb() -> float:
    return sum(f.stat().st_size for f in list_local_models()) / 1_073_741_824


def get_model_info(filename: str) -> dict | None:
    return next((m for m in AVAILABLE_MODELS if m["filename"] == filename), None)


def download_model(
    repo_id: str,
    filename: str,
    progress_callback: Callable[[int, int], None] | None = None,
    cancel: threading.Event | None = None,
) -> Path:
    """Download a model, resuming a previous partial download if there is one."""
    d = get_models_dir()
    d.mkdir(parents=True, exist_ok=True)
    dest = d / filename
    if dest.exists():
        return dest

    part = dest.with_name(dest.name + ".part")
    have = part.stat().st_size if part.exists() else 0
    headers = {"Range": f"bytes={have}-"} if have else {}
    url = HF_URL.format(repo=repo_id, filename=filename)

    with requests.get(url, stream=True, timeout=30, headers=headers) as r:
        if r.status_code == 416:            # already fully downloaded
            part.rename(dest)
            return dest
        r.raise_for_status()
        if r.status_code != 206:            # server ignored Range — start over
            have = 0
        total = have + int(r.headers.get("content-length", 0))
        done = have
        with open(part, "ab" if have else "wb") as f:
            for chunk in r.iter_content(chunk_size=_CHUNK):
                if cancel is not None and cancel.is_set():
                    raise DownloadCancelled()
                f.write(chunk)
                done += len(chunk)
                if progress_callback and total:
                    progress_callback(done, total)

    if total and part.stat().st_size != total:
        raise IOError("Download incomplete — please try again (it will resume).")
    part.rename(dest)
    return dest


def download_default(progress_callback=None, cancel=None) -> Path:
    return download_model(DEFAULT_MODEL["repo"], DEFAULT_MODEL["filename"],
                          progress_callback, cancel)

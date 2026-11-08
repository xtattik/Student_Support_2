"""
Download the pinned llama.cpp `llama-server` build into ./bin for this OS.

Used by the GitHub Actions build and for running from source:
    python scripts/fetch_llama_server.py

Windows: the CPU build (all CPU-variant DLLs, picked at runtime) is extracted
first, then the Vulkan build on top, so the app can use integrated graphics
but still runs on machines without a working Vulkan driver.
macOS (Apple Silicon): the Metal build.
"""
from __future__ import annotations

import io
import platform
import shutil
import sys
import tarfile
import zipfile
from pathlib import Path
from urllib.request import urlopen

# Pinned to the llama.cpp stable release v0.9.0 (= build b12110). Bump deliberately.
LLAMA_BUILD = "b12110"
BASE = f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_BUILD}"

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "bin"


def _fetch(name: str) -> bytes:
    url = f"{BASE}/{name}"
    print(f"Downloading {url}")
    with urlopen(url, timeout=120) as r:
        return r.read()


def _extract_zip_flat(data: bytes, dest: Path) -> None:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for m in z.infolist():
            if m.is_dir():
                continue
            target = dest / Path(m.filename).name  # flatten any sub-folder
            with z.open(m) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)


def _extract_tar_flat(data: bytes, dest: Path) -> None:
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as t:
        for m in t.getmembers():
            name = Path(m.name).name
            if m.isfile():
                with t.extractfile(m) as src, open(dest / name, "wb") as out:
                    shutil.copyfileobj(src, out)
                (dest / name).chmod(m.mode | 0o644)
            elif m.issym() and "/" not in m.linkname:
                link = dest / name
                if link.exists() or link.is_symlink():
                    link.unlink()
                link.symlink_to(m.linkname)


def main() -> int:
    system, machine = platform.system(), platform.machine().lower()
    if BIN.exists():
        for f in BIN.iterdir():
            if f.name != ".gitkeep":
                f.unlink() if f.is_file() or f.is_symlink() else shutil.rmtree(f)
    BIN.mkdir(exist_ok=True)

    if system == "Windows":
        arch = "arm64" if machine in ("arm64", "aarch64") else "x64"
        _extract_zip_flat(_fetch(f"llama-{LLAMA_BUILD}-bin-win-cpu-{arch}.zip"), BIN)
        _extract_zip_flat(_fetch(f"llama-{LLAMA_BUILD}-bin-win-vulkan-{arch}.zip"), BIN)
        exe = BIN / "llama-server.exe"
    elif system == "Darwin":
        arch = "arm64" if machine == "arm64" else "x64"
        _extract_tar_flat(_fetch(f"llama-{LLAMA_BUILD}-bin-macos-{arch}.tar.gz"), BIN)
        exe = BIN / "llama-server"
    else:
        print("Only Windows and macOS are supported.")
        return 1

    # Keep only what llama-server needs: drop the other CLI tools to save space
    for f in BIN.iterdir():
        n = f.name
        if n.startswith("llama-server"):
            continue
        # Other tools ship as llama-<tool>.exe plus a llama-<tool>-impl library
        if n.startswith("llama-") and ("-impl." in n or "." not in n or n.endswith(".exe")):
            f.unlink()
        elif n.startswith(("test-", "rpc-server", "ggml-rpc-server")):
            f.unlink()
        elif n in ("llama.exe", "llama"):  # all-in-one CLI launcher, not needed
            f.unlink()

    if not exe.exists():
        print(f"ERROR: {exe} not found after extraction")
        return 1
    total = sum(f.stat().st_size for f in BIN.iterdir() if f.is_file()) / 1e6
    print(f"OK — llama-server {LLAMA_BUILD} in {BIN} ({total:.0f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

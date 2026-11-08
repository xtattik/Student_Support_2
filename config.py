import json
import os
import sys
import platform
from pathlib import Path

VERSION = "2.0.0"

# Same data folder as v1 ("StudentAI"), so v2 upgrades in place and finds the
# models students already downloaded.
APP_ID       = "StudentAI"
APP_NAME     = "Student AI Support"
GITHUB_REPO  = "xtattik/Student_Support_2"
HELP_URL     = f"https://github.com/{GITHUB_REPO}#readme"

IS_WINDOWS = platform.system() == "Windows"
IS_MAC     = platform.system() == "Darwin"
FROZEN     = getattr(sys, "frozen", False)

# Bundled read-only files (logo, llama-server binaries) live in sys._MEIPASS when frozen.
if FROZEN:
    BUNDLE_DIR = Path(sys._MEIPASS)
else:
    BUNDLE_DIR = Path(__file__).parent

BIN_DIR    = BUNDLE_DIR / "bin"
ASSETS_DIR = BUNDLE_DIR / "assets"


def _platform_data_dir() -> Path:
    """Per-user writable folder that OneDrive / iCloud don't sync.
    Dev runs (not frozen) keep everything next to the code in ./data."""
    if FROZEN:
        if IS_WINDOWS and os.environ.get("LOCALAPPDATA"):
            return Path(os.environ["LOCALAPPDATA"]) / APP_ID
        if IS_MAC:
            return Path.home() / "Library" / "Application Support" / APP_ID
        return Path.home() / f".{APP_ID.lower()}"
    return Path(__file__).parent / "data"


DATA_DIR    = _platform_data_dir()
MODELS_DIR  = DATA_DIR / "models"          # platform default; can be overridden in config
CONFIG_FILE = DATA_DIR / "config.json"
LOG_FILE    = DATA_DIR / "error.log"
SERVER_LOG  = DATA_DIR / "llama-server.log"

# ── Inference settings ───────────────────────────────────────────────────────
CTX_SIZE        = 6144     # tokens; room for ~12k chars of input + a full answer
MAX_INPUT_CHARS = 12000    # longer selections are trimmed (with a notice)
MAX_OUTPUT      = 1024
IDLE_UNLOAD_SEC = 600      # llama-server unloads the model after 10 min unused

# ── Models ───────────────────────────────────────────────────────────────────
# Sizes are the Q4_K_M file sizes on Hugging Face (MB).
AVAILABLE_MODELS = [
    {
        "label": "Standard (recommended)",
        "repo": "unsloth/Qwen3.5-2B-GGUF",
        "filename": "Qwen3.5-2B-Q4_K_M.gguf",
        "size_mb": 1281,
        "note": "Good all-rounder for most laptops",
    },
    {
        "label": "Lite",
        "repo": "LiquidAI/LFM2.5-1.2B-Instruct-GGUF",
        "filename": "LFM2.5-1.2B-Instruct-Q4_K_M.gguf",
        "size_mb": 731,
        "note": "Fastest, for older / low-RAM laptops",
    },
    {
        "label": "Stronger",
        "repo": "unsloth/Qwen3.5-4B-GGUF",
        "filename": "Qwen3.5-4B-Q4_K_M.gguf",
        "size_mb": 2741,
        "note": "Better answers, needs 8 GB+ RAM",
    },
    {
        "label": "Gemma 4 E4B",
        "repo": "unsloth/gemma-4-E4B-it-GGUF",
        "filename": "gemma-4-E4B-it-Q4_K_M.gguf",
        "size_mb": 4977,
        "note": "Most capable, needs 16 GB RAM",
    },
]

DEFAULT_MODEL      = AVAILABLE_MODELS[0]
DEFAULT_MODEL_REPO = DEFAULT_MODEL["repo"]
DEFAULT_MODEL_FILE = DEFAULT_MODEL["filename"]

# Default hotkey — Ctrl+Shift+` avoids browser conflicts (Ctrl+Shift+A opens tab managers)
_DEFAULT_HOTKEY = {"ctrl": True, "shift": True, "alt": False, "key": "`"}


# ── Config file ──────────────────────────────────────────────────────────────

_cache: dict | None = None


def _legacy_config_file() -> Path | None:
    """v1 kept config.json next to the exe. If v2 was extracted over a v1
    install, that file holds the student's hotkey, junior mode, chosen model
    and any custom models folder."""
    if not FROZEN:
        return None
    p = Path(sys.executable).parent / "config.json"
    return p if p.exists() else None


def load_config() -> dict:
    global _cache
    if _cache is None:
        src = CONFIG_FILE if CONFIG_FILE.exists() else _legacy_config_file()
        try:
            with open(src, "r", encoding="utf-8") as f:
                _cache = json.load(f)
        except (TypeError, OSError, json.JSONDecodeError):
            _cache = {}
    return dict(_cache)


def save_config(data: dict) -> None:
    global _cache
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, CONFIG_FILE)
    _cache = dict(data)


def _set(key: str, value) -> None:
    cfg = load_config()
    if value is None:
        cfg.pop(key, None)
    else:
        cfg[key] = value
    save_config(cfg)


def reset_config() -> None:
    global _cache
    try:
        CONFIG_FILE.unlink(missing_ok=True)
    except OSError:
        pass
    _cache = None


# ── Hotkey ───────────────────────────────────────────────────────────────────

def get_hotkey() -> dict:
    return load_config().get("hotkey", _DEFAULT_HOTKEY.copy())


def set_hotkey(h: dict) -> None:
    _set("hotkey", h)


def get_hotkey_pynput(h: dict | None = None) -> str:
    """Return the hotkey in pynput GlobalHotKeys format, e.g. '<ctrl>+<shift>+`'."""
    h = h or get_hotkey()
    parts = []
    if h.get("ctrl"):  parts.append("<ctrl>")
    if h.get("shift"): parts.append("<shift>")
    if h.get("alt"):   parts.append("<alt>")
    parts.append(h.get("key", "`"))
    return "+".join(parts)


def get_hotkey_display(h: dict | None = None) -> str:
    """Return a human-readable hotkey string, e.g. 'Ctrl + Shift + `'."""
    h = h or get_hotkey()
    parts = []
    if h.get("ctrl"):  parts.append("Ctrl")
    if h.get("shift"): parts.append("Shift")
    if h.get("alt"):   parts.append("Alt")
    key = h.get("key", "`")
    parts.append(key.upper() if len(key) == 1 else key)
    return " + ".join(parts)


# ── Models folder / active model ─────────────────────────────────────────────

def get_models_dir() -> Path:
    override = load_config().get("models_dir")
    return Path(override) if override else MODELS_DIR


def set_models_dir(path: Path | None) -> None:
    _set("models_dir", str(path) if path else None)


def get_active_model() -> str:
    return load_config().get("active_model", DEFAULT_MODEL_FILE)


def set_active_model(filename: str) -> None:
    _set("active_model", filename)


# ── GPU ──────────────────────────────────────────────────────────────────────
# "auto": try the graphics chip (Vulkan on Windows, Metal on Mac), fall back to
# CPU if it fails. "off": CPU only. A failed GPU start is remembered.

def get_gpu_mode() -> str:
    return load_config().get("gpu_mode", "auto")


def set_gpu_mode(mode: str) -> None:
    _set("gpu_mode", mode)
    _set("gpu_failed", None)


def gpu_failed() -> bool:
    return load_config().get("gpu_failed", False)


def mark_gpu_failed() -> None:
    _set("gpu_failed", True)


# ── Misc flags ───────────────────────────────────────────────────────────────

def is_junior_mode() -> bool:
    return load_config().get("junior_mode", False)


def set_junior_mode(value: bool) -> None:
    _set("junior_mode", bool(value))


def is_first_run() -> bool:
    return not load_config().get("welcomed", False)


def mark_welcomed() -> None:
    _set("welcomed", True)


def log(msg: str) -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(msg.rstrip() + "\n")
    except Exception:
        pass

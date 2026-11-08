"""
Local AI engine — runs llama.cpp's `llama-server` as a small background process.

Why a separate process instead of an in-process Python binding:
  * Official llama.cpp builds pick the fastest CPU instructions at runtime
    (AVX2/AVX-512 on modern laptops, SSE fallback on old ones).
  * The Windows build includes Vulkan, so Intel/AMD integrated graphics can
    take load off the CPU. Macs use Metal.
  * New model families are supported as soon as llama.cpp supports them.
  * `--sleep-idle-seconds` unloads the model from RAM when it hasn't been used
    for a while, and the server is only started when the student first uses
    the hotkey — so the app costs almost nothing while sitting in the tray.

The server only listens on 127.0.0.1 on a random free port.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Iterator

import requests

import config
from config import (BIN_DIR, CTX_SIZE, IDLE_UNLOAD_SEC, IS_WINDOWS,
                    MAX_INPUT_CHARS, MAX_OUTPUT, SERVER_LOG)

_EXE_NAME = "llama-server.exe" if IS_WINDOWS else "llama-server"
_START_TIMEOUT = 180  # seconds — slow hard drives can take a while to load a model

_lock = threading.RLock()
_proc: subprocess.Popen | None = None
_port: int | None = None
_model: str | None = None
_job = None  # Windows job handle (kills the server if the app dies)
_session = requests.Session()


class EngineError(RuntimeError):
    pass


# ── Helpers ──────────────────────────────────────────────────────────────────

def server_exe() -> Path:
    exe = BIN_DIR / _EXE_NAME
    if not exe.exists():
        raise EngineError(
            f"The AI engine is missing ({exe}).\n"
            "If running from source, run:  python scripts/fetch_llama_server.py"
        )
    if not IS_WINDOWS and not os.access(exe, os.X_OK):
        try:
            exe.chmod(exe.stat().st_mode | 0o755)
        except OSError:
            pass
    return exe


def resolve_model() -> str | None:
    """Return the model file to use: the chosen one if present, else any local model."""
    d = config.get_models_dir()
    active = config.get_active_model()
    if (d / active).exists():
        return active
    if (d / config.DEFAULT_MODEL_FILE).exists():
        return config.DEFAULT_MODEL_FILE
    from model_manager import list_local_models
    found = list_local_models()
    return found[0].name if found else None


def trim_input(text: str) -> tuple[str, bool]:
    """Keep selections within the context window. Returns (text, was_trimmed)."""
    text = text.strip()
    if len(text) <= MAX_INPUT_CHARS:
        return text, False
    cut = text[:MAX_INPUT_CHARS]
    # Prefer ending at a sentence / paragraph boundary
    for sep in ("\n\n", ". ", "\n"):
        i = cut.rfind(sep)
        if i > MAX_INPUT_CHARS * 0.8:
            cut = cut[: i + len(sep)]
            break
    return cut.rstrip(), True


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _server_args(model_path: Path, port: int, use_gpu: bool) -> list[str]:
    args = [
        str(server_exe()),
        "--model", str(model_path),
        "--host", "127.0.0.1",
        "--port", str(port),
        "--ctx-size", str(CTX_SIZE),
        "--parallel", "1",
        "--cache-ram", "0",
        "--sleep-idle-seconds", str(IDLE_UNLOAD_SEC),
        "--reasoning-budget", "0",     # no hidden "thinking" — answer straight away
        "--no-webui",
        "--no-warmup",
    ]
    if use_gpu:
        args += ["--n-gpu-layers", "all"]
    else:
        args += ["--device", "none", "--n-gpu-layers", "0"]
    return args


def _tail_log(n: int = 15) -> str:
    try:
        lines = SERVER_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-n:])
    except OSError:
        return ""


def _attach_kill_on_close_job(proc: subprocess.Popen):
    """Windows: tie the server's lifetime to ours, so a crash never leaves it running."""
    import ctypes
    from ctypes import wintypes

    class BASIC(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                    ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t),
                    ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class IO(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint64) for n in (
            "Read", "Write", "Other", "ReadBytes", "WriteBytes", "OtherBytes")]

    class EXTENDED(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", BASIC),
                    ("IoInfo", IO),
                    ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                            ctypes.c_void_p, wintypes.DWORD]
    k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]

    job = k32.CreateJobObjectW(None, None)
    if not job:
        return None
    info = EXTENDED()
    info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))
    k32.AssignProcessToJobObject(job, wintypes.HANDLE(int(proc._handle)))
    return job


# ── Process lifecycle ────────────────────────────────────────────────────────

def _launch(model_file: str, use_gpu: bool) -> None:
    global _proc, _port, _model, _job
    model_path = config.get_models_dir() / model_file
    port = _free_port()
    args = _server_args(model_path, port, use_gpu)

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    log_f = open(SERVER_LOG, "w", encoding="utf-8", errors="replace")
    kwargs: dict = dict(stdin=subprocess.DEVNULL, stdout=log_f, stderr=subprocess.STDOUT,
                        cwd=str(BIN_DIR))
    if IS_WINDOWS:
        CREATE_NO_WINDOW = 0x08000000
        BELOW_NORMAL_PRIORITY_CLASS = 0x00004000  # keep the student's other apps snappy
        kwargs["creationflags"] = CREATE_NO_WINDOW | BELOW_NORMAL_PRIORITY_CLASS
    else:
        kwargs["start_new_session"] = True
        kwargs["preexec_fn"] = lambda: os.nice(5)

    proc = subprocess.Popen(args, **kwargs)
    log_f.close()
    if IS_WINDOWS:
        try:
            _job = _attach_kill_on_close_job(proc)
        except Exception as e:  # never fatal
            config.log(f"[engine] job object: {e}")

    deadline = time.time() + _START_TIMEOUT
    url = f"http://127.0.0.1:{port}/health"
    while time.time() < deadline:
        if proc.poll() is not None:
            raise EngineError(f"AI engine exited (code {proc.returncode}).\n{_tail_log()}")
        try:
            r = _session.get(url, timeout=1)
            if r.status_code == 200:
                _proc, _port, _model = proc, port, model_file
                return
        except requests.RequestException:
            pass
        time.sleep(0.25)
    proc.kill()
    raise EngineError("The AI engine took too long to start.")


def _stop_locked() -> None:
    global _proc, _port, _model, _job
    if _proc is not None and _proc.poll() is None:
        _proc.terminate()
        try:
            _proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _proc.kill()
    _proc = _port = _model = None
    if _job is not None:
        try:
            import ctypes
            ctypes.windll.kernel32.CloseHandle(_job)
        except Exception:
            pass
        _job = None


def ensure_running() -> None:
    """Start (or restart) the server with the active model. Blocks until ready."""
    with _lock:
        target = resolve_model()
        if target is None:
            raise EngineError("No AI model found. Open Settings to download one.")
        if _proc is not None and _proc.poll() is None and _model == target:
            return
        _stop_locked()

        want_gpu = config.get_gpu_mode() == "auto" and not config.gpu_failed()
        if want_gpu:
            try:
                _launch(target, use_gpu=True)
                return
            except EngineError as e:
                config.log(f"[engine] GPU start failed, falling back to CPU: {e}")
                config.mark_gpu_failed()
                _stop_locked()
        _launch(target, use_gpu=False)


def warm_up() -> None:
    """Start the server in the background (called when the hotkey menu opens)."""
    def _run():
        try:
            ensure_running()
        except Exception as e:
            config.log(f"[engine] warm-up: {e}")
    threading.Thread(target=_run, daemon=True).start()


def is_ready() -> bool:
    return _proc is not None and _proc.poll() is None


def switch_model(model_filename: str) -> None:
    config.set_active_model(model_filename)
    with _lock:
        if _proc is not None:
            _stop_locked()


def restart() -> None:
    """Stop the server; the next request starts it with current settings."""
    with _lock:
        _stop_locked()


def shutdown() -> None:
    with _lock:
        _stop_locked()


# ── Requests ─────────────────────────────────────────────────────────────────

def _payload(system_prompt: str, user_text: str, max_tokens: int, **extra) -> dict:
    return {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.4,
        "top_p": 0.9,
        "chat_template_kwargs": {"enable_thinking": False},
        **extra,
    }


def _post(payload: dict, stream: bool) -> requests.Response:
    ensure_running()
    try:
        r = _session.post(f"http://127.0.0.1:{_port}/v1/chat/completions",
                          json=payload, stream=stream, timeout=(5, 600))
    except requests.ConnectionError:
        # Server died between requests — restart once and retry
        restart()
        ensure_running()
        r = _session.post(f"http://127.0.0.1:{_port}/v1/chat/completions",
                          json=payload, stream=stream, timeout=(5, 600))
    if r.status_code != 200:
        try:
            msg = r.json().get("error", {}).get("message", r.text)
        except ValueError:
            msg = r.text
        raise EngineError(f"AI engine error: {msg[:300]}")
    # The streaming response has no charset header, so requests would assume
    # Latin-1 and turn "•" into "â€¢". llama-server always sends UTF-8.
    r.encoding = "utf-8"
    return r


def parse_sse_line(line: str) -> str | None:
    """Return the text delta from one server-sent-events line, '' for none, None at end."""
    if not line.startswith("data:"):
        return ""
    data = line[5:].strip()
    if data == "[DONE]":
        return None
    try:
        obj = json.loads(data)
    except ValueError:
        return ""
    choices = obj.get("choices") or [{}]
    return (choices[0].get("delta") or {}).get("content") or ""


def complete(system_prompt: str, user_text: str, *, max_tokens: int = MAX_OUTPUT,
             cancel: threading.Event | None = None) -> Iterator[str]:
    """Stream a reply. Set `cancel` to stop generation early (frees the CPU)."""
    r = _post(_payload(system_prompt, user_text, max_tokens, stream=True), stream=True)
    try:
        for raw in r.iter_lines(decode_unicode=True):
            if cancel is not None and cancel.is_set():
                return
            if not raw:
                continue
            delta = parse_sse_line(raw)
            if delta is None:
                return
            if delta:
                yield delta
    finally:
        r.close()  # closing the connection makes llama-server stop generating


def complete_json(system_prompt: str, user_text: str, schema: dict, *,
                  max_tokens: int = MAX_OUTPUT) -> dict:
    """Get a reply that is guaranteed to match `schema` (grammar-constrained)."""
    payload = _payload(system_prompt, user_text, max_tokens,
                       response_format={"type": "json_schema",
                                        "json_schema": {"name": "result", "schema": schema}})
    r = _post(payload, stream=False)
    content = r.json()["choices"][0]["message"]["content"]
    return json.loads(content)

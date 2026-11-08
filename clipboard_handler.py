import platform
import time

import pyperclip
from pynput.keyboard import Controller, Key

_keyboard = Controller()
# macOS copies with Cmd+C, not Ctrl+C
_COPY_MOD = Key.cmd if platform.system() == "Darwin" else Key.ctrl


def _safe_get_clipboard() -> str:
    try:
        return pyperclip.paste() or ""
    except Exception:
        return ""


def _safe_set_clipboard(text: str) -> None:
    try:
        pyperclip.copy(text)
    except Exception:
        pass


def get_selected_text() -> tuple[str, bool]:
    """
    Capture highlighted text by simulating a copy.
    Falls back to whatever is already on the clipboard (for PDFs/Adobe Reader
    where focus loss deselects text before the copy can fire).

    Returns (text, used_fallback).
    """
    pre_existing = _safe_get_clipboard()

    # Clear clipboard so we can tell whether the copy actually captured anything
    _safe_set_clipboard("")
    time.sleep(0.05)

    with _keyboard.pressed(_COPY_MOD):
        _keyboard.press("c")
        _keyboard.release("c")

    # Poll briefly instead of one fixed sleep — fast apps return sooner
    captured = ""
    for _ in range(8):
        time.sleep(0.05)
        captured = _safe_get_clipboard().strip()
        if captured:
            break

    if captured:
        if pre_existing:
            _safe_set_clipboard(pre_existing)  # leave the student's clipboard as it was
        return captured, False

    if pre_existing.strip():
        _safe_set_clipboard(pre_existing)
        return pre_existing.strip(), True

    return "", False

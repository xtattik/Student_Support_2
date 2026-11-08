import threading
from pynput import keyboard
from config import get_hotkey_pynput

_listener = None
_callback = None


def start(callback: callable) -> None:
    global _listener, _callback
    _callback = callback
    _listener = _make_listener(callback)
    _listener.start()


def restart() -> None:
    """Re-register the hotkey using the current value from config (called after settings change)."""
    global _listener
    if _listener is not None:
        _listener.stop()
        _listener = None
    if _callback is not None:
        _listener = _make_listener(_callback)
        _listener.start()


def stop() -> None:
    global _listener
    if _listener is not None:
        _listener.stop()
        _listener = None


def _make_listener(callback: callable) -> keyboard.GlobalHotKeys:
    def _on_trigger():
        threading.Thread(target=callback, daemon=True).start()

    hotkey_str = get_hotkey_pynput()
    return keyboard.GlobalHotKeys({hotkey_str: _on_trigger})

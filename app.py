import atexit
import sys
import threading
import traceback

import customtkinter as ctk

import config
import hotkey_listener
import llm_engine
import mathfmt
import single_instance
from clipboard_handler import get_selected_text
from config import get_hotkey_display, is_first_run, is_junior_mode
from first_run_wizard import FirstRunWizard
from model_manager import has_any_model
from overlay import OverlayWindow
from prompts import get_prompts
from system_tray import TrayIcon
from theme import set_window_icon
from ui.result_window import ResultWindow
from ui.settings_window import SettingsWindow
from ui.setup_window import SetupWindow
from ui.test_window import TestWindow

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

_root: ctk.CTk | None = None
_overlay: OverlayWindow | None = None
_settings_window = SettingsWindow()


def _on_action(action: str) -> None:
    """Runs on a worker thread (clipboard capture sleeps briefly)."""
    try:
        text, _used_fallback = get_selected_text()
        if not text:
            _show_error(
                "No text selected",
                "Please highlight some text before using the hotkey.\n\n"
                "Tip: In Adobe Reader or PDF viewers, copy the text first, "
                f"then press {get_hotkey_display()}.",
            )
            return

        text, trimmed = llm_engine.trim_input(text)
        junior = is_junior_mode()
        p = get_prompts(junior=junior)

        def _open():
            try:
                if action == "test_me":
                    win = TestWindow(source_text=text, quiz_prompt=p["test_me"],
                                     junior=junior, trimmed=trimmed)
                else:
                    win = ResultWindow(action, p[action], source_text=text,
                                       simplify_prompt=p["simplify"], trimmed=trimmed)
                win.show()
            except Exception:
                err = traceback.format_exc()
                config.log(f"[_open] {err}")
                _show_error("Error", f"Could not open result window:\n{err[-300:]}")

        _root.after(0, _open)

    except Exception:
        err = traceback.format_exc()
        config.log(f"[_on_action:{action}] {err}")
        _show_error("Error", f"Something went wrong:\n{err[-300:]}")


def _on_hotkey() -> None:
    # Start the engine while the student picks an option — hides most of the start-up time
    llm_engine.warm_up()
    _root.after(0, _overlay.show)


def _show_error(title: str, message: str) -> None:
    def _open():
        win = ctk.CTkToplevel(_root)
        win.title(title)
        win.geometry("380x170")
        win.attributes("-topmost", True)
        win.after(200, lambda: set_window_icon(win))
        ctk.CTkLabel(win, text=message, wraplength=340, justify="center").pack(expand=True)
        ctk.CTkButton(win, text="OK", command=win.destroy).pack(pady=(0, 16))
    _root.after(0, _open)


def _launch_app() -> None:
    global _root, _overlay

    _root = ctk.CTk()
    _root.withdraw()

    _overlay = OverlayWindow(
        on_action=lambda a: threading.Thread(target=_on_action, args=(a,), daemon=True).start()
    )

    tray = TrayIcon(on_settings=lambda: _root.after(0, _settings_window.show),
                    on_quit=_quit)
    tray.start()

    hotkey_listener.start(_on_hotkey)

    # No model preload: the engine starts on first hotkey press and unloads
    # itself after a period of inactivity, so the app is light when idle.

    if is_first_run():
        _root.after(1500, lambda: FirstRunWizard(_root).show())
        # First launch only: build the equation renderer's font cache (~10 s) in the
        # background now, so the first maths answer isn't slowed down by it.
        _root.after(4000, mathfmt.preload)

    _root.mainloop()


def _quit() -> None:
    hotkey_listener.stop()
    llm_engine.shutdown()
    _root.after(0, _root.quit)


def main() -> None:
    if not single_instance.acquire():
        import tkinter as tk
        import tkinter.messagebox as mb
        r = tk.Tk()
        r.withdraw()
        mb.showinfo("Already running",
                    f"{config.APP_NAME} is already running.\n\nFind it in the system tray.")
        r.destroy()
        sys.exit(0)

    atexit.register(llm_engine.shutdown)

    if not has_any_model():
        def _fail(e):
            config.log(f"[setup] download failed: {e}")
            sys.exit(1)
        SetupWindow(on_complete=_launch_app, on_error=_fail).show()
    else:
        _launch_app()


if __name__ == "__main__":
    main()

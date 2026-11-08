import platform
import threading
import webbrowser

import pystray

import updater
from config import APP_NAME, HELP_URL, get_hotkey_display, is_junior_mode, set_junior_mode
from theme import load_logo_pil


class TrayIcon:
    def __init__(self, on_settings: callable, on_quit: callable):
        self._on_settings = on_settings
        self._on_quit = on_quit
        self._icon = None

    def start(self) -> None:
        try:
            img = load_logo_pil((64, 64))
        except Exception:
            from PIL import Image, ImageDraw
            img = Image.new("RGB", (64, 64), color=(13, 107, 122))
            ImageDraw.Draw(img).text((18, 18), "AI", fill=(255, 255, 255))

        menu = pystray.Menu(
            pystray.MenuItem("Junior mode", self._toggle_junior,
                             checked=lambda _: is_junior_mode()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Settings", lambda: self._on_settings()),
            pystray.MenuItem("Help", lambda: webbrowser.open(HELP_URL)),
            pystray.MenuItem("Check for updates", self._check_updates_tray),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", lambda: self._quit()),
        )
        icon_kwargs = {}
        if platform.system() == "Darwin":
            import AppKit  # type: ignore[import]
            icon_kwargs["darwin_nsapplication"] = AppKit.NSApplication.sharedApplication()

        self._icon = pystray.Icon(
            "StudentAI", img,
            f"{APP_NAME}\nHighlight text, then press {get_hotkey_display()}",
            menu, **icon_kwargs,
        )
        # run_detached keeps AppKit on the main thread on macOS (see v1 crash log)
        self._icon.run_detached()

    def _check_updates_tray(self) -> None:
        def _run():
            result = updater.check()
            webbrowser.open(result["url"] if result["status"] == "update_available"
                            else updater.RELEASES_URL)
        threading.Thread(target=_run, daemon=True).start()

    def _toggle_junior(self) -> None:
        set_junior_mode(not is_junior_mode())

    def _quit(self) -> None:
        if self._icon:
            self._icon.stop()
        self._on_quit()

    def stop(self) -> None:
        if self._icon:
            self._icon.stop()

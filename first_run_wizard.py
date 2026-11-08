"""
First-run welcome wizard — shown once after a fresh install.
Offers a desktop shortcut and launch-at-login option.
"""
import sys
import platform
import subprocess
from pathlib import Path
import customtkinter as ctk
from theme import TEAL, TEAL_HOVER, CHARCOAL, WHITE, set_window_icon
from config import mark_welcomed


class FirstRunWizard:
    def __init__(self, root):
        self._root = root

    def show(self) -> None:
        win = ctk.CTkToplevel(self._root)
        win.title("Welcome!")
        win.geometry("420x310")
        win.attributes("-topmost", True)
        win.resizable(False, False)
        win.after(200, lambda: set_window_icon(win))

        header = ctk.CTkFrame(win, fg_color=TEAL, height=44, corner_radius=0)
        header.pack(fill="x")
        header.pack_propagate(False)
        ctk.CTkLabel(
            header, text="Student AI Support is ready!",
            font=ctk.CTkFont(size=15, weight="bold"), text_color=WHITE,
        ).pack(side="left", padx=16, pady=10)

        ctk.CTkLabel(
            win,
            text="Would you like a couple of quick shortcuts?",
            font=ctk.CTkFont(size=13),
            text_color=CHARCOAL,
        ).pack(pady=(18, 10))

        options = ctk.CTkFrame(win, fg_color="transparent")
        options.pack(padx=40, fill="x")

        self._shortcut_var = ctk.BooleanVar(value=True)
        self._startup_var  = ctk.BooleanVar(value=False)

        ctk.CTkCheckBox(
            options, text="Create a shortcut on my Desktop",
            variable=self._shortcut_var,
            fg_color=TEAL, hover_color=TEAL_HOVER, checkmark_color=WHITE,
        ).pack(anchor="w", pady=5)

        ctk.CTkCheckBox(
            options, text="Launch automatically when I log in",
            variable=self._startup_var,
            fg_color=TEAL, hover_color=TEAL_HOVER, checkmark_color=WHITE,
        ).pack(anchor="w", pady=5)

        self._status = ctk.CTkLabel(win, text="", text_color="gray", font=ctk.CTkFont(size=11))
        self._status.pack(pady=(8, 0))

        ctk.CTkButton(
            win, text="Done",
            fg_color=TEAL, hover_color=TEAL_HOVER, text_color=WHITE,
            width=120,
            command=lambda: self._finish(win),
        ).pack(pady=14)

    def _finish(self, win) -> None:
        mark_welcomed()
        if self._shortcut_var.get():
            ok, msg = create_shortcut()
            if not ok:
                self._status.configure(text=f"Shortcut: {msg}", text_color="orange")
        if self._startup_var.get():
            ok, msg = set_startup(True)
            if not ok:
                self._status.configure(text=f"Startup: {msg}", text_color="orange")
        win.destroy()


# ── Shortcut creation ──────────────────────────────────────────────────────────

def delete_shortcut() -> None:
    """Remove the Desktop shortcut if it exists. Silent no-op on Mac or dev builds."""
    if not getattr(sys, "frozen", False) or platform.system() != "Windows":
        return
    try:
        ps = (
            '$shell = New-Object -ComObject WScript.Shell; '
            '$lnk = Join-Path ($shell.SpecialFolders("Desktop")) "Student AI Support.lnk"; '
            'if (Test-Path $lnk) { Remove-Item $lnk -Force }'
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, creationflags=0x08000000)
    except Exception:
        pass  # shortcut deletion is best-effort


def create_shortcut() -> tuple[bool, str]:
    """Create a Desktop shortcut. Returns (success, message)."""
    if not getattr(sys, "frozen", False):
        return False, "Only works in packaged build"
    try:
        if platform.system() == "Windows":
            _shortcut_windows()
        # macOS: users drag .app to Applications — nothing to do
        return True, "Done"
    except Exception as e:
        return False, str(e)


def _shortcut_windows() -> None:
    exe = Path(sys.executable)
    # Use WScript.Shell.SpecialFolders so we find the real Desktop even when
    # OneDrive has redirected it (Path.home()/Desktop is often wrong on school PCs)
    ps = (
        '$shell = New-Object -ComObject WScript.Shell; '
        '$lnk = Join-Path ($shell.SpecialFolders("Desktop")) "Student AI Support.lnk"; '
        f'$s = $shell.CreateShortcut($lnk); '
        f'$s.TargetPath = "{exe}"; '
        f'$s.WorkingDirectory = "{exe.parent}"; '
        f'$s.IconLocation = "{exe}"; '
        '$s.Save()'
    )
    result = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, creationflags=0x08000000, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "PowerShell shortcut creation failed")


# ── Startup management ─────────────────────────────────────────────────────────

def get_startup_enabled() -> bool:
    """Return True if the app is currently set to launch at login."""
    try:
        if platform.system() == "Windows":
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Run",
                                 0, winreg.KEY_READ)
            try:
                winreg.QueryValueEx(key, "StudentAISupport")
                return True
            except FileNotFoundError:
                return False
            finally:
                winreg.CloseKey(key)
        elif platform.system() == "Darwin":
            plist = Path.home() / "Library" / "LaunchAgents" / "com.mpac.studentai.plist"
            return plist.exists()
    except Exception:
        return False
    return False


def set_startup(enable: bool) -> tuple[bool, str]:
    """Enable or disable launch at login. Returns (success, message)."""
    if not getattr(sys, "frozen", False):
        return False, "Only works in packaged build"
    try:
        if platform.system() == "Windows":
            _startup_windows(enable)
        elif platform.system() == "Darwin":
            _startup_mac(enable)
        else:
            return False, "Not supported on this OS"
        return True, "Done"
    except Exception as e:
        return False, str(e)


def _startup_windows(enable: bool) -> None:
    import winreg
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                         r"Software\Microsoft\Windows\CurrentVersion\Run",
                         0, winreg.KEY_SET_VALUE)
    try:
        if enable:
            winreg.SetValueEx(key, "StudentAISupport", 0,
                              winreg.REG_SZ, str(Path(sys.executable)))
        else:
            try:
                winreg.DeleteValue(key, "StudentAISupport")
            except FileNotFoundError:
                pass
    finally:
        winreg.CloseKey(key)


def _startup_mac(enable: bool) -> None:
    plist_dir  = Path.home() / "Library" / "LaunchAgents"
    plist_path = plist_dir / "com.mpac.studentai.plist"
    exe        = str(Path(sys.executable))
    if enable:
        plist_dir.mkdir(parents=True, exist_ok=True)
        plist_path.write_text(
            f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"'
            f' "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            f'<plist version="1.0"><dict>\n'
            f'  <key>Label</key><string>com.mpac.studentai</string>\n'
            f'  <key>ProgramArguments</key><array><string>{exe}</string></array>\n'
            f'  <key>RunAtLoad</key><true/>\n'
            f'  <key>KeepAlive</key><false/>\n'
            f'</dict></plist>\n'
        )
    else:
        if plist_path.exists():
            plist_path.unlink()

import sys
import platform
import subprocess
import threading
import webbrowser
import tkinter.filedialog as fd
import customtkinter as ctk
from pathlib import Path
from model_manager import list_local_models, download_model, models_dir_size_gb
from config import (AVAILABLE_MODELS, HELP_URL, get_models_dir, set_models_dir,
                    is_junior_mode, set_junior_mode,
                    get_hotkey, set_hotkey, get_hotkey_display,
                    get_gpu_mode, set_gpu_mode, gpu_failed, reset_config)
from theme import TEAL, TEAL_HOVER, LIME_GREEN, SKY_BLUE, CHARCOAL, WHITE, set_window_icon
from first_run_wizard import get_startup_enabled, set_startup, delete_shortcut
from config import VERSION
import updater
import llm_engine
from config import log as config_log


class SettingsWindow:
    def __init__(self):
        self._win: ctk.CTkToplevel | None = None

    def show(self) -> None:
        if self._win is not None:
            self._win.focus_force()
            return

        self._win = ctk.CTkToplevel()
        self._win.title("Settings — Student AI Support")
        self._win.geometry("520x660")
        self._win.resizable(False, True)
        self._win.protocol("WM_DELETE_WINDOW", self._close)
        self._win.after(200, lambda: set_window_icon(self._win))

        # ── Header ────────────────────────────────────────────────────
        header = ctk.CTkFrame(self._win, fg_color=TEAL, height=44, corner_radius=0)
        header.pack(fill="x")
        header.pack_propagate(False)
        ctk.CTkLabel(
            header, text="Settings",
            font=ctk.CTkFont(size=15, weight="bold"), text_color=WHITE,
        ).pack(side="left", padx=16, pady=10)

        ctk.CTkButton(
            header, text="Help", width=60,
            fg_color="transparent", hover_color=TEAL_HOVER, text_color=WHITE,
            border_width=1, border_color=WHITE,
            command=lambda: webbrowser.open(HELP_URL),
        ).pack(side="right", padx=12, pady=8)

        # ── Tabs ──────────────────────────────────────────────────────
        tabs = ctk.CTkTabview(self._win, fg_color="transparent",
                              segmented_button_fg_color=TEAL,
                              segmented_button_selected_color=TEAL_HOVER,
                              segmented_button_selected_hover_color=TEAL_HOVER,
                              segmented_button_unselected_color=TEAL,
                              segmented_button_unselected_hover_color=TEAL_HOVER,
                              text_color=WHITE)
        tabs.pack(fill="both", expand=True, padx=0, pady=0)
        tabs.add("General")
        tabs.add("Advanced")

        self._build_general(tabs.tab("General"))
        self._build_advanced(tabs.tab("Advanced"))

    # ══════════════════════════════════════════════════════════════════
    # General tab
    # ══════════════════════════════════════════════════════════════════

    def _build_general(self, tab) -> None:
        # Scrollable area so nothing gets cut off on small screens
        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=0, pady=0)

        # ── Active model ──────────────────────────────────────────────
        self._section(scroll, "Active Model")
        ctk.CTkLabel(scroll, text="Select a model or download additional ones below.",
                     text_color="gray").pack(padx=20, anchor="w")

        local  = [p.name for p in list_local_models()]
        active = llm_engine.resolve_model() or ""
        self._model_var = ctk.StringVar(value=active if active in local else (local[0] if local else ""))

        self._model_menu = ctk.CTkOptionMenu(
            scroll, values=local or ["No models downloaded"],
            variable=self._model_var, command=self._on_model_select,
            fg_color=TEAL, button_color=TEAL_HOVER,
            button_hover_color=TEAL_HOVER, text_color=WHITE,
        )
        self._model_menu.pack(padx=20, pady=(6, 14), anchor="w")

        # ── Language mode ─────────────────────────────────────────────
        self._section(scroll, "Language Mode")
        mode_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        mode_frame.pack(fill="x", padx=20, pady=(0, 4))

        self._junior_var = ctk.BooleanVar(value=is_junior_mode())
        ctk.CTkSwitch(
            mode_frame, text="Junior mode  (simpler language, ages 9–10)",
            variable=self._junior_var, onvalue=True, offvalue=False,
            fg_color="gray50", progress_color=TEAL,
            command=lambda: set_junior_mode(self._junior_var.get()),
        ).pack(side="left", padx=10, pady=4)

        startup_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        startup_frame.pack(fill="x", padx=20, pady=(0, 12))
        self._startup_var = ctk.BooleanVar(value=get_startup_enabled())
        ctk.CTkSwitch(
            startup_frame, text="Launch at login",
            variable=self._startup_var, onvalue=True, offvalue=False,
            fg_color="gray50", progress_color=TEAL,
            command=lambda: set_startup(self._startup_var.get()),
        ).pack(side="left", padx=10, pady=4)

        # ── Hotkey ────────────────────────────────────────────────────
        self._section(scroll, "Launch Hotkey")
        ctk.CTkLabel(scroll, text="Tick modifiers, type a single key, then Apply.",
                     text_color="gray").pack(padx=20, anchor="w")

        hk_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        hk_frame.pack(fill="x", padx=20, pady=(6, 12))

        h = get_hotkey()
        self._hk_ctrl  = ctk.BooleanVar(value=h.get("ctrl",  True))
        self._hk_shift = ctk.BooleanVar(value=h.get("shift", True))
        self._hk_alt   = ctk.BooleanVar(value=h.get("alt",   False))

        for text, var in [("Ctrl", self._hk_ctrl), ("Shift", self._hk_shift), ("Alt", self._hk_alt)]:
            ctk.CTkCheckBox(hk_frame, text=text, variable=var,
                            fg_color=TEAL, hover_color=TEAL_HOVER,
                            checkmark_color=WHITE).pack(side="left", padx=(0, 8))

        ctk.CTkLabel(hk_frame, text="+", text_color=CHARCOAL).pack(side="left", padx=(0, 6))
        self._hk_key_entry = ctk.CTkEntry(hk_frame, width=44, justify="center")
        self._hk_key_entry.insert(0, h.get("key", "`"))
        self._hk_key_entry.pack(side="left", padx=(0, 10))

        self._hk_status = ctk.CTkLabel(hk_frame, text="", text_color="gray")
        self._hk_status.pack(side="left", padx=(0, 6))
        ctk.CTkButton(hk_frame, text="Apply", width=72,
                      fg_color=TEAL, hover_color=TEAL_HOVER, text_color=WHITE,
                      command=self._apply_hotkey).pack(side="right")

        # ── Download models ───────────────────────────────────────────
        self._section(scroll, "Download Models")
        for m in AVAILABLE_MODELS:
            self._model_row(scroll, m)

        # Close button lives outside the scroll frame so it's always visible
        ctk.CTkButton(tab, text="Close",
                      fg_color=TEAL, hover_color=TEAL_HOVER, text_color=WHITE,
                      command=self._close).pack(pady=(6, 10))

    # ══════════════════════════════════════════════════════════════════
    # Advanced tab
    # ══════════════════════════════════════════════════════════════════

    def _build_advanced(self, tab) -> None:
        # ── Performance ───────────────────────────────────────────────
        self._section(tab, "Performance")
        gpu_note = ("Uses the laptop's graphics chip to take load off the processor.\n"
                    "Turn off if answers are garbled or the app is unstable.")
        if gpu_failed():
            gpu_note += "\n(The graphics chip didn't work last time, so the processor is being used.)"
        ctk.CTkLabel(tab, text=gpu_note, text_color="gray", justify="left"
                     ).pack(padx=20, anchor="w", pady=(0, 4))
        self._gpu_var = ctk.BooleanVar(value=get_gpu_mode() == "auto")
        ctk.CTkSwitch(
            tab, text="Use graphics chip when available",
            variable=self._gpu_var, onvalue=True, offvalue=False,
            fg_color="gray50", progress_color=TEAL,
            command=self._on_gpu_toggle,
        ).pack(padx=30, anchor="w", pady=(0, 8))

        # ── Models folder ─────────────────────────────────────────────
        self._section(tab, "Models Folder")
        ctk.CTkLabel(
            tab,
            text="Any .gguf file placed here is automatically detected.\n"
                 "Point to an existing folder to reuse models across installs.",
            text_color="gray", justify="left",
        ).pack(padx=20, anchor="w", pady=(0, 8))

        path_frame = ctk.CTkFrame(tab, fg_color="transparent")
        path_frame.pack(fill="x", padx=20, pady=(0, 6))

        self._models_path_var = ctk.StringVar(value=str(get_models_dir()))
        ctk.CTkEntry(path_frame, textvariable=self._models_path_var,
                     state="readonly", font=ctk.CTkFont(size=11),
                     ).pack(side="left", fill="x", expand=True, padx=(0, 8))

        btn_frame = ctk.CTkFrame(tab, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(0, 16))

        ctk.CTkButton(btn_frame, text="📁  Open folder", width=130,
                      fg_color=SKY_BLUE, hover_color=TEAL, text_color=WHITE,
                      command=self._open_models_folder).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_frame, text="Change folder…", width=130,
                      fg_color=TEAL, hover_color=TEAL_HOVER, text_color=WHITE,
                      command=self._change_models_folder).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_frame, text="Reset to default", width=130,
                      fg_color="gray", hover_color=TEAL_HOVER, text_color=WHITE,
                      command=self._reset_models_folder).pack(side="left")

        # ── Updates ───────────────────────────────────────────────────
        self._section(tab, "Updates")
        ctk.CTkLabel(
            tab,
            text="To update: download the new zip and extract it over your existing\n"
                 "StudentAI folder. Settings and models are kept automatically.",
            text_color="gray", justify="left",
        ).pack(padx=20, anchor="w", pady=(0, 8))

        update_row = ctk.CTkFrame(tab, fg_color="transparent")
        update_row.pack(fill="x", padx=20, pady=(0, 4))

        self._update_status = ctk.CTkLabel(
            update_row, text=f"Current version: v{VERSION}", text_color="gray",
        )
        self._update_status.pack(side="left")

        ctk.CTkButton(
            update_row, text="Check for updates", width=150,
            fg_color=TEAL, hover_color=TEAL_HOVER, text_color=WHITE,
            command=self._check_updates,
        ).pack(side="right")

        # ── Uninstall ─────────────────────────────────────────────────
        self._section(tab, "Uninstall")
        ctk.CTkLabel(
            tab,
            text="Removes settings and optionally deletes downloaded model files.\n"
                 "You will need to delete the app folder / .app manually afterwards.",
            text_color="gray", justify="left",
        ).pack(padx=20, anchor="w", pady=(0, 10))

        ctk.CTkButton(tab, text="Uninstall Student AI Support…",
                      fg_color="#C0392B", hover_color="#96281B", text_color=WHITE,
                      command=self._uninstall).pack(padx=20, anchor="w")

    # ══════════════════════════════════════════════════════════════════
    # Helpers
    # ══════════════════════════════════════════════════════════════════

    def _section(self, parent, text: str) -> None:
        ctk.CTkLabel(parent, text=text,
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=TEAL).pack(padx=20, pady=(14, 2), anchor="w")

    def _model_row(self, parent, model_info: dict) -> None:
        from config import get_models_dir
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", padx=20, pady=3)

        dest = get_models_dir() / model_info["filename"]
        status_label = ctk.CTkLabel(frame, text="", width=80, text_color="gray")
        status_label.pack(side="right", padx=(0, 6))

        if dest.exists():
            status_label.configure(text="Downloaded", text_color=LIME_GREEN)
        else:
            btn = ctk.CTkButton(
                frame, text="Download", width=90,
                fg_color=TEAL, hover_color=TEAL_HOVER, text_color=WHITE,
            )
            btn.configure(command=lambda m=model_info, lbl=status_label, b=btn:
                          self._start_download(m, lbl, b))
            btn.pack(side="right", padx=(0, 6), pady=4)

        label_text = f"{model_info['label']}  ·  {model_info['size_mb'] / 1000:.1f} GB"
        if model_info["note"]:
            label_text += f"\n{model_info['note']}"
        ctk.CTkLabel(frame, text=label_text, anchor="w", justify="left",
                     text_color=CHARCOAL).pack(side="left", padx=10, pady=6, expand=True, fill="x")

    def _ui(self, fn) -> None:
        """Run fn on the Tk thread (widgets must not be touched from workers)."""
        if self._win is not None:
            try:
                self._win.after(0, fn)
            except Exception:
                pass

    def _start_download(self, model_info: dict, status_label: ctk.CTkLabel, btn) -> None:
        btn.pack_forget()
        status_label.configure(text="Starting…", text_color="gray")

        def _progress(done, total):
            self._ui(lambda: status_label.configure(text=f"{done / total:.0%}"))

        def _run():
            try:
                download_model(model_info["repo"], model_info["filename"], _progress)
                self._ui(lambda: (status_label.configure(text="Downloaded", text_color=LIME_GREEN),
                                  self._refresh_model_menu()))
            except Exception as e:
                config_log(f"[settings] download failed: {e}")
                self._ui(lambda: (status_label.configure(text="Failed — retry", text_color="red"),
                                  btn.pack(side="right", padx=(0, 6), pady=4)))
        threading.Thread(target=_run, daemon=True).start()

    def _refresh_model_menu(self) -> None:
        local = [p.name for p in list_local_models()]
        self._model_menu.configure(values=local or ["No models downloaded"])
        if local and self._model_var.get() not in local:
            self._model_var.set(local[0])

    def _on_model_select(self, value: str) -> None:
        if value.endswith(".gguf"):
            llm_engine.switch_model(value)

    def _on_gpu_toggle(self) -> None:
        set_gpu_mode("auto" if self._gpu_var.get() else "off")
        llm_engine.restart()

    def _apply_hotkey(self) -> None:
        import hotkey_listener
        key = self._hk_key_entry.get().strip()
        if len(key) != 1:
            self._hk_status.configure(text="Type exactly 1 key", text_color="red")
            return
        if not (self._hk_ctrl.get() or self._hk_shift.get() or self._hk_alt.get()):
            self._hk_status.configure(text="Pick at least one modifier", text_color="red")
            return
        h = {"ctrl": self._hk_ctrl.get(), "shift": self._hk_shift.get(),
             "alt": self._hk_alt.get(), "key": key}
        set_hotkey(h)
        hotkey_listener.restart()
        self._hk_status.configure(text=f"Active: {get_hotkey_display(h)}", text_color=LIME_GREEN)

    # ── Advanced: update check ────────────────────────────────────────────────

    def _check_updates(self) -> None:
        self._update_status.configure(text="Checking…", text_color="gray")
        self._update_status.unbind("<Button-1>")

        def _run():
            result = updater.check()

            def _show():
                if result["status"] == "update_available":
                    self._update_status.configure(
                        text=result["message"], text_color=LIME_GREEN, cursor="hand2",
                    )
                    self._update_status.bind(
                        "<Button-1>", lambda _: webbrowser.open(result["url"])
                    )
                elif result["status"] == "up_to_date":
                    self._update_status.configure(
                        text=result["message"], text_color=LIME_GREEN, cursor="",
                    )
                else:
                    self._update_status.configure(
                        text=result["message"], text_color="orange", cursor="",
                    )

            if self._win:
                self._win.after(0, _show)

        threading.Thread(target=_run, daemon=True).start()

    # ── Advanced: models folder ────────────────────────────────────────────────

    def _open_models_folder(self) -> None:
        path = Path(self._models_path_var.get())
        path.mkdir(parents=True, exist_ok=True)
        if platform.system() == "Windows":
            subprocess.run(["explorer", str(path)])
        elif platform.system() == "Darwin":
            subprocess.run(["open", str(path)])

    def _change_models_folder(self) -> None:
        chosen = fd.askdirectory(title="Choose models folder", mustexist=False)
        if not chosen:
            return
        p = Path(chosen)
        set_models_dir(p)
        self._models_path_var.set(str(p))

    def _reset_models_folder(self) -> None:
        set_models_dir(None)
        from config import MODELS_DIR
        self._models_path_var.set(str(MODELS_DIR))

    # ── Uninstall ──────────────────────────────────────────────────────────────

    def _uninstall(self) -> None:
        dlg = ctk.CTkToplevel(self._win)
        dlg.title("Uninstall Student AI Support")
        dlg.geometry("420x300")
        dlg.attributes("-topmost", True)
        dlg.resizable(False, False)
        dlg.after(200, lambda: set_window_icon(dlg))

        ctk.CTkLabel(dlg, text="Uninstall Student AI Support",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color="#C0392B").pack(pady=(20, 8))

        # Work out model size for the checkbox label
        try:
            size_gb = models_dir_size_gb()
            size_str = f"  (~{size_gb:.1f} GB)" if size_gb > 0 else ""
        except Exception:
            size_str = ""

        delete_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            dlg,
            text=f"Delete downloaded AI models{size_str}",
            variable=delete_var,
            fg_color="#C0392B", hover_color="#96281B", checkmark_color=WHITE,
        ).pack(padx=30, anchor="w", pady=4)

        ctk.CTkLabel(
            dlg,
            text="After uninstalling, delete the StudentAI folder\n"
                 "(or StudentAI.app on Mac) to finish removal.\n\n"
                 "You will need to re-download models if you reinstall.",
            text_color="gray", justify="center",
        ).pack(pady=(8, 12))

        btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_row.pack()
        ctk.CTkButton(btn_row, text="Cancel", fg_color="gray", hover_color=TEAL_HOVER,
                      text_color=WHITE, width=100,
                      command=dlg.destroy).pack(side="left", padx=8)
        ctk.CTkButton(btn_row, text="Uninstall", fg_color="#C0392B", hover_color="#96281B",
                      text_color=WHITE, width=100,
                      command=lambda: self._do_uninstall(dlg, delete_var.get()),
                      ).pack(side="left", padx=8)

    def _do_uninstall(self, dlg: ctk.CTkToplevel, delete_models: bool) -> None:
        import shutil

        # Stop the AI engine first — on Windows it holds the model file open
        llm_engine.shutdown()

        # Remove startup entry and desktop shortcut
        set_startup(False)
        delete_shortcut()

        # Delete models if requested
        if delete_models:
            models_path = get_models_dir()
            try:
                shutil.rmtree(models_path, ignore_errors=True)
            except Exception:
                pass

        reset_config()

        dlg.destroy()

        # Show "done" message then quit
        final = ctk.CTkToplevel(self._win)
        final.title("Uninstalled")
        final.geometry("380x180")
        final.attributes("-topmost", True)
        final.after(200, lambda: set_window_icon(final))
        ctk.CTkLabel(final, text="Student AI Support has been uninstalled.",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=TEAL).pack(pady=(24, 8))
        ctk.CTkLabel(final,
                     text="You can now delete the StudentAI folder\n(or StudentAI.app on Mac).",
                     text_color=CHARCOAL, justify="center").pack()

        def _open_folder_and_quit():
            self._open_app_folder()
            import os as _os
            _os._exit(0)  # hard exit — releases the exe lock so Windows can delete the folder

        ctk.CTkButton(final, text="Show app folder & Quit",
                      fg_color=TEAL, hover_color=TEAL_HOVER, text_color=WHITE,
                      command=_open_folder_and_quit).pack(pady=16)

    def _open_app_folder(self) -> None:
        folder = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path.cwd()
        if platform.system() == "Windows":
            subprocess.run(["explorer", str(folder)])
        elif platform.system() == "Darwin":
            subprocess.run(["open", str(folder)])

    def _close(self) -> None:
        if self._win:
            self._win.destroy()
            self._win = None

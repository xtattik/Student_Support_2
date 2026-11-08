import sys
import threading
import tkinter.filedialog as fd
from pathlib import Path

import customtkinter as ctk

from config import AVAILABLE_MODELS, get_models_dir, set_active_model, set_models_dir
from model_manager import download_model, list_local_models
from theme import CHARCOAL, SKY_BLUE, TEAL, TEAL_HOVER, WHITE, load_logo, set_window_icon

# Only the two lighter models are offered at first setup; others are in Settings
_CHOICES = {f"{m['label']} — {m['size_mb'] / 1000:.1f} GB": m for m in AVAILABLE_MODELS[:2]}


class SetupWindow:
    """Shown on first launch when no model is present.
    Lets the user pick a model and folder, detects existing models, downloads
    (resumable) if needed, then calls on_complete."""

    def __init__(self, on_complete: callable, on_error: callable):
        self._on_complete = on_complete
        self._on_error = on_error
        self._done = False
        self._error = None
        self._cancel = threading.Event()

    def show(self) -> None:
        self._win = ctk.CTk()
        self._win.title("Student AI Support — First Time Setup")
        self._win.geometry("520x430")
        self._win.resizable(False, False)
        self._win.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self._win.after(200, lambda: set_window_icon(self._win))

        header = ctk.CTkFrame(self._win, fg_color=TEAL, height=56, corner_radius=0)
        header.pack(fill="x")
        header.pack_propagate(False)
        try:
            ctk.CTkLabel(header, image=load_logo((40, 40)), text="").pack(side="left", padx=(12, 8), pady=8)
        except Exception:
            pass
        ctk.CTkLabel(header, text="Marsden Park Anglican College",
                     font=ctk.CTkFont(size=13, weight="bold"), text_color=WHITE).pack(side="left", pady=8)

        ctk.CTkLabel(self._win, text="First Time Setup",
                     font=ctk.CTkFont(size=15, weight="bold"), text_color=CHARCOAL).pack(pady=(16, 4))
        ctk.CTkLabel(self._win,
                     text="The AI model needs to be downloaded once.\n"
                          "If you already have a model file, just point to that folder.",
                     justify="center", text_color=CHARCOAL).pack(pady=(0, 10))

        # ── Model choice ──────────────────────────────────────────────
        ctk.CTkLabel(self._win, text="Model:", font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=TEAL).pack(padx=20, anchor="w")
        self._choice_var = ctk.StringVar(value=next(iter(_CHOICES)))
        ctk.CTkSegmentedButton(self._win, values=list(_CHOICES), variable=self._choice_var,
                               selected_color=TEAL, selected_hover_color=TEAL_HOVER,
                               command=lambda _: self._check_existing()
                               ).pack(padx=20, pady=(2, 2), fill="x")
        self._choice_note = ctk.CTkLabel(self._win, text="", text_color="gray")
        self._choice_note.pack(padx=20, anchor="w", pady=(0, 8))

        # ── Folder picker ─────────────────────────────────────────────
        ctk.CTkLabel(self._win, text="Models folder:", font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=TEAL).pack(padx=20, anchor="w")
        path_frame = ctk.CTkFrame(self._win, fg_color="transparent")
        path_frame.pack(fill="x", padx=20, pady=(2, 10))
        self._path_var = ctk.StringVar(value=str(get_models_dir()))
        ctk.CTkEntry(path_frame, textvariable=self._path_var, state="readonly",
                     font=ctk.CTkFont(size=11)).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(path_frame, text="Change…", width=80, fg_color=SKY_BLUE, hover_color=TEAL,
                      text_color=WHITE, command=self._pick_folder).pack(side="left")

        # ── Status + progress ─────────────────────────────────────────
        self._status_label = ctk.CTkLabel(self._win, text="", text_color=CHARCOAL)
        self._status_label.pack(pady=(0, 4))
        self._progress = ctk.CTkProgressBar(self._win, width=440, progress_color=TEAL)
        self._progress.set(0)
        self._size_label = ctk.CTkLabel(self._win, text="", text_color="gray")
        self._size_label.pack()

        self._action_btn = ctk.CTkButton(self._win, text="Start Download", fg_color=TEAL,
                                         hover_color=TEAL_HOVER, text_color=WHITE, width=160,
                                         command=self._start)
        self._action_btn.pack(pady=(8, 0))

        self._check_existing()
        self._win.mainloop()

        if self._error:
            self._on_error(self._error)
        elif self._done:
            self._on_complete()

    def _model(self) -> dict:
        return _CHOICES[self._choice_var.get()]

    def _pick_folder(self) -> None:
        chosen = fd.askdirectory(title="Choose models folder", mustexist=False)
        if not chosen:
            return
        set_models_dir(Path(chosen))
        self._path_var.set(chosen)
        self._check_existing()

    def _check_existing(self) -> None:
        self._choice_note.configure(text=self._model()["note"])
        local = list_local_models()
        if local:
            names = {p.name for p in local}
            pick = self._model()["filename"]
            use = pick if pick in names else local[0].name
            self._existing = use
            self._status_label.configure(text=f"✓ Model found ({use}) — no download needed.",
                                         text_color=TEAL)
            self._action_btn.configure(text="Continue  →", command=self._skip)
        else:
            self._existing = None
            self._status_label.configure(text="No model found here yet — ready to download.",
                                         text_color=CHARCOAL)
            self._action_btn.configure(text="Start Download", command=self._start)

    # ── Download ─────────────────────────────────────────────────────────────

    def _start(self) -> None:
        self._action_btn.configure(state="disabled", text="Downloading…")
        self._progress.pack(before=self._size_label, pady=(0, 2))
        m = self._model()
        threading.Thread(target=self._download, args=(m,), daemon=True).start()

    def _download(self, m: dict) -> None:
        try:
            download_model(m["repo"], m["filename"], self._on_progress, self._cancel)
            set_active_model(m["filename"])
            self._win.after(0, self._finish)
        except Exception as e:
            if self._cancel.is_set():
                return
            self._win.after(0, lambda e=e: self._failed(e))

    def _on_progress(self, downloaded: int, total: int) -> None:
        if self._win_alive():
            self._win.after(0, lambda d=downloaded, t=total: self._update_ui(d, t))

    def _update_ui(self, done: int, total: int) -> None:
        if not self._win_alive():
            return
        pct = done / total
        self._progress.set(pct)
        self._status_label.configure(text=f"Downloading… {pct:.0%}")
        self._size_label.configure(text=f"{done / 1e6:.0f} MB / {total / 1e6:.0f} MB")

    def _failed(self, e: Exception) -> None:
        self._status_label.configure(
            text="Download stopped — check your internet and press Retry.\n"
                 "(It will carry on from where it got to.)", text_color="orange")
        self._size_label.configure(text=str(e)[:120])
        self._action_btn.configure(state="normal", text="Retry", command=self._start)

    def _finish(self) -> None:
        if not self._win_alive():
            return
        self._done = True
        self._status_label.configure(text="Download complete!")
        self._progress.set(1)
        self._win.after(800, self._win.destroy)

    def _skip(self) -> None:
        if self._existing:
            set_active_model(self._existing)
        self._done = True
        self._win.destroy()

    def _win_alive(self) -> bool:
        try:
            return bool(self._win.winfo_exists())
        except Exception:
            return False

    def _on_cancel(self) -> None:
        self._cancel.set()
        sys.exit(0)

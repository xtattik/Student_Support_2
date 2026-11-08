import customtkinter as ctk
from pynput.mouse import Controller as MouseController
from theme import TEAL, TEAL_HOVER, CHARCOAL, WHITE, load_logo

_mouse = MouseController()

BUTTON_ACTIONS = [
    ("Explain this", "explain"),
    ("Summarise this", "summarise"),
    ("Test me on this", "test_me"),
]


class OverlayWindow:
    def __init__(self, on_action: callable):
        self._on_action = on_action
        self._win: ctk.CTkToplevel | None = None

    def show(self) -> None:
        if self._win is not None:
            self.hide()

        x, y = _mouse.position

        self._win = ctk.CTkToplevel()
        self._win.title("")
        self._win.overrideredirect(True)
        self._win.attributes("-topmost", True)
        self._win.resizable(False, False)

        # ── Header bar ──────────────────────────────────────────────────
        header = ctk.CTkFrame(self._win, fg_color=TEAL, corner_radius=0)
        header.pack(fill="x")

        try:
            logo_img = load_logo((36, 36))
            ctk.CTkLabel(header, image=logo_img, text="").pack(side="left", padx=(10, 6), pady=8)
        except Exception:
            pass

        ctk.CTkLabel(
            header,
            text="Marsden Park AC",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=WHITE,
        ).pack(side="left", pady=8)

        # ── Body ────────────────────────────────────────────────────────
        body = ctk.CTkFrame(self._win, fg_color=WHITE, corner_radius=0)
        body.pack(fill="both", padx=0, pady=0)

        ctk.CTkLabel(
            body,
            text="What would you like?",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=CHARCOAL,
        ).pack(padx=16, pady=(12, 6))

        for text, action in BUTTON_ACTIONS:
            btn = ctk.CTkButton(
                body,
                text=text,
                width=210,
                fg_color=TEAL,
                hover_color=TEAL_HOVER,
                text_color=WHITE,
                command=lambda a=action: self._handle(a),
            )
            btn.pack(padx=16, pady=4)

        cancel = ctk.CTkButton(
            body,
            text="Cancel",
            width=210,
            fg_color="transparent",
            border_width=1,
            border_color=TEAL,
            text_color=TEAL,
            hover_color="#E8F4F6",
            command=self.hide,
        )
        cancel.pack(padx=16, pady=(4, 14))

        # ── Position near cursor ─────────────────────────────────────────
        self._win.update_idletasks()
        w = self._win.winfo_reqwidth()
        h = self._win.winfo_reqheight()
        sw = self._win.winfo_screenwidth()
        sh = self._win.winfo_screenheight()
        px = min(x + 10, sw - w - 10)
        py = min(y + 10, sh - h - 10)

        self._win.geometry(f"+{px}+{py}")
        self._win.focus_force()
        self._win.bind("<FocusOut>", lambda _: self.hide())
        self._win.bind("<Escape>", lambda _: self.hide())

    def hide(self) -> None:
        if self._win is not None:
            self._win.destroy()
            self._win = None

    def _handle(self, action: str) -> None:
        self.hide()
        self._on_action(action)

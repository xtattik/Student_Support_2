import base64
import queue
import sys
import threading
import tkinter as tk

import customtkinter as ctk
import pyperclip

import clipboard_image
import llm_engine
import markdown_lite
import mathfmt
from theme import TEAL, TEAL_HOVER, SKY_BLUE, WHITE, set_window_icon

ACTION_LABELS = {
    "explain":   "Explanation",
    "summarise": "Summary",
}

_DONE = object()


class ResultWindow:
    """Streams a reply into a text box.

    Generation runs on a worker thread and pushes text into a queue; the Tk
    thread drains the queue on a timer. (Touching Tk widgets from a worker
    thread is unsafe and can crash, especially on macOS.)
    Closing the window cancels generation so the CPU stops working.
    """

    def __init__(self, action: str, system_prompt: str, source_text: str,
                 simplify_prompt: str = "", trimmed: bool = False):
        self._action = action
        self._system_prompt = system_prompt
        self._source_text = source_text
        self._simplify_prompt = simplify_prompt
        self._trimmed = trimmed
        self._win: ctk.CTkToplevel | None = None
        self._simplify_btn = None
        self._q: queue.Queue = queue.Queue()
        self._cancel = threading.Event()
        self._first_chunk = True

    def show(self) -> None:
        mathfmt.preload()  # load the equation renderer while the AI warms up
        title = ACTION_LABELS.get(self._action, "Result")
        self._win = ctk.CTkToplevel()
        self._win.title(title)
        self._win.geometry("620x460")
        self._win.attributes("-topmost", True)
        self._win.resizable(True, True)
        self._win.protocol("WM_DELETE_WINDOW", self._close)
        self._win.after(200, lambda: set_window_icon(self._win))

        header = ctk.CTkFrame(self._win, fg_color=TEAL, height=44, corner_radius=0)
        header.pack(fill="x")
        header.pack_propagate(False)
        ctk.CTkLabel(header, text=title, font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=WHITE).pack(side="left", padx=16, pady=10)

        self._textbox = ctk.CTkTextbox(self._win, wrap="word", font=ctk.CTkFont(size=13),
                                       spacing2=2, spacing3=4)
        self._textbox.pack(fill="both", expand=True, padx=16, pady=(12, 4))
        self._setup_tags()

        self._note = ctk.CTkLabel(self._win, text="", text_color="gray")
        self._note.pack()

        btn_frame = ctk.CTkFrame(self._win, fg_color="transparent")
        btn_frame.pack(pady=(4, 16))
        ctk.CTkButton(btn_frame, text="Close", fg_color=TEAL, hover_color=TEAL_HOVER,
                      text_color=WHITE, command=self._close).pack(side="left", padx=8)

        if self._action == "explain" and self._simplify_prompt:
            self._simplify_btn = ctk.CTkButton(btn_frame, text="Simpler please",
                                               fg_color=SKY_BLUE, hover_color=TEAL,
                                               text_color=WHITE, command=self._simplify)
            self._simplify_btn.pack(side="left", padx=8)

        self._start(self._system_prompt)
        self._poll()

    # ── Generation ───────────────────────────────────────────────────────────

    def _start(self, prompt: str) -> None:
        self._cancel = threading.Event()
        self._first_chunk = True
        self._set_placeholder("Thinking…" if llm_engine.is_ready()
                              else "Starting the AI — please wait a moment…")
        if self._simplify_btn:
            self._simplify_btn.configure(state="disabled")
        cancel = self._cancel
        threading.Thread(target=self._worker, args=(prompt, cancel), daemon=True).start()

    def _worker(self, prompt: str, cancel: threading.Event) -> None:
        try:
            for chunk in llm_engine.complete(prompt, self._source_text, cancel=cancel):
                self._q.put((cancel, chunk))
        except Exception as e:
            self._q.put((cancel, f"\n\n[Error: {e}]"))
        finally:
            self._q.put((cancel, _DONE))

    def _poll(self) -> None:
        if self._win is None:
            return
        try:
            while True:
                cancel, item = self._q.get_nowait()
                if cancel is not self._cancel:
                    continue  # leftovers from a cancelled run
                if item is _DONE:
                    self._finish()
                else:
                    self._append(item)
        except queue.Empty:
            pass
        self._win.after(40, self._poll)

    # ── Formatting ───────────────────────────────────────────────────────────

    def _setup_tags(self) -> None:
        """Styles for the Markdown subset in markdown_lite (bold, headings, bullets…).
        Tag fonts go on the inner tk.Text, since CTkTextbox forbids tag fonts."""
        tb = self._textbox
        inner = tb._textbox

        def font(size=13, **kw):
            f = ctk.CTkFont(size=size, **kw)
            try:
                return tb._apply_font_scaling(f)   # match CTk's DPI scaling
            except Exception:
                return f

        def px(n):
            try:
                return tb._apply_widget_scaling(n)
            except Exception:
                return n

        self._fonts = {
            "bold": font(weight="bold"),
            "italic": font(slant="italic"),
            "bolditalic": font(weight="bold", slant="italic"),
            "heading": font(size=15, weight="bold"),
            "code": ("Consolas", 13) if sys.platform == "win32" else ("Menlo", 13),
        }
        inner.tag_configure("heading", font=self._fonts["heading"], spacing1=px(6), spacing3=px(4))
        # Wrapped bullet lines line up with the text, not the "•"
        try:
            import tkinter.font as tkfont
            hang = tkfont.Font(font=inner.cget("font")).measure("•  ")
        except Exception:
            hang = px(18)
        inner.tag_configure("bullet", lmargin1=px(6), lmargin2=px(6) + hang)
        inner.tag_configure("bullet2", lmargin1=px(26), lmargin2=px(26) + hang)
        inner.tag_configure("bold", font=self._fonts["bold"])
        inner.tag_configure("italic", font=self._fonts["italic"])
        inner.tag_configure("bolditalic", font=self._fonts["bolditalic"])
        inner.tag_configure("code", font=self._fonts["code"])
        inner.tag_raise("bold")
        inner.tag_raise("italic")
        inner.tag_raise("bolditalic")
        # Equations on their own line: centred, with breathing room, like a textbook
        inner.tag_configure("eqline", justify="center", spacing1=px(4), spacing3=px(6))
        try:
            self._scale = tb._get_widget_scaling()
        except Exception:
            self._scale = 1.0

    @staticmethod
    def _tk_tags(tags: tuple) -> tuple:
        if "bold" in tags and "italic" in tags:
            tags = tuple(t for t in tags if t not in ("bold", "italic")) + ("bolditalic",)
        return tags

    def _insert_segments(self, segments) -> None:
        inner = self._textbox._textbox
        for text, tags in segments:
            if "display" in tags:
                self._insert_equation(text)
            else:
                inner.insert("end", text, self._tk_tags(tags))

    # ── Equations ────────────────────────────────────────────────────────────

    def _insert_equation(self, latex: str) -> None:
        """Typeset each line of a display equation as a picture (Unicode if it can't
        be drawn). Click = copy as picture, right-click = copy as text."""
        inner = self._textbox._textbox
        dark = ctk.get_appearance_mode() == "Dark"
        colour = "#E5E5E5" if dark else "#1A1A1A"
        lines = mathfmt.display_lines(latex) or [latex]
        for n, line in enumerate(lines):
            if n:
                inner.insert("end", "\n")
            start = inner.index("end-1c")
            png = mathfmt.render_png(line, color=colour, dpi=round(72 * self._scale), fontsize=19)
            if png:
                img = tk.PhotoImage(data=base64.b64encode(png).decode("ascii"))
                self._images.append(img)  # Tk doesn't keep its own reference
                inner.image_create("end", image=img, align="center")
            else:
                inner.insert("end", mathfmt.latex_to_unicode(line))
            self._eq_count += 1
            tag = f"eq{self._eq_count}"
            inner.tag_add("eqline", start, "end-1c")
            inner.tag_add(tag, start, "end-1c")
            inner.tag_bind(tag, "<Button-1>", lambda _e, s=line: self._copy_equation(s))
            for btn in ("<Button-3>", "<Button-2>"):   # right-click (Windows / Mac)
                inner.tag_bind(tag, btn, lambda _e, s=line: self._copy_equation(s, as_text=True))
            inner.tag_bind(tag, "<Enter>", lambda _e: inner.configure(cursor="hand2"))
            inner.tag_bind(tag, "<Leave>", lambda _e: inner.configure(cursor="xterm"))

    def _copy_equation(self, latex: str, as_text: bool = False) -> None:
        copied = None
        if not as_text:
            png = mathfmt.render_png(latex, color="#000000", dpi=200, fontsize=16,
                                     background="#FFFFFF")
            if png and clipboard_image.copy_png(png):
                copied = "as a picture"
        if copied is None:
            try:
                pyperclip.copy(mathfmt.latex_to_unicode(latex))
                copied = "as text"
            except Exception:
                pass
        self._flash(f"Equation copied {copied} — paste it into your notes." if copied
                    else "Sorry, couldn't copy that equation.")

    def _flash(self, msg: str) -> None:
        self._note.configure(text=msg, text_color=TEAL)

        def _restore():
            if self._win is not None:
                self._note.configure(text=self._tip_text(), text_color="gray")
        self._win.after(3000, _restore)

    def _tip_text(self) -> str:
        if self._eq_count:
            return "Tip: click an equation to copy it as a picture (right-click copies it as text)."
        return ""

    def _set_placeholder(self, text: str) -> None:
        self._raw = ""
        self._done_upto = 0       # chars of _raw already rendered as complete lines
        self._blank_run = 0
        self._fmt = markdown_lite.LineFormatter()
        self._images: list = []
        self._eq_count = 0
        self._textbox.configure(state="normal")
        self._textbox.delete("1.0", "end")
        self._textbox.insert("end", text)
        self._textbox.configure(state="disabled", text_color="gray")

    def _append(self, chunk: str) -> None:
        """Complete lines are formatted once; the line still streaming in is
        re-rendered on each update so formatting appears as soon as it closes."""
        inner = self._textbox._textbox
        self._textbox.configure(state="normal")
        if self._first_chunk:
            self._textbox.delete("1.0", "end")
            self._textbox.configure(text_color=("gray10", "gray90"))
            self._first_chunk = False
            chunk = chunk.lstrip()
            inner.mark_set("live", "1.0")
            inner.mark_gravity("live", "left")
        self._raw += chunk

        # "end-1c", not "end": deleting through Tk's final newline makes it
        # delete the previous line break instead, joining lines together.
        inner.delete("live", "end-1c")
        pending = self._raw[self._done_upto:]
        nl = pending.rfind("\n")
        if nl >= 0:
            for line in pending[:nl].split("\n"):
                segs = self._fmt.feed(line)
                if segs is None:
                    continue          # inside a multi-line $$ block
                if not segs and not line.strip():
                    self._blank_run += 1
                    if self._blank_run > 1:
                        continue
                else:
                    self._blank_run = 0
                self._insert_segments(segs + [("\n", ())])
            self._done_upto += nl + 1
            inner.mark_set("live", "end-1c")
        self._insert_segments(self._fmt.preview(self._raw[self._done_upto:]))

        self._textbox.see("end")
        self._textbox.configure(state="disabled")

    def _finish(self) -> None:
        if not self._first_chunk:
            self._append("\n")            # commit the last line
            tail = self._fmt.flush()      # and any unclosed $$ block
            if tail:
                self._textbox.configure(state="normal")
                self._insert_segments(tail)
                self._textbox.configure(state="disabled")
        notes = [self._tip_text()]
        if self._trimmed:
            notes.insert(0, "Your selection was long, so only the first part was used.")
        self._note.configure(text="\n".join(n for n in notes if n), text_color="gray")
        if self._simplify_btn:
            self._simplify_btn.configure(state="normal", text="Simpler please")

    def _simplify(self) -> None:
        self._cancel.set()
        self._simplify_btn.configure(text="Simplifying…")
        self._start(self._simplify_prompt)

    def _close(self) -> None:
        self._cancel.set()
        if self._win is not None:
            self._win.destroy()
            self._win = None

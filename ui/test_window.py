import threading
import customtkinter as ctk

import llm_engine
from prompts import QUIZ_SCHEMA
from quiz import clean_quiz, mark
from theme import TEAL, TEAL_HOVER, LIME_GREEN, WHITE, set_window_icon

_RED = "#C0392B"


class TestWindow:
    def __init__(self, source_text: str, quiz_prompt: str, junior: bool = False,
                 trimmed: bool = False):
        self._source_text = source_text
        self._quiz_prompt = quiz_prompt
        self._junior = junior
        self._trimmed = trimmed
        self._win: ctk.CTkToplevel | None = None
        self._answer_vars: list[ctk.StringVar] = []
        self._questions: list[dict] = []
        self._closed = False

    def show(self) -> None:
        self._win = ctk.CTkToplevel()
        self._win.title("Test Yourself")
        self._win.geometry("640x200")
        self._win.attributes("-topmost", True)
        self._win.resizable(True, True)
        self._win.protocol("WM_DELETE_WINDOW", self._close)
        self._win.after(200, lambda: set_window_icon(self._win))

        header = ctk.CTkFrame(self._win, fg_color=TEAL, height=44, corner_radius=0)
        header.pack(fill="x")
        header.pack_propagate(False)
        ctk.CTkLabel(header, text="Test Yourself",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=WHITE).pack(side="left", padx=16, pady=10)

        loading = "Writing your questions…" if llm_engine.is_ready() \
            else "Starting the AI — please wait a moment…"
        self._loading = ctk.CTkLabel(self._win, text=loading,
                                     font=ctk.CTkFont(size=14), text_color="gray")
        self._loading.pack(expand=True)

        threading.Thread(target=self._generate, daemon=True).start()

    # ── Background work → marshalled back to the Tk thread with after() ──────

    def _ui(self, fn) -> None:
        if not self._closed and self._win is not None:
            try:
                self._win.after(0, fn)
            except Exception:
                pass

    def _generate(self) -> None:
        try:
            data = llm_engine.complete_json(self._quiz_prompt, self._source_text,
                                            QUIZ_SCHEMA, max_tokens=1200)
            questions = clean_quiz(data)
            if questions:
                self._ui(lambda: self._render_questions(questions))
            else:
                self._ui(lambda: self._show_message(
                    "Sorry — the AI couldn't make good questions from that text.\n"
                    "Try selecting a longer passage."))
        except Exception as e:
            self._ui(lambda e=e: self._show_message(f"Error: {e}"))

    # ── Rendering ────────────────────────────────────────────────────────────

    def _render_questions(self, questions: list[dict]) -> None:
        self._loading.destroy()
        self._win.geometry("700x600")
        self._questions = questions
        self._answer_vars = []

        if self._trimmed:
            ctk.CTkLabel(self._win, text="Your selection was long, so only the first part was used.",
                         text_color="gray").pack(pady=(8, 0))

        self._scroll = ctk.CTkScrollableFrame(self._win)
        self._scroll.pack(fill="both", expand=True, padx=16, pady=(12, 0))
        self._radios: list[list[ctk.CTkRadioButton]] = []
        self._feedback_slots: list[ctk.CTkFrame] = []

        for i, q in enumerate(questions):
            ctk.CTkLabel(self._scroll, text=f"Q{i + 1}. {q['question']}",
                         font=ctk.CTkFont(size=13, weight="bold"), text_color=TEAL,
                         wraplength=620, justify="left", anchor="w").pack(anchor="w", pady=(10, 4))
            var = ctk.StringVar(value="")
            self._answer_vars.append(var)
            row = []
            for letter, text in q["options"].items():
                rb = ctk.CTkRadioButton(self._scroll, text=f"{letter})  {text}",
                                        variable=var, value=letter,
                                        font=ctk.CTkFont(size=12),
                                        fg_color=TEAL, hover_color=TEAL_HOVER)
                rb.pack(anchor="w", padx=20, pady=2)
                row.append(rb)
            self._radios.append(row)
            slot = ctk.CTkFrame(self._scroll, fg_color="transparent")
            slot.pack(fill="x", padx=20)
            self._feedback_slots.append(slot)

        self._status = ctk.CTkLabel(self._win, text="", text_color="gray")
        self._status.pack()
        self._check_btn = ctk.CTkButton(self._win, text="Check my answers",
                                        fg_color=TEAL, hover_color=TEAL_HOVER,
                                        text_color=WHITE, command=self._check_answers)
        self._check_btn.pack(pady=(4, 12))

    def _check_answers(self) -> None:
        answers = [v.get() for v in self._answer_vars]
        if any(a == "" for a in answers):
            self._status.configure(text="Please answer all questions before checking.",
                                   text_color="orange")
            return

        score, results = mark(self._questions, answers)
        for q, ok, slot, radios in zip(self._questions, results,
                                       self._feedback_slots, self._radios):
            for rb in radios:
                rb.configure(state="disabled")
            if ok:
                head = "Correct! 🌟" if self._junior else "Correct"
            else:
                right = f"{q['answer']}) {q['options'][q['answer']]}"
                head = f"Not quite — the answer is {right}" if self._junior \
                    else f"Incorrect — the answer is {right}"
            ctk.CTkLabel(slot, text=head, text_color=LIME_GREEN if ok else _RED,
                         font=ctk.CTkFont(size=12, weight="bold"),
                         wraplength=600, justify="left", anchor="w").pack(anchor="w", pady=(4, 0))
            if q["explanation"]:
                ctk.CTkLabel(slot, text=q["explanation"], text_color="gray",
                             wraplength=600, justify="left", anchor="w").pack(anchor="w")

        total = len(self._questions)
        cheer = "  Great work!" if score == total else ""
        self._status.configure(text=f"Score: {score}/{total}{cheer}",
                               text_color=TEAL, font=ctk.CTkFont(size=14, weight="bold"))
        self._check_btn.configure(text="Close", command=self._close)

    def _show_message(self, text: str) -> None:
        self._loading.destroy()
        self._win.geometry("640x300")
        box = ctk.CTkTextbox(self._win, wrap="word", font=ctk.CTkFont(size=13))
        box.pack(fill="both", expand=True, padx=16, pady=16)
        box.insert("end", text)
        box.configure(state="disabled")
        ctk.CTkButton(self._win, text="Close", fg_color=TEAL, hover_color=TEAL_HOVER,
                      text_color=WHITE, command=self._close).pack(pady=(0, 12))

    def _close(self) -> None:
        self._closed = True
        if self._win is not None:
            self._win.destroy()
            self._win = None

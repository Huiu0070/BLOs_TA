
#!/usr/bin/env python3
"""
BLO Quiz App — Aerospace Technology
GUI version using tkinter.
Answer (a) in the PDF is ALWAYS correct; options are shuffled before display.

Dependencies: pip install pdfplumber
"""

import re
import sys
import random
import os
import hashlib
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# ── PDF parsing (unchanged logic) ─────────────────────────────────────────────
SPLIT_COL = 65
OPTION_RE  = re.compile(r"^\s*\([a-d]\)")
QNUM_RE    = re.compile(r"^\s*\d+\.")
BLO_RE     = re.compile(r"^BLO-\d+")
HEADER_RE  = re.compile(r"^(Aerospace|EETAC|Q\d|Perm)")

BLO_NAMES = {
    "BLO-1": "Flight Principles",
    "BLO-2": "Aircraft Stability & Control",
    "BLO-3": "Aircraft Performances",
    "BLO-4": "Materials & Structures / Aircraft Recognition",
    "BLO-5": "Aerospace Propulsion",
    "BLO-6": "Aircraft Systems & Helicopters",
    "BLO-7": "Space Systems",
    "BLO-8": "Navigation & Altimetry",
}


def pdf_to_text(pdf_path: str) -> str:
    pdf_hash  = hashlib.md5(pdf_path.encode()).hexdigest()[:8]
    cache_file = os.path.join(tempfile.gettempdir(), f"_blo_quiz_cache_{pdf_hash}.txt")
    if os.path.exists(cache_file):
        with open(cache_file, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    try:
        import pdfplumber
    except ImportError:
        raise RuntimeError("pdfplumber is not installed.\nRun:  pip install pdfplumber")

    linear_lines: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            words = page.extract_words(x_tolerance=3, y_tolerance=3)
            if not words:
                linear_lines.append("")
                continue
            split_x = page.width * (SPLIT_COL / 100)
            from collections import defaultdict
            rows: dict = defaultdict(list)
            for w in words:
                rows[round(w["top"] / 3) * 3].append(w)
            left_lines, right_lines = [], []
            for y_key in sorted(rows):
                row_words = sorted(rows[y_key], key=lambda w: w["x0"])
                left  = [w["text"] for w in row_words if w["x0"] <  split_x]
                right = [w["text"] for w in row_words if w["x0"] >= split_x]
                if left:  left_lines.append(" ".join(left))
                if right: right_lines.append(" ".join(right))
            linear_lines.extend(left_lines)
            linear_lines.extend(right_lines)
            linear_lines.append("")
    text = "\n".join(linear_lines)
    with open(cache_file, "w", encoding="utf-8") as fh:
        fh.write(text)
    return text


def merge_lines(text: str) -> str:
    lines = text.splitlines()
    out: list[str] = []
    for line in lines:
        s = line.strip()
        if not s:
            out.append("")
            continue
        is_new = bool(
            OPTION_RE.match(s) or QNUM_RE.match(s)
            or BLO_RE.match(s) or HEADER_RE.match(s)
        )
        if out and out[-1] and not is_new:
            out[-1] = out[-1] + " " + s
        else:
            out.append(s)
    return "\n".join(out)


def parse_all(text: str) -> dict[str, list[dict]]:
    text  = merge_lines(text)
    blos: dict[str, list[dict]] = {}
    parts = re.compile(r"(BLO-\d+:[^\n]+)").split(text)
    i = 1
    while i < len(parts) - 1:
        heading, body = parts[i].strip(), parts[i + 1]
        i += 2
        m = re.match(r"(BLO-\d+)", heading)
        if not m:
            continue
        key = m.group(1)
        q_re = re.compile(
            r"\d+\.\s+(.*?)\(a\)\s*(.*?)\(b\)\s*(.*?)\(c\)\s*(.*?)\(d\)\s*(.*?)"
            r"(?=\n\s*\d+\.|\Z)", re.DOTALL
        )
        for qm in q_re.finditer(body):
            def clean(s):
                return re.sub(r"\s+", " ", s).strip().rstrip(". ")
            q, a, b, c, d = (clean(qm.group(k)) for k in range(1, 6))
            if len(q) < 10 or len(a) < 3:
                continue
            blos.setdefault(key, []).append(
                {"question": q, "correct_text": a, "options": [a, b, c, d]}
            )
    return blos


def dedup(qs: list[dict]) -> list[dict]:
    seen, out = set(), []
    for q in qs:
        k = q["question"][:70].lower()
        if k not in seen:
            seen.add(k)
            out.append(q)
    return out


# ── Colour palette ─────────────────────────────────────────────────────────────
BG       = "#0f1923"   # deep navy
SURFACE  = "#1a2635"   # card surface
BORDER   = "#243447"   # subtle border
ACCENT   = "#00b4d8"   # cyan
ACCENT2  = "#0077b6"   # darker cyan
TEXT     = "#e8f4f8"   # near-white
DIMTEXT  = "#6b8fa8"   # muted
GREEN    = "#2dc653"
RED      = "#e5383b"
YELLOW   = "#ffd166"
FONT_H   = ("Segoe UI", 13, "bold")
FONT_B   = ("Segoe UI", 11)
FONT_SM  = ("Segoe UI", 9)
FONT_XL  = ("Segoe UI", 16, "bold")
FONT_TIT = ("Segoe UI", 10)


# ── App ────────────────────────────────────────────────────────────────────────
class BLOQuizApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("✈  BLO Quiz — Aerospace Technology")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.minsize(700, 500)

        # State
        self.all_blos:   dict[str, list[dict]] = {}
        self.quiz_sample: list[dict] = []
        self.quiz_idx    = 0
        self.score       = 0
        self.q_count     = 10
        self.blo_name    = ""
        self.answered    = False

        self._build_ui()
        self._show_home()
        self.after(100, self._center_window)

    # ── Layout ────────────────────────────────────────────────────────────────
    def _build_ui(self):
        # ── Top bar ──────────────────────────────────────────────────────────
        bar = tk.Frame(self, bg=SURFACE, height=52)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        tk.Label(bar, text="✈  AEROSPACE TECHNOLOGY  BLO QUIZ",
                 font=("Segoe UI", 11, "bold"), bg=SURFACE, fg=ACCENT
                 ).pack(side="left", padx=20, pady=14)

        self.lbl_status = tk.Label(bar, text="", font=FONT_SM, bg=SURFACE, fg=DIMTEXT)
        self.lbl_status.pack(side="right", padx=20)

        # thin accent line under bar
        tk.Frame(self, bg=ACCENT2, height=2).pack(fill="x")

        # ── Main content area ─────────────────────────────────────────────────
        self.content = tk.Frame(self, bg=BG)
        self.content.pack(fill="both", expand=True, padx=30, pady=24)

    def _clear_content(self):
        for w in self.content.winfo_children():
            w.destroy()

    # ── HOME screen ───────────────────────────────────────────────────────────
    def _show_home(self):
        self._clear_content()
        self.lbl_status.config(text="")

        # Hero text
        tk.Label(self.content, text="Select a PDF to begin",
                 font=FONT_XL, bg=BG, fg=TEXT).pack(pady=(30, 6))
        tk.Label(self.content,
                 text="Load your Aerospace Technology question bank, then choose a BLO topic.",
                 font=FONT_B, bg=BG, fg=DIMTEXT).pack()

        # Drop zone / browse button
        drop = tk.Frame(self.content, bg=SURFACE, bd=0, relief="flat",
                        highlightthickness=2, highlightbackground=BORDER)
        drop.pack(pady=36, ipadx=30, ipady=24)

        tk.Label(drop, text="📄", font=("Segoe UI", 28), bg=SURFACE, fg=ACCENT
                 ).pack(pady=(16, 4))
        tk.Label(drop, text="No PDF loaded", font=FONT_B, bg=SURFACE, fg=DIMTEXT
                 ).pack()

        self.btn_browse = tk.Button(
            drop, text="  Browse PDF…  ",
            font=FONT_H, bg=ACCENT, fg=BG, activebackground=ACCENT2,
            activeforeground=TEXT, relief="flat", cursor="hand2",
            bd=0, padx=18, pady=8,
            command=self._load_pdf
        )
        self.btn_browse.pack(pady=16)

        # Loading bar (hidden until needed)
        self.progress_frame = tk.Frame(self.content, bg=BG)
        self.progress_frame.pack(fill="x", pady=(0, 8))
        self.progress_lbl = tk.Label(self.progress_frame, text="",
                                     font=FONT_SM, bg=BG, fg=DIMTEXT)
        self.progress_lbl.pack()
        self.progress = ttk.Progressbar(self.progress_frame, mode="indeterminate",
                                        length=320)

    def _load_pdf(self):
        path = filedialog.askopenfilename(
            title="Select Aerospace Technology PDF",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")]
        )
        if not path:
            return
        self.btn_browse.config(state="disabled", text="  Loading…  ")
        self.progress_lbl.config(text=f"Extracting: {os.path.basename(path)}")
        self.progress.pack(pady=4)
        self.progress.start(12)

        def worker():
            try:
                text     = pdf_to_text(path)
                all_blos = parse_all(text)
                for k in list(all_blos):
                    all_blos[k] = dedup(all_blos[k])
                    if not all_blos[k]:
                        del all_blos[k]
                self.after(0, lambda: self._pdf_loaded(all_blos, path))
            except Exception as e:
                self.after(0, lambda: self._pdf_error(str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _pdf_error(self, msg):
        self.progress.stop()
        self.progress.pack_forget()
        self.btn_browse.config(state="normal", text="  Browse PDF…  ")
        messagebox.showerror("Error loading PDF", msg)

    def _pdf_loaded(self, all_blos, path):
        self.progress.stop()
        self.all_blos = all_blos
        total = sum(len(v) for v in all_blos.values())
        self.lbl_status.config(
            text=f"{total} questions · {len(all_blos)} BLOs · {os.path.basename(path)}"
        )
        self._show_blo_menu()

    # ── BLO MENU ──────────────────────────────────────────────────────────────
    def _show_blo_menu(self):
        self._clear_content()
        keys = sorted(self.all_blos, key=lambda k: int(k.split("-")[1]))

        tk.Label(self.content, text="Choose a topic",
                 font=FONT_XL, bg=BG, fg=TEXT).pack(pady=(10, 18))

        grid = tk.Frame(self.content, bg=BG)
        grid.pack()

        # "All BLOs" card
        self._blo_card(grid, 0, 0, "ALL", "All BLOs",
                       "Full random mix", sum(len(v) for v in self.all_blos.values()),
                       lambda: self._start_config("All BLOs",
                           [q for qs in self.all_blos.values() for q in qs]))

        for idx, key in enumerate(keys, 1):
            row, col = divmod(idx, 3)
            name  = BLO_NAMES.get(key, key)
            count = len(self.all_blos[key])
            qs    = self.all_blos[key]
            self._blo_card(grid, row, col, key.replace("BLO-", ""),
                           key, name, count,
                           lambda qs=qs, k=key, n=name: self._start_config(f"{k} — {n}", qs))

    def _blo_card(self, parent, row, col, number, key, name, count, cmd):
        card = tk.Frame(parent, bg=SURFACE, cursor="hand2",
                        highlightthickness=1, highlightbackground=BORDER)
        card.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")

        num_lbl = tk.Label(card, text=number, font=("Segoe UI", 22, "bold"),
                           bg=SURFACE, fg=ACCENT)
        num_lbl.pack(anchor="w", padx=14, pady=(12, 0))

        tk.Label(card, text=key, font=("Segoe UI", 8, "bold"),
                 bg=SURFACE, fg=DIMTEXT).pack(anchor="w", padx=14)

        tk.Label(card, text=name, font=("Segoe UI", 9),
                 bg=SURFACE, fg=TEXT, wraplength=170, justify="left"
                 ).pack(anchor="w", padx=14, pady=(2, 0))

        tk.Label(card, text=f"{count} questions", font=FONT_SM,
                 bg=SURFACE, fg=DIMTEXT).pack(anchor="w", padx=14, pady=(2, 12))

        # hover effect
        def on_enter(e):
            card.config(highlightbackground=ACCENT)
            num_lbl.config(fg=TEXT)
        def on_leave(e):
            card.config(highlightbackground=BORDER)
            num_lbl.config(fg=ACCENT)

        for w in [card, num_lbl] + card.winfo_children():
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)
            w.bind("<Button-1>", lambda e, f=cmd: f())

    # ── CONFIG (question count) ────────────────────────────────────────────────
    def _start_config(self, blo_name, questions):
        self.blo_name     = blo_name
        self._quiz_pool   = questions
        self._clear_content()

        tk.Label(self.content, text=blo_name,
                 font=FONT_XL, bg=BG, fg=TEXT).pack(pady=(20, 4))
        tk.Label(self.content, text=f"{len(questions)} questions available",
                 font=FONT_B, bg=BG, fg=DIMTEXT).pack()

        box = tk.Frame(self.content, bg=SURFACE,
                       highlightthickness=1, highlightbackground=BORDER)
        box.pack(pady=30, ipadx=30, ipady=20)

        tk.Label(box, text="How many questions?",
                 font=FONT_H, bg=SURFACE, fg=TEXT).pack(pady=(16, 10))

        self.count_var = tk.IntVar(value=min(10, len(questions)))
        slider = tk.Scale(box, from_=1, to=len(questions),
                          variable=self.count_var, orient="horizontal",
                          length=300, bg=SURFACE, fg=TEXT,
                          troughcolor=BORDER, activebackground=ACCENT,
                          highlightthickness=0, bd=0,
                          font=FONT_SM, sliderlength=20)
        slider.pack()

        self.count_lbl = tk.Label(box, text=f"{self.count_var.get()} questions",
                                  font=FONT_B, bg=SURFACE, fg=ACCENT)
        self.count_lbl.pack(pady=(2, 14))
        self.count_var.trace_add("write", lambda *_: self.count_lbl.config(
            text=f"{self.count_var.get()} questions"))

        btn_row = tk.Frame(self.content, bg=BG)
        btn_row.pack()

        tk.Button(btn_row, text="← Back", font=FONT_B,
                  bg=SURFACE, fg=DIMTEXT, relief="flat", bd=0,
                  activebackground=BORDER, activeforeground=TEXT,
                  padx=16, pady=8, cursor="hand2",
                  command=self._show_blo_menu).pack(side="left", padx=8)

        tk.Button(btn_row, text="Start Quiz →", font=FONT_H,
                  bg=ACCENT, fg=BG, relief="flat", bd=0,
                  activebackground=ACCENT2, activeforeground=TEXT,
                  padx=20, pady=8, cursor="hand2",
                  command=self._begin_quiz).pack(side="left", padx=8)

    def _begin_quiz(self):
        self.q_count     = self.count_var.get()
        self.quiz_sample = random.sample(self._quiz_pool, self.q_count)
        self.quiz_idx    = 0
        self.score       = 0
        self._show_question()

    # ── QUESTION screen ───────────────────────────────────────────────────────
    def _show_question(self):
        self._clear_content()
        self.answered = False
        q    = self.quiz_sample[self.quiz_idx]
        idx  = self.quiz_idx
        tot  = self.q_count

        # Progress bar
        pf = tk.Frame(self.content, bg=BG)
        pf.pack(fill="x", pady=(0, 6))
        tk.Label(pf, text=f"Q {idx+1} / {tot}  ·  Score {self.score}/{idx}",
                 font=FONT_SM, bg=BG, fg=DIMTEXT).pack(side="left")
        tk.Label(pf, text=self.blo_name, font=FONT_SM, bg=BG, fg=DIMTEXT
                 ).pack(side="right")

        prog_bg = tk.Frame(self.content, bg=BORDER, height=4)
        prog_bg.pack(fill="x", pady=(0, 18))
        fill_w = int((idx / tot) * self.content.winfo_width()) if tot else 0
        tk.Frame(prog_bg, bg=ACCENT, height=4, width=fill_w).place(x=0, y=0,
                                                                    relwidth=idx/tot)

        # Question card
        qcard = tk.Frame(self.content, bg=SURFACE,
                         highlightthickness=1, highlightbackground=BORDER)
        qcard.pack(fill="x", pady=(0, 16))
        tk.Label(qcard, text=q["question"], font=FONT_H, bg=SURFACE, fg=TEXT,
                 wraplength=580, justify="left", pady=20, padx=20
                 ).pack(anchor="w")

        # Shuffle options
        opts = q["options"][:]
        random.shuffle(opts)
        correct = q["correct_text"]

        self._opt_buttons = []
        labels = ["A", "B", "C", "D"]
        for i, opt in enumerate(opts):
            row = tk.Frame(self.content, bg=BG)
            row.pack(fill="x", pady=3)
            btn = tk.Button(
                row,
                text=f"  {labels[i]}.  {opt}",
                font=FONT_B, bg=SURFACE, fg=TEXT,
                relief="flat", bd=0, anchor="w",
                activebackground=BORDER, activeforeground=TEXT,
                padx=16, pady=10, cursor="hand2",
                highlightthickness=1, highlightbackground=BORDER,
                wraplength=560, justify="left",
            )
            btn.pack(fill="x")

            def on_click(b=btn, o=opt, c=correct, all_opts=opts):
                if self.answered:
                    return
                self.answered = True
                self._evaluate(b, o, c, all_opts)

            btn.config(command=on_click)

            def _enter(e, b=btn): b.config(highlightbackground=ACCENT)
            def _leave(e, b=btn): b.config(highlightbackground=BORDER)
            btn.bind("<Enter>", _enter)
            btn.bind("<Leave>", _leave)
            self._opt_buttons.append((btn, opt))

        # Feedback label (shown after answering)
        self.feedback_lbl = tk.Label(self.content, text="", font=FONT_H,
                                     bg=BG, fg=TEXT)
        self.feedback_lbl.pack(pady=(8, 0))

        # Next / Finish button (hidden until answer chosen)
        self.btn_next = tk.Button(
            self.content,
            text="Next →" if idx + 1 < tot else "See Results",
            font=FONT_H, bg=ACCENT, fg=BG, relief="flat", bd=0,
            activebackground=ACCENT2, activeforeground=TEXT,
            padx=20, pady=8, cursor="hand2",
            command=self._next_question
        )

    def _evaluate(self, chosen_btn, chosen_opt, correct, all_opts):
        if chosen_opt == correct:
            self.score += 1
            chosen_btn.config(bg=GREEN, fg=BG, highlightbackground=GREEN)
            self.feedback_lbl.config(text="✔  Correct!", fg=GREEN)
        else:
            chosen_btn.config(bg=RED, fg=TEXT, highlightbackground=RED)
            self.feedback_lbl.config(
                text=f"✘  Incorrect — correct answer: {correct}", fg=RED
            )
            # Highlight the correct answer
            for btn, opt in self._opt_buttons:
                if opt == correct:
                    btn.config(bg=GREEN, fg=BG, highlightbackground=GREEN)

        self.btn_next.pack(pady=12)

    def _next_question(self):
        self.quiz_idx += 1
        if self.quiz_idx < self.q_count:
            self._show_question()
        else:
            self._show_results()

    # ── RESULTS screen ────────────────────────────────────────────────────────
    def _show_results(self):
        self._clear_content()
        pct = self.score / self.q_count * 100
        colour = GREEN if pct >= 70 else (YELLOW if pct >= 50 else RED)

        tk.Label(self.content, text="Quiz Complete", font=FONT_XL,
                 bg=BG, fg=TEXT).pack(pady=(30, 6))
        tk.Label(self.content, text=self.blo_name,
                 font=FONT_TIT, bg=BG, fg=DIMTEXT).pack()

        # Score circle (canvas)
        c = tk.Canvas(self.content, width=160, height=160, bg=BG,
                      highlightthickness=0)
        c.pack(pady=24)
        c.create_oval(10, 10, 150, 150, outline=BORDER, width=10)
        extent = 360 * (self.score / self.q_count)
        c.create_arc(10, 10, 150, 150, start=90, extent=-extent,
                     outline=colour, width=10, style="arc")
        c.create_text(80, 72, text=f"{self.score}/{self.q_count}",
                      font=("Segoe UI", 22, "bold"), fill=colour)
        c.create_text(80, 100, text=f"{pct:.0f}%",
                      font=("Segoe UI", 13), fill=DIMTEXT)

        msgs = {100: "🏆  Perfect score!", 80: "🎉  Great job!",
                60: "📚  Good effort — review missed topics.",
                0:  "💪  Keep studying — practice makes perfect!"}
        msg = next(v for k, v in sorted(msgs.items(), reverse=True) if pct >= k)
        tk.Label(self.content, text=msg, font=FONT_H, bg=BG, fg=colour).pack()

        btn_row = tk.Frame(self.content, bg=BG)
        btn_row.pack(pady=24)

        tk.Button(btn_row, text="Try Again", font=FONT_B,
                  bg=SURFACE, fg=TEXT, relief="flat", bd=0,
                  activebackground=BORDER, padx=16, pady=8, cursor="hand2",
                  command=lambda: self._start_config(self.blo_name, self._quiz_pool)
                  ).pack(side="left", padx=8)

        tk.Button(btn_row, text="Change Topic", font=FONT_B,
                  bg=SURFACE, fg=TEXT, relief="flat", bd=0,
                  activebackground=BORDER, padx=16, pady=8, cursor="hand2",
                  command=self._show_blo_menu).pack(side="left", padx=8)

        tk.Button(btn_row, text="Load New PDF", font=FONT_B,
                  bg=SURFACE, fg=TEXT, relief="flat", bd=0,
                  activebackground=BORDER, padx=16, pady=8, cursor="hand2",
                  command=self._show_home).pack(side="left", padx=8)

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _center_window(self):
        self.update_idletasks()
        w, h = 760, 600
        x = (self.winfo_screenwidth()  - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")


if __name__ == "__main__":
    app = BLOQuizApp()
    app.mainloop()
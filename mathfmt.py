"""
Maths display for AI replies.

The model writes maths as LaTeX. Students never see that:
  * inline maths ($x^2$)          -> Unicode text  (x²)            via latex_to_unicode()
  * equations on their own line ($$...$$) -> typeset picture, like a textbook, via render_png()

Typesetting uses matplotlib's built-in maths renderer ("mathtext"). It is
imported lazily on a background thread (preload()) so the app stays light
until maths is actually needed; until it's ready, equations fall back to Unicode.
"""
from __future__ import annotations

import functools
import io
import os
import re
import threading

import config

# ── LaTeX -> Unicode ─────────────────────────────────────────────────────────

_SYMBOLS = {
    "pm": "±", "mp": "∓", "times": "×", "div": "÷", "cdot": "·", "ast": "∗",
    "le": "≤", "leq": "≤", "ge": "≥", "geq": "≥", "ne": "≠", "neq": "≠",
    "approx": "≈", "equiv": "≡", "sim": "∼", "propto": "∝", "infty": "∞",
    "to": "→", "rightarrow": "→", "leftarrow": "←", "Rightarrow": "⇒",
    "Leftarrow": "⇐", "Leftrightarrow": "⇔", "implies": "⇒", "iff": "⇔",
    "therefore": "∴", "because": "∵", "degree": "°", "circ": "°", "angle": "∠",
    "perp": "⊥", "parallel": "∥", "triangle": "△", "partial": "∂", "nabla": "∇",
    "sum": "Σ", "prod": "Π", "int": "∫", "oint": "∮", "in": "∈", "notin": "∉",
    "subset": "⊂", "subseteq": "⊆", "cup": "∪", "cap": "∩", "emptyset": "∅",
    "forall": "∀", "exists": "∃", "neg": "¬", "land": "∧", "lor": "∨",
    "ldots": "…", "cdots": "⋯", "dots": "…", "prime": "′", "%": "%", "$": "$",
    "{": "{", "}": "}", "_": "_", "&": "&", "#": "#", "|": "‖",
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
    "varepsilon": "ε", "zeta": "ζ", "eta": "η", "theta": "θ", "vartheta": "ϑ",
    "iota": "ι", "kappa": "κ", "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ",
    "pi": "π", "rho": "ρ", "sigma": "σ", "tau": "τ", "upsilon": "υ", "phi": "φ",
    "varphi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ", "Pi": "Π",
    "Sigma": "Σ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
}
_FUNCS = {"sin", "cos", "tan", "sec", "csc", "cot", "arcsin", "arccos", "arctan",
          "sinh", "cosh", "tanh", "log", "ln", "exp", "lim", "max", "min", "det", "gcd"}
_SPACES = {",": " ", ";": " ", ":": " ", "!": "", " ": " ", "quad": "  ", "qquad": "   "}
_IGNORE = {"left", "right", "displaystyle", "textstyle", "big", "Big", "bigg", "Bigg",
           "limits", "nolimits"}
_UNWRAP = {"text", "mathrm", "textrm", "mathbf", "textbf", "mathit", "textit", "mathsf",
           "operatorname", "boxed", "cancel", "mbox", "mathbb", "mathcal", "underline"}

_SUP = dict(zip("0123456789+-=()niaxyk", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱᵃˣʸᵏ"))
_SUP["−"] = "⁻"
_SUB = dict(zip("0123456789+-=()aeoxhklmnpstij", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₒₓₕₖₗₘₙₚₛₜᵢⱼ"))


def _group(s: str, i: int) -> tuple[str, int]:
    """Read one argument at s[i]: a {braced group}, a \\command, or one character."""
    while i < len(s) and s[i] == " ":
        i += 1
    if i >= len(s):
        return "", i
    if s[i] == "{":
        depth, j = 0, i
        while j < len(s):
            if s[j] == "{" and (j == 0 or s[j - 1] != "\\"):
                depth += 1
            elif s[j] == "}" and s[j - 1] != "\\":
                depth -= 1
                if depth == 0:
                    return s[i + 1:j], j + 1
            j += 1
        return s[i + 1:], len(s)
    if s[i] == "\\":
        m = re.match(r"\\([A-Za-z]+|.)", s[i:])
        return m.group(0), i + m.end()
    return s[i], i + 1


def _needs_brackets(u: str) -> bool:
    return len(u) > 1 and bool(re.search(r"[\s+\-−±×÷/=<>≤≥]", u.strip()))


def _script(u: str, table: dict, mark: str) -> str:
    u = u.strip()
    if u and all(c in table for c in u):
        return "".join(table[c] for c in u)
    return f"{mark}({u})" if len(u) > 1 else f"{mark}{u}"


def latex_to_unicode(s: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(s):
        c = s[i]
        if c == "\\":
            m = re.match(r"\\([A-Za-z]+|.)", s[i:])
            name = m.group(1)
            i += m.end()
            if name in ("frac", "dfrac", "tfrac", "cfrac"):
                a, i = _group(s, i)
                b, i = _group(s, i)
                ua, ub = latex_to_unicode(a), latex_to_unicode(b)
                ua = f"({ua})" if _needs_brackets(ua) else ua
                # A denominator like "2a" needs brackets: 1/2a would read as (1/2)a
                simple = re.fullmatch(r"[\d.]+|[A-Za-zα-ωΑ-Ω]", ub)
                ub = f"({ub})" if len(ub) > 1 and not simple else ub
                out.append(f"{ua}/{ub}")
            elif name == "sqrt":
                n = ""
                if i < len(s) and s[i] == "[":
                    j = s.find("]", i)
                    n, i = s[i + 1:j], j + 1
                a, i = _group(s, i)
                ua = latex_to_unicode(a)
                root = {"3": "∛", "4": "∜"}.get(n.strip(), (_script(n, _SUP, "^") if n else "") + "√")
                out.append(root + (f"({ua})" if len(ua) > 1 and not ua.isalnum() else ua))
            elif name in _UNWRAP:
                a, i = _group(s, i)
                out.append(latex_to_unicode(a))
            elif name in ("vec", "overrightarrow"):
                a, i = _group(s, i)
                out.append(latex_to_unicode(a) + "\u20d7")
            elif name in ("bar", "overline"):
                a, i = _group(s, i)
                out.append("".join(ch + "\u0305" for ch in latex_to_unicode(a)))
            elif name == "hat":
                a, i = _group(s, i)
                out.append(latex_to_unicode(a) + "\u0302")
            elif name in ("begin", "end"):
                _, i = _group(s, i)
            elif name in _SYMBOLS:
                out.append(_SYMBOLS[name])
            elif name in _SPACES:
                out.append(_SPACES[name])
            elif name in _FUNCS:
                out.append(name + (" " if i < len(s) and s[i] not in "(^_{" else ""))
            elif name == "\\":
                out.append("; ")
            elif name not in _IGNORE:
                out.append(name)
        elif c in "^_":
            a, i = _group(s, i + 1)
            if c == "^" and a in ("\\circ", "{\\circ}", "\\degree"):
                out.append("°")
            elif c == "^" and a in ("\\prime", "'"):
                out.append("′")
            else:
                u = latex_to_unicode(a)
                out.append(_script(u, _SUP, "^") if c == "^" else _script(u, _SUB, "_"))
        elif c in "{}":
            i += 1
        elif c == "&":
            i += 1
        elif c == "-":
            out.append("−")
            i += 1
        elif c == "~":
            out.append(" ")
            i += 1
        else:
            out.append(c)
            i += 1
    text = "".join(out)
    text = re.sub(r"\s*([=<>≤≥≠≈±×÷→⇒])\s*", r" \1 ", text)   # tidy spacing
    text = re.sub(r"(?<=[(\[^_]) | (?=[)\]])", "", text)
    return re.sub(r" {2,}", " ", text).strip()


# ── LaTeX -> picture ─────────────────────────────────────────────────────────

_ready = threading.Event()
_loading = threading.Lock()
_mpl: dict = {}


def preload() -> None:
    """Import matplotlib in the background (first ever run builds a font cache)."""
    if _ready.is_set() or _loading.locked():
        return

    def _run():
        with _loading:
            if _ready.is_set():
                return
            try:
                os.environ.setdefault("MPLCONFIGDIR", str(config.DATA_DIR / "matplotlib"))
                import matplotlib
                matplotlib.use("Agg")
                from matplotlib.figure import Figure
                from matplotlib.font_manager import FontProperties
                from matplotlib.mathtext import MathTextParser
                _mpl.update(matplotlib=matplotlib, Figure=Figure,
                            FontProperties=FontProperties, parser=MathTextParser("path"))
                _ready.set()
            except Exception as e:
                config.log(f"[mathfmt] matplotlib unavailable: {e}")

    threading.Thread(target=_run, daemon=True).start()


def is_ready() -> bool:
    return _ready.is_set()


def display_lines(latex: str) -> list[str]:
    """Split a display block into renderable lines and swap unsupported commands."""
    s = latex.strip()
    s = re.sub(r"\\begin\{(aligned|align\*?|gather\*?|split|cases|array|eqnarray\*?)\}(\{[^}]*\})?", "", s)
    s = re.sub(r"\\end\{(aligned|align\*?|gather\*?|split|cases|array|eqnarray\*?)\}", "", s)
    lines = [ln.replace("&", "").strip() for ln in re.split(r"\\\\(?:\[[^\]]*\])?", s)]
    return [ln for ln in lines if ln]


def _for_mathtext(s: str) -> str:
    """Rewrite commands matplotlib's renderer doesn't know into ones it does."""
    # Full-size fractions (like a textbook), not the small inline style
    s = re.sub(r"\\(frac|tfrac|cfrac)\b", r"\\dfrac", s)
    s = re.sub(r"\\(mbox|textrm|textbf|textit)\b", r"\\mathrm", s)
    # \boxed{x} -> {x} etc. (just drop the decoration)
    s = re.sub(r"\\(boxed|cancel|displaystyle|textstyle|limits|nolimits)\b", "", s)
    s = re.sub(r"\\(implies)\b", r"\\Rightarrow", s)
    s = re.sub(r"\\(iff)\b", r"\\Leftrightarrow", s)
    s = re.sub(r"\\degree\b", r"^\\circ", s)
    s = re.sub(r"\\le\b", r"\\leq", s)
    s = re.sub(r"\\ge\b", r"\\geq", s)
    # Primes: f'(x) draws with an odd raised gap in mathtext; \prime sits correctly
    s = re.sub(r"\^\{?\\prime\}?", r"\\prime", s)
    s = re.sub(r"'", r"\\prime ", s)
    # Thin space before sin/cos/log… after a number or variable: "6x sin x", not "6xsin x"
    s = re.sub(r"(?<=[\w)}])\s*\\(" + "|".join(sorted(_FUNCS, key=len, reverse=True)) + r")\b",
               r"\\,\\\1", s)
    return s


@functools.lru_cache(maxsize=128)
def render_png(latex: str, color: str = "#1A1A1A", dpi: int = 100,
               fontsize: float = 15, background: str | None = None) -> bytes | None:
    """Typeset one line of LaTeX. Returns PNG bytes, or None if it can't be drawn."""
    if not _ready.is_set():
        return None
    mpl = _mpl["matplotlib"]
    try:
        with mpl.rc_context({"mathtext.fontset": "stix"}):
            s = f"${_for_mathtext(latex)}$"
            prop = _mpl["FontProperties"](size=fontsize)
            width, height, depth, _, _ = _mpl["parser"].parse(s, dpi=72, prop=prop)
            if width <= 0 or height <= 0:
                return None
            fig = _mpl["Figure"](figsize=(width / 72, height / 72))
            fig.text(0, depth / height, s, fontproperties=prop, color=color)
            buf = io.BytesIO()
            fig.savefig(buf, dpi=dpi, format="png", transparent=background is None,
                        facecolor=background or "none")
            return buf.getvalue()
    except Exception:
        return None

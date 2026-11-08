"""
Tiny Markdown subset for AI replies — no dependencies.

Small models use Markdown even when asked not to, so instead of fighting it
we render the common bits: **bold**, *italic*, `code`, # headings,
- / * / + bullets and 1. numbered lists. Anything else shows as plain text.

Maths:
  * inline $...$ / \\(...\\)                -> Unicode text, tagged "math"
  * a line that is just $$...$$ / \\[...\\]  -> one ("<latex>", ("display",)) segment,
    which the result window draws as a typeset picture. Multi-line $$ blocks
    are handled by LineFormatter.

Segments are [(text, tags)] that the result window inserts into a Tk Text
widget with matching tag styles.
"""
from __future__ import annotations

import re

from mathfmt import latex_to_unicode

Segments = list[tuple[str, tuple[str, ...]]]

_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_BULLET  = re.compile(r"^(\s*)(?:[-*+•▪●]|•)\s+(.*)$")
_NUMBER  = re.compile(r"^(\s*)(\d{1,2})[.)]\s+(.*)$")
_RULE    = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")
# Order matters: bold before italic
_INLINE  = re.compile(r"\*\*(.+?)\*\*|__(.+?)__|`([^`]+)`|(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])")

# $x$ needs non-space just inside both dollars and no digit after the closing one,
# so prices like "$5 and $10" are left alone.
_INLINE_MATH = re.compile(
    r"\$\$(.+?)\$\$|\\\((.+?)\\\)|(?<![\\$\w])\$(?!\s)([^$\n]+?)(?<![\s\\])\$(?![\w$])")
_DISPLAY_LINE = re.compile(r"^\s*(?:\$\$(.+?)\$\$|\\\[(.+?)\\\])\s*[.,;]?\s*$")
_PH = re.compile("\x00(\\d+)\x00")


def _inline(text: str, base: tuple[str, ...]) -> Segments:
    # Protect inline maths from the Markdown rules, then put it back as Unicode
    maths: list[str] = []

    def _stash(m: re.Match) -> str:
        maths.append(next(g for g in m.groups() if g is not None))
        return f"\x00{len(maths) - 1}\x00"

    text = _INLINE_MATH.sub(_stash, text)
    out: Segments = []
    for t, tags in _markdown(text, base):
        if not maths or "\x00" not in t:
            out.append((t, tags))
            continue
        pos = 0
        for m in _PH.finditer(t):
            if m.start() > pos:
                out.append((t[pos:m.start()], tags))
            out.append((latex_to_unicode(maths[int(m.group(1))]), tags + ("math",)))
            pos = m.end()
        if pos < len(t):
            out.append((t[pos:], tags))
    return out


def _markdown(text: str, base: tuple[str, ...]) -> Segments:
    out: Segments = []
    pos = 0
    for m in _INLINE.finditer(text):
        if m.start() > pos:
            out.append((text[pos:m.start()], base))
        bold, bold2, code, italic = m.groups()
        if bold is not None or bold2 is not None:
            # allow *italic* inside **bold**
            out.extend(_markdown(bold if bold is not None else bold2, base + ("bold",)))
        elif code is not None:
            out.append((code, base + ("code",)))
        else:
            out.append((italic, base + ("italic",)))
        pos = m.end()
    if pos < len(text):
        out.append((text[pos:], base))
    # Unmatched markers (e.g. a "**" still streaming in) are hidden, not shown raw
    return [(t.replace("**", ""), tags) for t, tags in out if t.replace("**", "")]


def parse_line(line: str) -> Segments:
    """Format one line (without its newline)."""
    if _RULE.match(line):
        return []
    m = _DISPLAY_LINE.match(line)
    if m:
        return [((m.group(1) or m.group(2)).strip(), ("display",))]
    m = _HEADING.match(line)
    if m:
        return _inline(m.group(2), ("heading",))
    m = _BULLET.match(line)
    if m:
        tag = "bullet2" if len(m.group(1).expandtabs(4)) >= 2 else "bullet"
        return [("•  ", (tag,))] + _inline(m.group(2), (tag,))
    m = _NUMBER.match(line)
    if m:
        return [(f"{m.group(2)}.  ", ("bullet",))] + _inline(m.group(3), ("bullet",))
    return _inline(line, ())


def _opens_block(s: str) -> bool:
    return s.startswith(("$$", "\\[")) and not _DISPLAY_LINE.match(s)


class LineFormatter:
    """Formats complete lines one at a time, collecting multi-line $$ … $$ blocks."""

    def __init__(self) -> None:
        self._block: list[str] | None = None

    def feed(self, line: str) -> Segments | None:
        """Segments for a complete line, or None if it was swallowed into a block."""
        s = line.strip()
        if self._block is not None:
            if s.endswith(("$$", "\\]")):
                self._block.append(s[:-2])
                return self.flush()
            self._block.append(s)
            return None
        if _opens_block(s):
            rest = s[2:]
            self._block = []
            if rest.endswith(("$$", "\\]")):       # "$$ a \\ b $$" style one-liner
                self._block.append(rest[:-2])
                return self.flush()
            self._block.append(rest)
            return None
        return parse_line(line)

    def preview(self, partial: str) -> Segments:
        """Segments for the line still streaming in (hidden while inside maths)."""
        if self._block is not None or _opens_block(partial.strip()):
            return []
        return parse_line(partial)

    def flush(self) -> Segments | None:
        """Close an open block (end of reply)."""
        if self._block is None:
            return None
        parts = [p.strip() for p in self._block if p.strip()]
        self._block = None
        if not parts:
            return []
        # Each source line inside a block is its own step of working
        return [(" \\\\ ".join(p.rstrip("\\").strip() for p in parts), ("display",))]


def parse(text: str) -> Segments:
    """Format a whole reply. Collapses runs of blank lines."""
    out: Segments = []
    fmt = LineFormatter()
    blank = 0
    first = True
    lines = text.split("\n")
    for idx, line in enumerate(lines):
        segs = fmt.feed(line)
        if segs is None:
            if idx == len(lines) - 1:
                segs = fmt.flush() or []
            else:
                continue
        if not segs and not line.strip():
            blank += 1
            if blank > 1:
                continue
        else:
            blank = 0
        if not first:
            out.append(("\n", ()))
        first = False
        out.extend(segs)
    return out


def to_plain(text: str) -> str:
    """Strip Markdown (and turn maths into Unicode) for places that can't style text."""
    parts = []
    for t, tags in parse(text):
        parts.append(latex_to_unicode(t).replace("\\\\", ";") if "display" in tags else t)
    return "".join(parts).strip()

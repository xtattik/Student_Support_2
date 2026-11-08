"""
Tiny Markdown subset for AI replies — no dependencies.

Small models use Markdown even when asked not to, so instead of fighting it
we render the common bits: **bold**, *italic*, `code`, # headings,
- / * / + bullets and 1. numbered lists. Anything else shows as plain text.

parse_line() returns [(text, tags)] segments that the result window inserts
into a Tk Text widget with matching tag styles.
"""
from __future__ import annotations

import re

_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_BULLET  = re.compile(r"^(\s*)(?:[-*+•▪●]|•)\s+(.*)$")
_NUMBER  = re.compile(r"^(\s*)(\d{1,2})[.)]\s+(.*)$")
_RULE    = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")
# Order matters: bold before italic
_INLINE  = re.compile(r"\*\*(.+?)\*\*|__(.+?)__|`([^`]+)`|(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])")


def _inline(text: str, base: tuple[str, ...]) -> list[tuple[str, tuple[str, ...]]]:
    out: list[tuple[str, tuple[str, ...]]] = []
    pos = 0
    for m in _INLINE.finditer(text):
        if m.start() > pos:
            out.append((text[pos:m.start()], base))
        bold, bold2, code, italic = m.groups()
        if bold is not None or bold2 is not None:
            # allow *italic* inside **bold**
            out.extend(_inline(bold if bold is not None else bold2, base + ("bold",)))
        elif code is not None:
            out.append((code, base + ("code",)))
        else:
            out.append((italic, base + ("italic",)))
        pos = m.end()
    if pos < len(text):
        out.append((text[pos:], base))
    # Unmatched markers (e.g. a "**" still streaming in) are hidden, not shown raw
    return [(t.replace("**", ""), tags) for t, tags in out if t.replace("**", "")]


def parse_line(line: str) -> list[tuple[str, tuple[str, ...]]]:
    """Format one line (without its newline)."""
    if _RULE.match(line):
        return []
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


def parse(text: str) -> list[tuple[str, tuple[str, ...]]]:
    """Format a whole reply. Collapses runs of blank lines."""
    out: list[tuple[str, tuple[str, ...]]] = []
    blank = 0
    for i, line in enumerate(text.split("\n")):
        segs = parse_line(line)
        if not segs and not line.strip():
            blank += 1
            if blank > 1:
                continue
        else:
            blank = 0
        if i:
            out.append(("\n", ()))
        out.extend(segs)
    return out


def to_plain(text: str) -> str:
    """Strip Markdown for places that can't style text (quiz labels)."""
    return "".join(t for t, _ in parse(text)).strip()

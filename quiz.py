"""Quiz validation and marking — done in code, so scores are always right."""
from __future__ import annotations

import re

LETTERS = "ABCD"
_PREFIX = re.compile(r"^\s*(?:[A-Da-d][\).:]\s+|\([A-Da-d]\)\s+)")


def clean_quiz(data: dict) -> list[dict]:
    """Normalise model output into [{question, options{A..D}, answer, explanation}].
    Drops malformed questions rather than showing something broken."""
    out = []
    for q in (data or {}).get("questions", []):
        try:
            question = str(q["question"]).strip()
            opts = [str(o).strip() for o in q["options"]][:4]
            answer = str(q["answer"]).strip().upper()[:1]
            explanation = str(q.get("explanation", "")).strip()
        except (KeyError, TypeError):
            continue
        # Some models repeat the letter inside the option ("A) Paris")
        opts = [_PREFIX.sub("", o) for o in opts]
        if not question or len(opts) != 4 or any(not o for o in opts) or answer not in LETTERS:
            continue
        if len(set(o.lower() for o in opts)) < 4:  # duplicate options
            continue
        out.append({
            "question": question,
            "options": dict(zip(LETTERS, opts)),
            "answer": answer,
            "explanation": explanation,
        })
    return out


def mark(questions: list[dict], answers: list[str]) -> tuple[int, list[bool]]:
    results = [a == q["answer"] for q, a in zip(questions, answers)]
    return sum(results), results

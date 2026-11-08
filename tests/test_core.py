import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import llm_engine  # noqa: E402
from prompts import QUIZ_SCHEMA, get_prompts  # noqa: E402
from quiz import clean_quiz, mark  # noqa: E402


def _q(question="Q?", options=("a", "b", "c", "d"), answer="B", explanation="because"):
    return {"question": question, "options": list(options), "answer": answer,
            "explanation": explanation}


def test_clean_quiz_normalises_and_strips_letter_prefixes():
    data = {"questions": [_q(options=("A) Paris", "B) Rome", "(C) Oslo", "D. Bern"))]}
    out = clean_quiz(data)
    assert out[0]["options"] == {"A": "Paris", "B": "Rome", "C": "Oslo", "D": "Bern"}
    assert out[0]["answer"] == "B"


def test_clean_quiz_drops_malformed():
    data = {"questions": [
        _q(options=("a", "b", "c")),            # too few options
        _q(answer="E"),                          # bad answer letter
        _q(options=("x", "x", "y", "z")),       # duplicate options
        {"question": "missing fields"},
        _q(),                                    # the only good one
    ]}
    assert len(clean_quiz(data)) == 1
    assert clean_quiz({}) == []
    assert clean_quiz(None) == []


def test_mark():
    qs = clean_quiz({"questions": [_q(answer="A"), _q(answer="B"), _q(answer="C")]})
    score, results = mark(qs, ["A", "C", "C"])
    assert score == 2 and results == [True, False, True]


def test_trim_input():
    short, t = llm_engine.trim_input("  hello  ")
    assert short == "hello" and not t
    long_text = ("This is a sentence. " * 2000)
    cut, t = llm_engine.trim_input(long_text)
    assert t and len(cut) <= llm_engine.MAX_INPUT_CHARS and cut.endswith(".")


def test_parse_sse_line():
    chunk = {"choices": [{"delta": {"content": "Hi"}}]}
    assert llm_engine.parse_sse_line("data: " + json.dumps(chunk)) == "Hi"
    assert llm_engine.parse_sse_line("data: [DONE]") is None
    assert llm_engine.parse_sse_line(": keep-alive") == ""
    assert llm_engine.parse_sse_line('data: {"choices":[{"delta":{}}]}') == ""


def test_server_args_gpu_and_cpu(monkeypatch, tmp_path):
    monkeypatch.setattr(llm_engine, "server_exe", lambda: tmp_path / "llama-server")
    gpu = llm_engine._server_args(tmp_path / "m.gguf", 1234, use_gpu=True)
    cpu = llm_engine._server_args(tmp_path / "m.gguf", 1234, use_gpu=False)
    assert "--sleep-idle-seconds" in gpu and "--reasoning-budget" in gpu
    assert gpu[gpu.index("--host") + 1] == "127.0.0.1"
    assert "none" in cpu and "all" in gpu


def test_prompts_and_schema():
    for junior in (False, True):
        p = get_prompts(junior)
        assert set(p) == {"explain", "summarise", "simplify", "test_me"}
    q = QUIZ_SCHEMA["properties"]["questions"]
    assert q["minItems"] == q["maxItems"] == 3


def test_existing_models_are_listed():
    from model_manager import is_model_file
    # v1 / user-supplied models still count
    assert is_model_file("Qwen2.5-3B-Instruct-Q4_K_M.gguf")
    assert is_model_file("Qwen2.5-7B-Instruct-Q4_K_M.gguf")
    assert is_model_file("Some-Model.GGUF")
    # split models: only part 1 is shown
    assert is_model_file("big-model-Q4_K_M-00001-of-00003.gguf")
    assert not is_model_file("big-model-Q4_K_M-00002-of-00003.gguf")
    # helper files and partial downloads are hidden
    assert not is_model_file("mmproj-gemma-4-E4B-it-Q8_0.gguf")
    assert not is_model_file("mtp-gemma-4-E4B-it-Q4_0.gguf")
    assert not is_model_file("Qwen3.5-2B-Q4_K_M.gguf.part")


def test_markdown_lite():
    from markdown_lite import parse, parse_line, to_plain
    assert parse_line("Plain **bold** and *it* `x`") == [
        ("Plain ", ()), ("bold", ("bold",)), (" and ", ()), ("it", ("italic",)), (" ", ()), ("x", ("code",))]
    assert parse_line("- **Marx** said") == [("•  ", ("bullet",)), ("Marx", ("bullet", "bold")), (" said", ("bullet",))]
    assert parse_line("• already a bullet")[0] == ("•  ", ("bullet",))
    assert parse_line("  * nested")[0] == ("•  ", ("bullet2",))
    assert parse_line("2. second")[0] == ("2.  ", ("bullet",))
    assert parse_line("## Heading") == [("Heading", ("heading",))]
    assert parse_line("---") == []
    # half-streamed bold markers are hidden, not shown raw
    assert parse_line("The **Bourg") == [("The Bourg", ())]
    # maths / multiplication stars are left alone
    assert to_plain("2 * 3 * 4") == "2 * 3 * 4"
    assert to_plain("**A** is *b*") == "A is b"
    # blank-line runs collapse
    assert "".join(t for t, _ in parse("a\n\n\n\nb")) == "a\n\nb"


def test_quiz_strips_markdown():
    q = clean_quiz({"questions": [_q(question="What is **mitosis**?",
                                      options=("**A** cell", "b", "c", "d"))]})
    assert q[0]["question"] == "What is mitosis?" and q[0]["options"]["A"] == "A cell"


def test_stream_decodes_utf8():
    import io
    import requests
    r = requests.models.Response()
    r.status_code = 200
    body = 'data: {"choices":[{"delta":{"content":"• Marx"}}]}\n\ndata: [DONE]\n\n'
    r.raw = io.BytesIO(body.encode("utf-8"))
    r.headers["Content-Type"] = "text/event-stream"
    assert requests.utils.get_encoding_from_headers(r.headers) in (None, "ISO-8859-1")
    r.encoding = "utf-8"   # what llm_engine._post now does
    lines = [llm_engine.parse_sse_line(x) for x in r.iter_lines(decode_unicode=True) if x]
    assert lines[0] == "• Marx"


def test_latex_to_unicode():
    from mathfmt import latex_to_unicode as u
    assert u(r"x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}") == "x = (−b ± √(b² − 4ac))/(2a)"
    assert u(r"\frac{3}{4}") == "3/4"
    assert u(r"2x^2 - 8x + 6 = 0") == "2x² − 8x + 6 = 0"
    assert u(r"90^\circ") == "90°"
    assert u(r"x_1 + x_2") == "x₁ + x₂"
    assert u(r"\theta = \tan^{-1}\left(\frac{3}{4}\right)") == "θ = tan⁻¹(3/4)"
    assert u(r"v = 12\,\text{m/s}") == "v = 12 m/s"
    assert u(r"\sqrt[3]{27} = 3") == "∛27 = 3"
    assert u(r"\boxed{x = 3}") == "x = 3"


def test_display_lines_split_aligned_blocks():
    from mathfmt import display_lines
    block = r"\begin{aligned} 2x + 3 &= 11 \\ 2x &= 8 \\ x &= 4 \end{aligned}"
    assert display_lines(block) == ["2x + 3 = 11", "2x = 8", "x = 4"]


def test_markdown_maths():
    from markdown_lite import LineFormatter, parse_line, to_plain
    # inline maths becomes Unicode, tagged so it isn't mistaken for markdown
    segs = parse_line(r"Here $a = 2$ and **$x^2$** matter")
    assert ("a = 2", ("math",)) in segs and ("x²", ("bold", "math")) in segs
    # prices are not maths
    assert to_plain("It costs $5 and $10 today") == "It costs $5 and $10 today"
    # a line that is only an equation becomes a display segment
    assert parse_line(r"$$x = \frac{8 \pm 4}{4}$$") == [(r"x = \frac{8 \pm 4}{4}", ("display",))]
    assert parse_line(r"\[ y = mx + c \]") == [("y = mx + c", ("display",))]
    # multi-line $$ blocks are collected, one step per line
    f = LineFormatter()
    assert f.feed("$$") is None and f.feed("2x = 8") is None
    assert f.feed("x = 4") is None
    assert f.feed("$$") == [(r"2x = 8 \\ x = 4", ("display",))]
    # half-streamed display maths is hidden rather than shown raw
    assert f.preview(r"$$x = \frac{8") == []
    # quiz/plain text gets readable symbols
    assert to_plain(r"Solve $x^2 = 9$") == "Solve x² = 9"

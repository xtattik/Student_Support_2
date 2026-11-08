# Student AI Support 2 — Marsden Park Anglican College

A private, local AI study tool. Highlight any text on your screen, press a keyboard shortcut, and get instant help — no internet required after setup, no accounts, and nothing leaves your device.

> **Version 2** is a lighter, faster rebuild of [Student AI Support](https://github.com/xtattik/Student_AI_Support). It replaces version 1 and uses the same models folder, so models you already downloaded keep working.

---

## What it does

Press **Ctrl+Shift+`** after highlighting any text — in a document, a webpage, a PDF, anything — and choose:

| Option | What you get |
|---|---|
| **Explain this** | A plain-English explanation (with a "Simpler please" button) |
| **Summarise this** | Key points as bullet points |
| **Test me on this** | 3 multiple-choice questions, marked instantly with explanations |

**Junior mode** (tray menu or Settings) switches to simpler language for ages 9–10.

### Maths

Highlight a maths problem or worked example and choose **Explain this** — the AI works through it step by step. Equations are drawn the way they look in a textbook (proper fractions, square roots, powers), one step per line.

- **Click an equation** to copy it as a picture, then paste it into OneNote, Word, Google Docs etc.
- **Right-click an equation** to copy it as text instead (e.g. `x = (8 ± 4)/4`).

> Small AI models can make arithmetic slips in long working. The **Stronger** model (Settings) is more reliable for senior maths. Maths copied from PDFs can lose its formatting (x² may arrive as x2) — check the question looks right.

### What's new in version 2

- **Faster answers** — uses llama.cpp's official engine, which uses all of your processor's speed-ups and, where available, the laptop's graphics chip.
- **Lighter when idle** — the AI only starts when you first press the shortcut, and unloads itself from memory after 10 minutes unused.
- **Smaller download** — the standard model is ~1.3 GB (was 1.9 GB), and there's a 0.7 GB *Lite* model for older laptops.
- **Instant, accurate quiz marking** — the answers are checked by the app, not by asking the AI a second time.
- **Resumable downloads** — if the download drops out on school Wi-Fi, press Retry and it carries on.
- Closing a window stops the AI working straight away (saves battery).

---

## For Windows Students

1. Go to the [Releases page](../../releases) and download **StudentAI2-Windows.zip**
2. Right-click the zip → **Extract All** → choose a location (e.g. Documents)
3. Open the `StudentAI` folder and double-click **StudentAI.exe**
   > If you see *"Windows protected your PC"*, click **More info** → **Run anyway**. This appears because the app isn't signed with a paid certificate.
4. **First time only:** choose **Standard** (recommended) or **Lite** (older laptops), then click **Start Download**.
   > Default model location: `%LOCALAPPDATA%\StudentAI\models\` (not synced by OneDrive)
5. A small icon appears in your system tray (near the clock). Highlight text → press **Ctrl+Shift+`** → choose an option.

**To quit:** right-click the tray icon → **Quit**

## For Mac Students (Apple Silicon — M1 or newer)

1. Download **StudentAI2-macOS.zip** from the [Releases page](../../releases) and double-click it
2. **First time only:** right-click **StudentAI.app** → **Open** → **Open** (the app isn't signed with a paid Apple certificate)
3. When asked, allow keyboard access: **Open System Settings** → find **Student AI Support** → toggle **on**
4. Choose a model and click **Start Download**
   > Default model location: `~/Library/Application Support/StudentAI/models/`
5. Use it from the menu-bar icon (top-right). Highlight text → **Ctrl+Shift+`**

---

## Models

| Model | Download | Best for |
|---|---|---|
| **Standard** — Qwen3.5 2B (default) | ~1.3 GB | Most laptops, all subjects |
| **Lite** — LFM2.5 1.2B | ~0.7 GB | Old or low-memory laptops (fastest) |
| **Stronger** — Qwen3.5 4B | ~2.7 GB | Laptops with 8 GB+ RAM |
| **Gemma 4 E4B** | ~5.0 GB | Laptops with 16 GB RAM |

Switch or download models in **Settings**.

### Using your own / existing models

Any `.gguf` model file in the models folder shows up in **Settings → Active Model** — including the Qwen2.5 models from version 1, or anything else you've downloaded (e.g. a bigger model for a stronger PC). If you keep models somewhere else, point the app at that folder in **Settings → Advanced → Change folder…**.

- Version 2's engine is newer than version 1's, so it runs everything v1 could, plus newer model families.
- Split models (`…-00001-of-00003.gguf`) work — only part 1 is listed.
- "Thinking" models (e.g. Qwen3) are told to answer directly, so they don't waste time reasoning.
- If the chosen model isn't in the folder any more, the app uses another one it finds.

### Upgrading from version 1

Quit version 1 (tray icon → Quit), then extract version 2 over the top of your existing StudentAI folder (or replace StudentAI.app on Mac). Your models, hotkey, junior mode and launch-at-login setting are kept.

### Manual model download

If the download is blocked on school Wi-Fi, download the file at home and copy it into the models folder (paths above):

- Standard: [Qwen3.5-2B-Q4_K_M.gguf](https://huggingface.co/unsloth/Qwen3.5-2B-GGUF/resolve/main/Qwen3.5-2B-Q4_K_M.gguf?download=true)
- Lite: [LFM2.5-1.2B-Instruct-Q4_K_M.gguf](https://huggingface.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF/resolve/main/LFM2.5-1.2B-Instruct-Q4_K_M.gguf?download=true)

Then launch the app — it will show **"✓ Model found"** and you can click Continue.

---

## Troubleshooting

**Nothing happens when I press the shortcut** — check the tray icon is still there; make sure text is highlighted; change the shortcut in Settings if another app uses it.

**"No text selected"** — in Adobe Reader / PDF viewers, copy the text first (Ctrl+C), then press the shortcut.

**The first answer is slow** — the AI is starting up (a few seconds). It's faster after that, until it's been unused for 10 minutes.

**Answers are garbled, or the app crashes when answering** — Settings → Advanced → turn off **Use graphics chip when available**. (The app also does this automatically if the graphics chip fails to start.)

**Logs** — `error.log` and `llama-server.log` are in the StudentAI data folder (`%LOCALAPPDATA%\StudentAI` on Windows, `~/Library/Application Support/StudentAI` on Mac).

---

## For Teachers — Building and Releasing

### Releases
GitHub Actions builds Windows and Mac versions when you push a version tag:
```
git tag v2.0.0
git push origin v2.0.0
```
Both zips are attached to a new Release within ~5 minutes. You can also run the workflow manually from the **Actions** tab to get test builds (downloadable as artifacts) without making a release.

Remember to bump `VERSION` in `config.py` first so "Check for updates" works.

### How it works
- `app.py` — tray app, hotkey, windows (Python + CustomTkinter)
- `llm_engine.py` — starts llama.cpp's `llama-server` as a background process on `127.0.0.1` when first needed. Uses Vulkan (Windows) / Metal (Mac) when available, falls back to CPU, unloads the model when idle, and runs at below-normal priority.
- `quiz.py` — the quiz is generated as structured data (guaranteed shape), and marked in code.
- The llama.cpp version is pinned in `scripts/fetch_llama_server.py` (`LLAMA_BUILD`). Bump it deliberately to pick up new model support.

### Running from source (Python 3.12+)
```
python -m venv .venv
.venv\Scripts\activate            # macOS: source .venv/bin/activate
pip install -r requirements.txt
python scripts/fetch_llama_server.py
python app.py
```
In development, settings and models are stored in `./data/`. Run tests with `pip install pytest` then `python -m pytest tests`.

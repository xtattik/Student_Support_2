import platform
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

IS_WINDOWS = platform.system() == "Windows"
IS_MAC     = platform.system() == "Darwin"

# llama-server and its libraries are shipped as plain files in bin/ — they are
# run as a separate process, so PyInstaller must not analyse or relink them.
bin_files = [(str(p), "bin") for p in Path("bin").iterdir() if p.name != ".gitkeep"]
if not any(Path(s).name.startswith("llama-server") for s, _ in bin_files):
    raise SystemExit("bin/ is empty — run: python scripts/fetch_llama_server.py")

a = Analysis(
    ["app.py"],
    pathex=["."],
    binaries=[],
    datas=[
        ("assets", "assets"),
        *bin_files,
        *collect_data_files("customtkinter"),
    ],
    hiddenimports=[
        "pystray._win32" if IS_WINDOWS else "pystray._darwin",
        "PIL._tkinter_finder",
    ],
    excludes=["numpy", "pandas", "matplotlib", "scipy", "IPython", "pytest"],
    hookspath=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="StudentAI",
    icon="assets/logo.png",
    console=False,
    windowed=True,
)

coll = COLLECT(exe, a.binaries, a.datas, name="StudentAI")

if IS_MAC:
    app = BUNDLE(
        coll,
        name="StudentAI.app",
        icon="assets/logo.png",
        bundle_identifier="au.edu.marsdenparkac.studentai2",
    )

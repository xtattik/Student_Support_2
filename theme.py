from PIL import Image
import customtkinter as ctk

# School colours — sampled from Marsden Park Anglican College logo
TEAL        = "#0D6B7A"
TEAL_HOVER  = "#0A5361"
TEAL_LIGHT  = "#1A8A9C"
SKY_BLUE    = "#47B8D4"
LIME_GREEN  = "#6DC23A"
CHARCOAL    = "#2C2C2C"
WHITE       = "#FFFFFF"
OFF_WHITE   = "#F4F7F8"

from config import ASSETS_DIR


def load_logo(size: tuple[int, int]) -> ctk.CTkImage:
    img = Image.open(ASSETS_DIR / "logo.png").convert("RGBA")
    return ctk.CTkImage(light_image=img, dark_image=img, size=size)


def load_logo_pil(size: tuple[int, int]) -> Image.Image:
    return Image.open(ASSETS_DIR / "logo.png").convert("RGBA").resize(size, Image.LANCZOS)


def set_window_icon(win) -> None:
    """Apply the school logo as the window title-bar / taskbar icon."""
    try:
        from PIL import ImageTk
        img = Image.open(ASSETS_DIR / "logo.png").convert("RGBA").resize((32, 32), Image.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        win.iconphoto(False, photo)
        win._icon_ref = photo  # keep a reference so GC doesn't destroy it
    except Exception:
        pass  # icon is purely cosmetic — never crash over it

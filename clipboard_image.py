"""Put a picture (PNG bytes) on the clipboard so students can paste equations into notes."""
from __future__ import annotations

import io
import platform
import time

import config


def _with_margin(png: bytes, margin: int = 16) -> bytes:
    """Add a white border so pasted equations don't sit flush against other content."""
    from PIL import Image
    img = Image.open(io.BytesIO(png)).convert("RGBA")
    out = Image.new("RGBA", (img.width + 2 * margin, img.height + 2 * margin), "white")
    out.paste(img, (margin, margin), img)
    buf = io.BytesIO()
    out.convert("RGB").save(buf, "PNG", dpi=(200, 200))
    return buf.getvalue()


def copy_png(png: bytes) -> bool:
    """Returns True if the picture was copied."""
    try:
        png = _with_margin(png)
        if platform.system() == "Windows":
            return _copy_windows(png)
        if platform.system() == "Darwin":
            return _copy_mac(png)
    except Exception as e:
        config.log(f"[clipboard_image] {e}")
    return False


def _copy_windows(png: bytes) -> bool:
    import ctypes
    from ctypes import wintypes

    from PIL import Image

    # Most apps read the classic bitmap format (no transparency, so flatten on white);
    # Office, OneNote and browsers also read the "PNG" format, which stays crisp.
    img = Image.open(io.BytesIO(png)).convert("RGBA")
    flat = Image.new("RGB", img.size, "white")
    flat.paste(img, mask=img.getchannel("A"))
    bmp = io.BytesIO()
    flat.save(bmp, "BMP")
    dib = bmp.getvalue()[14:]  # strip the BITMAPFILEHEADER

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
    user32.RegisterClipboardFormatW.restype = wintypes.UINT
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]

    def _put(fmt: int, data: bytes) -> None:
        h = kernel32.GlobalAlloc(0x0002, len(data))  # GMEM_MOVEABLE
        p = kernel32.GlobalLock(h)
        ctypes.memmove(p, data, len(data))
        kernel32.GlobalUnlock(h)
        user32.SetClipboardData(fmt, h)  # clipboard now owns the memory

    for _ in range(10):  # another app may briefly hold the clipboard
        if user32.OpenClipboard(None):
            break
        time.sleep(0.05)
    else:
        return False
    try:
        user32.EmptyClipboard()
        _put(8, dib)  # CF_DIB
        _put(user32.RegisterClipboardFormatW("PNG"), png)
    finally:
        user32.CloseClipboard()
    return True


def _copy_mac(png: bytes) -> bool:
    from AppKit import NSPasteboard, NSPasteboardTypePNG  # type: ignore[import]
    from Foundation import NSData  # type: ignore[import]

    pb = NSPasteboard.generalPasteboard()
    pb.clearContents()
    return bool(pb.setData_forType_(NSData.dataWithBytes_length_(png, len(png)), NSPasteboardTypePNG))

"""
Ensure only one copy of the app can run at a time.

Uses a TCP socket bound to localhost — works on Windows and macOS
without any platform-specific code or temp files.
"""
import socket

# Arbitrary port unlikely to clash with anything else.
# Only needs to be unique to this app on the local machine.
_LOCK_PORT = 47_823  # same as v1, so v1 and v2 never run at once
_sock: socket.socket | None = None


def acquire() -> bool:
    """
    Try to claim the single-instance lock.
    Returns True if this is the first (and only) instance.
    Returns False if another instance is already running.
    The socket stays open for the lifetime of the process.
    """
    global _sock
    _sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # SO_REUSEADDR would defeat the purpose — do NOT set it.
    try:
        _sock.bind(("127.0.0.1", _LOCK_PORT))
        return True
    except OSError:
        _sock.close()
        _sock = None
        return False

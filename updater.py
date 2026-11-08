"""
Lightweight update checker — queries the GitHub Releases API and compares
the latest tag to the current VERSION constant.  No auto-download; just
tells the user and points them at the releases page.
"""
import requests
from config import VERSION, GITHUB_REPO

_REPO         = GITHUB_REPO
_API_URL      = f"https://api.github.com/repos/{_REPO}/releases/latest"
RELEASES_URL  = f"https://github.com/{_REPO}/releases"


def _parse_ver(v: str) -> tuple[int, ...]:
    """Turn 'v1.9.3' or '1.9.3' into (1, 9, 3) for comparison."""
    try:
        return tuple(int(x) for x in v.lstrip("v").split(".") if x.isdigit())
    except Exception:
        return (0,)


def check() -> dict:
    """
    Returns a dict:
      status  : "up_to_date" | "update_available" | "error"
      current : current version string (no v prefix)
      latest  : latest tag from GitHub (e.g. "v1.10.0"), or "" on error
      url     : direct URL to the latest release page
      message : human-readable one-liner
    """
    try:
        r = requests.get(
            _API_URL, timeout=6,
            headers={"Accept": "application/vnd.github+json",
                     "User-Agent": "StudentAI2-updater"},
        )
        r.raise_for_status()
        data       = r.json()
        latest_tag = data.get("tag_name", "")
        url        = data.get("html_url", RELEASES_URL)

        if _parse_ver(latest_tag) > _parse_ver(VERSION):
            return {
                "status":  "update_available",
                "current": VERSION,
                "latest":  latest_tag,
                "url":     url,
                "message": f"{latest_tag} is available — click to download",
            }
        return {
            "status":  "up_to_date",
            "current": VERSION,
            "latest":  latest_tag,
            "url":     url,
            "message": f"You're on the latest version (v{VERSION})",
        }
    except Exception:
        return {
            "status":  "error",
            "current": VERSION,
            "latest":  "",
            "url":     RELEASES_URL,
            "message": "Could not check — verify your internet connection",
        }

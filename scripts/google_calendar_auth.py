"""Google Calendar OAuth setup helper.

Run inside the container once to authorize Zenith for Google Calendar:

    docker exec -it zenith python scripts/google_calendar_auth.py    (via source)

Or from the host:
    python google_calendar_auth.py

Prereqs (in .env):
  GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET (from Google Cloud console > OAuth app)
  GOOGLE_REDIRECT_URI (must match the OAuth app's configured redirect)

Prints a URL. Open it, authorize, paste the "code" param back. Writes
GOOGLE_REFRESH_TOKEN into .env so the calendar tools can get access tokens.

For CLI/desktop setups the redirect can be http://localhost (any port) with
"Desktop app" or "OOB" enabled — Google's OAuth lets native apps use
urn:ietf:wg:oauth:2.0:oob technically, but the modern flow uses the redirect
URI and you copy the ?code= from the browser after auth.
"""
from __future__ import annotations

import getpass
import os
import sys
import urllib.parse

import httpx

# Same constants the tools read.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)  # zenith/
_ENV_FILE = os.path.join(_PROJECT_ROOT, ".env")

_SCOPES = "https://www.googleapis.com/auth/calendar"
_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"


def _read_env() -> dict:
    env = {}
    if os.path.exists(_ENV_FILE):
        with open(_ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    return env


def _prompt(key: str, current: str, secret: bool = False) -> str:
    if current:
        print(f"  {key} (already set, Enter to keep) ", end="")
        val = input()
        return val.strip() or current
    if secret:
        return getpass.getpass(f"  {key}: ").strip()
    return input(f"  {key}: ").strip()


def main() -> None:
    print("Zenith — Google Calendar OAuth setup\n")
    env = _read_env()
    client_id = _prompt("GOOGLE_CLIENT_ID", env.get("GOOGLE_CLIENT_ID", ""))
    client_secret = _prompt("GOOGLE_CLIENT_SECRET", env.get("GOOGLE_CLIENT_SECRET", ""),
                            secret=True)
    redirect = _prompt("GOOGLE_REDIRECT_URI",
                       env.get("GOOGLE_REDIRECT_URI", "http://localhost:8000/oauth/callback"))

    if not client_id or not client_secret:
        print("\n✗ Need GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET (Google Cloud console).")
        sys.exit(1)

    params = {
        "client_id": client_id,
        "redirect_uri": redirect,
        "response_type": "code",
        "scope": _SCOPES,
        "access_type": "offline",
        "prompt": "consent",
    }
    auth_url = f"{_AUTH_URL}?{urllib.parse.urlencode(params)}"
    print(f"\nOpen this URL, authorize, then paste the '?code=' value back:")
    print(auth_url)
    code = input("\nAuthorization code (after redirect): ").strip()

    if code.startswith("http"):  # allow pasting the full redirect URL
        parsed = urllib.parse.urlparse(code)
        code = urllib.parse.parse_qs(parsed.query).get("code", [""])[0]
        code = code.strip()

    if not code:
        print("✗ No code provided.")
        sys.exit(1)

    print("\nExchanging code for refresh token…")
    payload = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect,
        "grant_type": "authorization_code",
    }
    resp = httpx.post(_TOKEN_URL, data=payload, timeout=30)
    if resp.status_code >= 400:
        print(f"✗ Exchange failed ({resp.status_code}): {resp.text[:300]}")
        sys.exit(1)
    data = resp.json()
    refresh = data.get("refresh_token")
    if not refresh:
        print(f"✗ No refresh_token in response (data: {data}) — you may need prompt=consent again.")
        sys.exit(1)

    # Persist.
    lines = open(_ENV_FILE).read() if os.path.exists(_ENV_FILE) else ""
    set_line = f"GOOGLE_REFRESH_TOKEN={refresh}\n"
    if "GOOGLE_REFRESH_TOKEN=" in lines:
        import re
        lines = re.sub(r"(?m)^GOOGLE_REFRESH_TOKEN=.*\n?", "", lines)
    if lines and not lines.endswith("\n"):
        lines += "\n"
    with open(_ENV_FILE, "w") as f:
        f.write(lines + set_line)

    print("\n✓ GOOGLE_REFRESH_TOKEN written to .env")
    print("  Restart the container for the tools to pick it up: docker compose up -d")


if __name__ == "__main__":
    main()
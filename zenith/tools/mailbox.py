"""Mailbox tool — zero-config disposable email via the Mail.tm API.

Unlike Zenith's real Gmail/Resend stack (which needs credentials in
.env), Mail.tm creates a throwaway mailbox on demand — no account, no secret.
Used for signup flows, verification links, and anything where Zenith doesn't
want to burn production credentials. Everything degrades gracefully.
"""
from __future__ import annotations

import json

import httpx

_API = "https://api.mail.tm"

_client = httpx.AsyncClient(
    base_url=_API,
    timeout=25,
    headers={"Accept": "application/json", "Content-Type": "application/json"},
)


async def create() -> str:
    """Create a fresh disposable inbox and return address + password."""
    import random
    import string

    address = (
        "zenith." + "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
        + "@"
        + await _domain()
    )
    password = "pk-" + "".join(random.choices(string.ascii_letters + string.digits, k=16))

    resp = await _client.post(
        "/accounts", json={"address": address, "password": password}
    )
    if resp.status_code < 200 or resp.status_code >= 300:
        return f"[mailbox] create failed ({resp.status_code}): {resp.text[:200]}"
    return f"Disposable inbox ready: {address} (password {password}). Read it with email_check_disposable."  # noqa: E501


async def _domain() -> str:
    resp = await _client.get("/domains")
    resp.raise_for_status()
    data = resp.json()
    if not data or not data.get("hydra:member"):
        raise RuntimeError("no domains from mail.tm")
    return data["hydra:member"][0]["domain"]


async def messages(address: str, password: str, limit: int = 8) -> str:
    """List messages in the disposable inbox (verification links etc.)."""
    token = await _login(address, password)
    if not token:
        return f"[mailbox] can't log into {address} — check the password."
    resp = await _client.get(
        "/messages",
        headers={"Authorization": f"Bearer {token}"},
        params={"page": 1},
    )
    if resp.status_code >= 400:
        return f"[mailbox] list failed ({resp.status_code})"
    items = resp.json().get("hydra:member", [])
    if not items:
        return f"{address}: no messages yet."
    lines = []
    for m in items[:limit]:
        lines.append(
            f"- id {m['id']} — {m.get('subject', '(no subject)')} from {m.get('from', {}).get('address', '?')}"
        )
    return "\n".join(lines) + f"\n({len(items)} total)"


async def read(address: str, password: str) -> str:
    """Read the newest message's body."""
    token = await _login(address, password)
    if not token:
        return f"[mailbox] can't log into {address} — check the password."
    resp = await _client.get(
        "/messages",
        headers={"Authorization": f"Bearer {token}"},
        params={"page": 1},
    )
    if resp.status_code >= 400:
        return f"[mailbox] list failed ({resp.status_code})"
    items = resp.json().get("hydra:member", [])
    if not items:
        return f"{address}: no messages yet."
    mid = items[0]["id"]
    msg = (await _client.get(
        f"/messages/{mid}", headers={"Authorization": f"Bearer {token}"}
    )).json()
    body = (msg.get("text") or msg.get("html") or "(no body)")[:1200]
    return (f"From: {msg.get('from', {}).get('address', '?')}\n"
            f"Subject: {msg.get('subject', '(none)')}\n\n{body}")


async def delete(address: str, password: str) -> str:
    """Delete the disposable inbox (it self-destructs anyway)."""
    token = await _login(address, password)
    if not token:
        return f"[mailbox] can't log into {address}."
    resp = await _client.delete(
        "/accounts", headers={"Authorization": f"Bearer {token}"}
    )
    if resp.status_code >= 400:
        return f"[mailbox] delete failed ({resp.status_code})"
    return f"Deleted disposable inbox {address}."


async def _login(address: str, password: str) -> str | None:
    resp = await _client.post(
        "/token", json={"address": address, "password": password}
    )
    if resp.status_code >= 300:
        return None
    return resp.json().get("token")

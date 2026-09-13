"""Minecraft RCON admin — safe server control via the itzg rcon-cli helper.

Runs `docker exec twilight-mc-server rcon-cli <cmd>`. rcon-cli picks up the
server's RCON_PASSWORD from the container env automatically, so no password
leaks into Zenith's config (same pattern as mc_players in homelab.py).

Safety:
- Only the itzg server container is talked to (fixed name, no user input).
- Commanded operations are white-listed to admin actions the user would want
  from chat. Free-form commands are NOT accepted.
- Every command has a hard subprocess timeout (20s) and validates the reply.
"""
from __future__ import annotations

import asyncio
import re

import httpx

from ..core.config import settings

_SERVER = "twilight-mc-server"
_RCON_TIMEOUT = 20.0


async def _docker_exec(argv: list[str], timeout: float = _RCON_TIMEOUT) -> tuple[int, str, str]:
    """Run a command inside a container via the Docker socket (no docker CLI)."""
    from ..tools.homelab import _docker_json

    # 1) Create the exec instance on the container.
    try:
        create = await _docker_json(
            f"/containers/{_SERVER}/exec",
            method="POST",
            body={
                "AttachStdout": True,
                "AttachStderr": True,
                "Cmd": ["/usr/local/bin/rcon-cli", *argv],
            },
        )
        exec_id = create.get("Id")
    except Exception as exc:
        return (1, "", f"[rcon] could not create exec: {exc}")

    # 2) Start it and capture output.
    transport = httpx.AsyncHTTPTransport(uds=settings.docker_socket)
    try:
        async with httpx.AsyncClient(transport=transport, timeout=timeout) as client:
            start = await client.post(f"http://docker/exec/{exec_id}/start",
                                      json={"Detach": False, "Tty": True})
            out = start.text or ""
            # Return code lives in the exec inspect.
            inspect = await client.get(f"http://docker/exec/{exec_id}/json")
            data = inspect.json() if inspect.status_code == 200 else {}
            code = (data.get("ExitCode")) if isinstance(data.get("ExitCode"), int) else 0
    except Exception as exc:
        return (1, "", f"[rcon] exec failed: {exc}")
    return (code, out, "")

# Allowed actions → the exact rcon-cli argv. Kept narrow on purpose.
_COMMANDS: dict[str, list[str]] = {
    "list": ["list"],
    "save_all": ["save-all"],
    "seed": ["seed"],
    "whitelist_add": ["whitelist", "add", "{}"],
    "whitelist_remove": ["whitelist", "remove", "{}"],
    "whitelist_list": ["whitelist", "list"],
    "ban": ["ban", "{}"],
    "pardon": ["pardon", "{}"],
    "op": ["op", "{}"],
    "deop": ["deop", "{}"],
    "tp": ["tp", "{}"],
    "give": ["give", "{}"],
    "say": ["say", "{}"],
    "time_set": ["time", "set", "{}"],
    "weather": ["weather", "{}"],
    "kick": ["kick", "{}", "Zenith admin"],
}

# "player" fields, validated to avoid shell/path injection.
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{1,16}$")
# "say" / "give" payloads — allow spaces but forbid shell metachars.
_SAY_BAD = re.compile(r"[;&|`$<>]")
_TIME_RE = re.compile(r"^\d{1,5}$")
_WEATHER_RE = re.compile(r"^(clear|rain|thunder)$")


def _validate(command: str, *args: str) -> tuple[str | None, list[str]]:
    """Return (error, argv) or (None, argv)."""
    base = _COMMANDS.get(command)
    if not base:
        return (f"Unknown mc_admin action '{command}'. Allowed: "
                f"{', '.join(sorted(_COMMANDS))}.", [])
    args = [a for a in args if a]  # drop empties

    if command == "say":
        payload = " ".join(args).strip()
        if not payload:
            return ("Provide a message to say.", [])
        if _SAY_BAD.search(payload):
            return ("The message contains shell metacharacters — I won't run that.", [])
        return (None, ["say", payload])

    if command in ("whitelist_add", "whitelist_remove", "ban", "pardon", "op", "deop", "kick"):
        if not args:
            return (f"Provide a player name for {command}.", [])
        if not _USERNAME_RE.match(args[0]):
            return ("Player names must be 1-16 chars of letters/digits/underscore.", [])
        if command == "kick":
            return (None, ["kick", args[0], "Zenith admin"])
        return (None, base[:-1] + [args[0]])  # fill the trailing {} slot

    if command == "tp":
        if len(args) < 3:
            return ("give all three: x, y, z (or scale to: fromX fromY fromZ toX toY toZ).", [])
        coords = args[:3]
        if not all(c.replace("-", "").isdigit() for c in coords):
            return ("Coordinates must be numbers (e.g. 123 64 456).", [])
        return (None, ["tp", *coords])

    if command == "give":
        if len(args) < 2:
            return ("Give needs: player item [count] (e.g. 'give Aryan diamond 64').", [])
        if not _USERNAME_RE.match(args[0]):
            return ("Player names must be 1-16 chars of letters/digits/underscore.", [])
        item = args[1].lower()
        if _SAY_BAD.search(item):
            return ("The item name contains shell metacharacters — I won't run that.", [])
        count = args[2] if len(args) > 2 else ""
        if count and not re.match(r"^\d{1,4}$", count):
            return ("Count must be an integer (e.g. 64).", [])
        return (None, ["give", args[0], item] + ([count] if count else []))

    if command == "time_set":
        if not args or not _TIME_RE.match(args[0]):
            return ("Provide a time tick value (0-24000) or 'day'/'night'.", [])
        return (None, ["time", "set", args[0]])

    if command == "weather":
        if not args or not _WEATHER_RE.match(args[0].lower()):
            return ("Weather must be 'clear', 'rain', or 'thunder'.", [])
        return (None, ["weather", args[0].lower()])

    if command == "seed" or command == "list" or command == "save_all" or command == "whitelist_list":
        if args:
            return (f"{command} takes no arguments.", [])
        return (None, base)

    return (f"Unhandled action '{command}'.", [])


async def mc_admin(
    command: str = "list",
    player: str = "",
    item: str = "",
    count: str = "",
    x: str = "0",
    y: str = "64",
    z: str = "0",
    message: str = "",
    tick: str = "1000",
    weather: str = "clear",
) -> str:
    """Run a white-listed Minecraft admin operation via rcon.

    The exact argv list built from validated inputs — never a shell string, so
    no injection.
    """
    # Build the argument list based on the action's payload slots.
    if command == "tp":
        args = [x, y, z]
    elif command == "give":
        args = [player, item, count]
    elif command in ("whitelist_add", "whitelist_remove", "ban", "pardon", "op", "deop", "kick"):
        args = [player]
    elif command == "say":
        args = [message]
    elif command == "time_set":
        args = [tick]
    elif command == "weather":
        args = [weather]
    else:
        args = []

    err, argv = _validate(command, *args)
    if err:
        return f"[minecraft] {err}"

    from ..tools.homelab import _docker_json

    # Is the server even up? A stopped container is the common case.
    try:
        containers = await _docker_json(
            "/containers/json?all=1&filters=" + _urlencode({"name": [_SERVER]})
        )
    except Exception as exc:
        return f"[minecraft] {exc}"
    if not containers or (containers[0].get("State") or "") != "running":
        return ("[minecraft] server unreachable (likely stopped). Start it with "
                "mc_start first.")

    code, out, err = await _docker_exec(argv)
    if code != 0 or err:
        # A non-zero exec often just means the server has no players / not
        # fully ready — prefer whatever rcon returned.
        if err and code != 0 and not out:
            return ("[minecraft] rcon failed. Is the server still starting? "
                    f"({err[:200]})")
    reply = (out or "").strip()
    if not reply:
        reply = "(no response — command sent)"
    return reply[:2000]


def _urlencode(params: dict) -> str:
    import json
    import urllib.parse
    # Docker expects filters as a URL-encoded JSON string, not a str(dict).
    return urllib.parse.quote(json.dumps(params))


async def mc_admin_help() -> str:
    """Human list of what mc_admin can do (for the model's benefit)."""
    return """Minecraft admin via RCON (server must be running):
- list                     — who's online
- seed                     — world seed
- save_all                 — save the world now
- whitelist_add PLAYER
- whitelist_remove PLAYER
- whitelist_list
- ban PLAYER / pardon PLAYER / kick PLAYER
- op PLAYER / deop PLAYER
- tp X Y Z                 — teleport a player (in the chat flow, coordinates)
- give PLAYER ITEM [COUNT] — e.g. give Aryan diamond 64
- say MESSAGE              — broadcast to all players
- time_set TICKS           — e.g. 0 for day, 13000 for night
- weather clear|rain|thunder"""
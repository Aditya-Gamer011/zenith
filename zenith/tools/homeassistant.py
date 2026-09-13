"""Home Assistant & Smart Home Integration for Zenith.

Enables control over Home Assistant devices:
- Panasonic Air Conditioner (AC): climate.panasonic_ac_panasonic_ac & switch.power_switch_switch_2 (ha_ac, ha_climate)
- Soundbar: switch.power_switch_switch_1 (ha_soundbar)
- Smart Fans: fan.fan_1 & fan.fan_2 (ha_fan)
- Smart Plugs & Switches: switch.power_switch_switch, switch.smart_plug_10a_socket_1 (ha_switch, ha_smart_plug)
- Generic HA Entity & Service calls (ha_entity)
- All-Device Overview Dashboard (ha_overview)
"""
from __future__ import annotations

import os
import httpx

from ..core.config import settings

_AC_CLIMATE_ID = "climate.panasonic_ac_panasonic_ac"
_AC_SWITCH_ID = "switch.power_switch_switch_2"

def _get_token() -> str:
    """Long-lived access token from .env. No hardcoded fallback — if unset the
    tools return a clear 'not configured' error (the old literal JWT leak is gone)."""
    return (getattr(settings, "home_assistant_token", "") or os.environ.get("HOME_ASSISTANT_TOKEN", "")).strip()

def _get_url() -> str:
    url = getattr(settings, "home_assistant_url", "") or os.environ.get("HOME_ASSISTANT_URL", "") or "http://172.17.0.1:8123"
    return url.rstrip("/")

def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_get_token()}",
        "Content-Type": "application/json",
    }

def _normalize_fan_id(entity_id: str | None) -> str:
    if not entity_id or not str(entity_id).strip():
        return "fan.fan_2"
    clean = str(entity_id).strip().lower()
    if clean in ("fan 1", "fan_1", "fan1", "1"):
        return "fan.fan_1"
    if clean in ("fan 2", "fan_2", "fan2", "2", "fan", "the fan", "fan.fan2", "fan 2 entity", "fan2 entity"):
        return "fan.fan_2"
    if not clean.startswith("fan."):
        return f"fan.{clean}"
    return str(entity_id).strip()

def _resolve_switch_id(device: str | None) -> tuple[str, str]:
    """Resolves device string/alias to (entity_id, friendly_label)."""
    clean = (device or "ac").strip().lower()
    if clean in ("ac", "air conditioner", "aircon", "cooler", "climate", "switch 2", "switch_2", "power_switch_switch_2"):
        return _AC_SWITCH_ID, "Air Conditioner Switch"
    elif clean in ("soundbar", "speaker", "audio", "sound bar", "switch 1", "switch_1", "power_switch_switch_1"):
        return "switch.power_switch_switch_1", "Soundbar"
    elif clean in ("power_switch", "main_switch", "main switch", "power switch", "switch"):
        return "switch.power_switch_switch", "Main Power Switch"
    elif clean in ("smart_plug", "plug", "socket", "socket 1", "socket_1", "smart_plug_10a_socket_1"):
        return "switch.smart_plug_10a_socket_1", "Smart Plug 10A Socket 1"
    elif clean.startswith("switch."):
        return clean, clean
    else:
        return f"switch.{clean}", clean


async def ha_ac(
    action: str = "status",
    temperature: float | int | str | None = None,
    mode: str | None = None,
    fan_mode: str | None = None,
) -> str:
    """Full control over Air Conditioner (power switch + Panasonic AC climate unit).

    action: 'status' | 'on' | 'off' | 'temp' | 'mode' | 'fan' | 'toggle'
    temperature: Target temperature in °C (e.g. 23.0, 16.0 - 30.0)
    mode: HVAC mode ('cool', 'heat', 'auto', 'dry', 'fan_only', 'off')
    fan_mode: AC internal fan mode ('auto', 'diffuse', 'low', 'medium', 'high')
    """
    token = _get_token()
    if not token:
        return "[ha_ac] Home Assistant token missing."

    base_url = _get_url()
    act = (action or "status").lower().strip()

    if act in ("on", "turn_on", "turn on", "power_on", "power on", "start"):
        act_type = "on"
    elif act in ("off", "turn_off", "turn off", "power_off", "power off", "stop"):
        act_type = "off"
    elif act in ("temp", "set_temp", "set_temperature", "temperature"):
        act_type = "temp"
    elif act in ("mode", "set_mode", "hvac_mode"):
        act_type = "mode"
    elif act in ("fan", "fan_mode", "set_fan_mode"):
        act_type = "fan"
    elif act in ("toggle", "switch"):
        act_type = "toggle"
    elif temperature is not None:
        act_type = "temp"
    elif mode is not None:
        act_type = "mode"
    elif fan_mode is not None:
        act_type = "fan"
    else:
        act_type = "status"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            if act_type == "on":
                # 1. Turn ON physical power switch
                await client.post(
                    f"{base_url}/api/services/homeassistant/turn_on",
                    headers=_headers(),
                    json={"entity_id": _AC_SWITCH_ID},
                )
                # 2. Turn ON climate unit (set HVAC mode, default to 'cool' if none specified)
                target_mode = (mode or "cool").lower()
                await client.post(
                    f"{base_url}/api/services/climate/set_hvac_mode",
                    headers=_headers(),
                    json={"entity_id": _AC_CLIMATE_ID, "hvac_mode": target_mode},
                )
                # 3. Optional temperature adjustment
                temp_msg = ""
                if temperature is not None:
                    try:
                        temp_val = float(temperature)
                        await client.post(
                            f"{base_url}/api/services/climate/set_temperature",
                            headers=_headers(),
                            json={"entity_id": _AC_CLIMATE_ID, "temperature": temp_val},
                        )
                        temp_msg = f" at {temp_val}°C"
                    except (ValueError, TypeError):
                        pass

                # 4. Optional fan mode adjustment
                fan_msg = ""
                if fan_mode:
                    await client.post(
                        f"{base_url}/api/services/climate/set_fan_mode",
                        headers=_headers(),
                        json={"entity_id": _AC_CLIMATE_ID, "fan_mode": str(fan_mode).lower()},
                    )
                    fan_msg = f" (Fan: {str(fan_mode).upper()})"

                return f"❄️ **Panasonic AC**: Powered ON (Switch & Climate unit set to `{target_mode.upper()}`{temp_msg}){fan_msg}."

            elif act_type == "off":
                # 1. Turn OFF climate unit
                await client.post(
                    f"{base_url}/api/services/climate/set_hvac_mode",
                    headers=_headers(),
                    json={"entity_id": _AC_CLIMATE_ID, "hvac_mode": "off"},
                )
                # 2. Turn OFF physical power switch
                await client.post(
                    f"{base_url}/api/services/homeassistant/turn_off",
                    headers=_headers(),
                    json={"entity_id": _AC_SWITCH_ID},
                )
                return "🛑 **Panasonic AC**: Powered OFF (Climate unit & Power Switch turned off)."

            elif act_type == "temp":
                if temperature is None:
                    return "[ha_ac] Please specify a target temperature (e.g., temperature=23.0)."
                try:
                    temp_val = float(temperature)
                except (ValueError, TypeError):
                    return f"[ha_ac] Invalid temperature value '{temperature}'. Must be a number."

                resp = await client.post(
                    f"{base_url}/api/services/climate/set_temperature",
                    headers=_headers(),
                    json={"entity_id": _AC_CLIMATE_ID, "temperature": temp_val},
                )
                resp.raise_for_status()
                return f"🌡️ **Panasonic AC**: Set target temperature to `{temp_val}°C`."

            elif act_type == "mode":
                if not mode:
                    return "[ha_ac] Please specify an HVAC mode ('cool', 'heat', 'auto', 'dry', 'fan_only', 'off')."
                m = str(mode).lower().strip()
                resp = await client.post(
                    f"{base_url}/api/services/climate/set_hvac_mode",
                    headers=_headers(),
                    json={"entity_id": _AC_CLIMATE_ID, "hvac_mode": m},
                )
                resp.raise_for_status()
                return f"❄️ **Panasonic AC**: Set HVAC mode to `{m.upper()}`."

            elif act_type == "fan":
                if not fan_mode:
                    return "[ha_ac] Please specify an AC fan mode ('auto', 'diffuse', 'low', 'medium', 'high')."
                fm = str(fan_mode).lower().strip()
                resp = await client.post(
                    f"{base_url}/api/services/climate/set_fan_mode",
                    headers=_headers(),
                    json={"entity_id": _AC_CLIMATE_ID, "fan_mode": fm},
                )
                resp.raise_for_status()
                return f"💨 **Panasonic AC**: Set AC fan mode to `{fm.upper()}`."

            elif act_type == "toggle":
                st_res = await client.get(f"{base_url}/api/states/{_AC_CLIMATE_ID}", headers=_headers())
                st = st_res.json().get("state", "off") if st_res.status_code == 200 else "off"
                if st == "off":
                    return await ha_ac(action="on", temperature=temperature, mode=mode, fan_mode=fan_mode)
                else:
                    return await ha_ac(action="off")

            else:  # status
                c_res = await client.get(f"{base_url}/api/states/{_AC_CLIMATE_ID}", headers=_headers())
                s_res = await client.get(f"{base_url}/api/states/{_AC_SWITCH_ID}", headers=_headers())

                sw_state = s_res.json().get("state", "unknown").upper() if s_res.status_code == 200 else "N/A"
                if c_res.status_code == 200:
                    c_data = c_res.json()
                    hvac = c_data.get("state", "unknown").upper()
                    attrs = c_data.get("attributes", {})
                    target_temp = attrs.get("temperature", "N/A")
                    curr_temp = attrs.get("current_temperature", "N/A")
                    ac_fan = attrs.get("fan_mode", "N/A").upper()
                    return (
                        f"❄️ **Panasonic AC** (`{_AC_CLIMATE_ID}`):\n"
                        f"- Power Switch = `{sw_state}`\n"
                        f"- HVAC Mode = `{hvac}`\n"
                        f"- Target Temp = `{target_temp}°C`\n"
                        f"- Room Temp = `{curr_temp}°C`\n"
                        f"- AC Fan Speed = `{ac_fan}`\n"
                        f"- Supported Modes = `cool, heat, auto, dry, fan_only, off`"
                    )
                else:
                    return f"❄️ **Air Conditioner Power Switch** (`{_AC_SWITCH_ID}`): State = `{sw_state}`"

    except Exception as exc:
        return f"[ha_ac error] {exc}"


async def ha_climate(
    action: str = "status",
    entity_id: str = _AC_CLIMATE_ID,
    temperature: float | int | str | None = None,
    hvac_mode: str | None = None,
    fan_mode: str | None = None,
) -> str:
    """Control Home Assistant climate / thermostat device (temperature, hvac_mode, fan_mode)."""
    return await ha_ac(action=action, temperature=temperature, mode=hvac_mode, fan_mode=fan_mode)


async def ha_soundbar(action: str = "status") -> str:
    """Control Soundbar (POWER SWITCH Switch 1).

    action: 'on' | 'off' | 'toggle' | 'status'
    """
    return await ha_switch(action=action, device="soundbar")


async def ha_switch(action: str = "status", device: str = "ac") -> str:
    """Control smart switches (AC, Soundbar, Main Power Switch, Smart Plug Socket 1, or custom switch entity).

    action: 'on' | 'off' | 'toggle' | 'status'
    device: 'ac' | 'soundbar' | 'power_switch' | 'plug' | entity_id
    """
    token = _get_token()
    if not token:
        return "[ha_switch] Home Assistant token missing."

    base_url = _get_url()
    act = (action or "status").lower().strip()
    target_id, label = _resolve_switch_id(device)

    if target_id == _AC_SWITCH_ID and act in ("on", "turn_on", "turn on", "power_on"):
        return await ha_ac(action="on")
    elif target_id == _AC_SWITCH_ID and act in ("off", "turn_off", "turn off", "power_off"):
        return await ha_ac(action="off")

    if act in ("on", "turn_on", "turn on", "power_on", "power on", "enable", "start", "1", "true"):
        act_type = "on"
    elif act in ("off", "turn_off", "turn off", "power_off", "power off", "disable", "stop", "0", "false"):
        act_type = "off"
    elif act in ("toggle", "switch"):
        act_type = "toggle"
    else:
        act_type = "status"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            if act_type == "status":
                resp = await client.get(f"{base_url}/api/states/{target_id}", headers=_headers())
                if resp.status_code == 404:
                    return f"[ha_switch] Switch entity '{target_id}' not found in Home Assistant."
                resp.raise_for_status()
                data = resp.json()
                state = data.get("state", "unknown")
                return f"⚡ **{label}** (`{target_id}`): State = `{state.upper()}`"

            elif act_type in ("on", "off", "toggle"):
                service = f"turn_{act_type}" if act_type in ("on", "off") else "toggle"
                resp = await client.post(
                    f"{base_url}/api/services/homeassistant/{service}",
                    headers=_headers(),
                    json={"entity_id": target_id},
                )
                if resp.status_code != 200:
                    resp = await client.post(
                        f"{base_url}/api/services/switch/{service}",
                        headers=_headers(),
                        json={"entity_id": target_id},
                    )
                resp.raise_for_status()
                icon = "❄️" if "AC" in label else ("🔊" if "Soundbar" in label else "✅")
                return f"{icon} **{label}**: Turned `{act_type.upper()}` (`{target_id}`)."

            else:
                return f"[ha_switch] Unknown action '{action}'. Valid actions: on, off, toggle, status."

    except Exception as exc:
        return f"[ha_switch error] {exc}"


async def ha_fan(action: str = "status", entity_id: str = "fan.fan_2", percentage: int | str | None = None) -> str:
    """Control smart fans (FAN 1 / fan.fan_1, FAN 2 / fan.fan_2).

    action: 'on' | 'off' | 'toggle' | 'speed' | 'status'
    entity_id: 'fan.fan_1' ('fan 1') or 'fan.fan_2' ('fan 2')
    percentage: Fan speed percentage (0 to 100)
    """
    token = _get_token()
    if not token:
        return "[ha_fan] Home Assistant token missing."

    base_url = _get_url()
    act = (action or "status").lower().strip()
    target_id = _normalize_fan_id(entity_id)

    if act in ("on", "turn_on", "turn on", "power_on", "power on", "enable", "start", "1", "true"):
        act_type = "on"
    elif act in ("off", "turn_off", "turn off", "power_off", "power off", "disable", "stop", "0", "false"):
        act_type = "off"
    elif act in ("toggle", "switch"):
        act_type = "toggle"
    elif act in ("speed", "set_percentage", "set_speed"):
        act_type = "speed"
    elif percentage is not None:
        act_type = "speed"
    else:
        act_type = "status"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            if act_type == "status":
                resp = await client.get(f"{base_url}/api/states/{target_id}", headers=_headers())
                if resp.status_code == 404:
                    return f"[ha_fan] Fan entity '{target_id}' not found in Home Assistant."
                resp.raise_for_status()
                data = resp.json()
                state = data.get("state", "unknown")
                attrs = data.get("attributes", {})
                name = attrs.get("friendly_name", target_id)
                pct = attrs.get("percentage", "N/A")
                return f"🌀 **{name}** (`{target_id}`): State = `{state.upper()}` | Speed = `{pct}%`"

            elif act_type == "on":
                payload: dict = {"entity_id": target_id}
                if percentage is not None:
                    try:
                        payload["percentage"] = int(percentage)
                    except (ValueError, TypeError):
                        pass
                    endpoint = f"{base_url}/api/services/fan/set_percentage"
                else:
                    endpoint = f"{base_url}/api/services/homeassistant/turn_on"

                resp = await client.post(endpoint, headers=_headers(), json=payload)
                if resp.status_code != 200:
                    resp = await client.post(f"{base_url}/api/services/fan/turn_on", headers=_headers(), json={"entity_id": target_id})
                resp.raise_for_status()
                speed_str = f" at {percentage}% speed" if percentage is not None else ""
                return f"✅ Turned ON `{target_id}`{speed_str}."

            elif act_type == "off":
                resp = await client.post(
                    f"{base_url}/api/services/homeassistant/turn_off",
                    headers=_headers(),
                    json={"entity_id": target_id},
                )
                if resp.status_code != 200:
                    resp = await client.post(
                        f"{base_url}/api/services/fan/turn_off",
                        headers=_headers(),
                        json={"entity_id": target_id},
                    )
                resp.raise_for_status()
                return f"🛑 Turned OFF `{target_id}`."

            elif act_type == "toggle":
                resp = await client.post(
                    f"{base_url}/api/services/homeassistant/toggle",
                    headers=_headers(),
                    json={"entity_id": target_id},
                )
                if resp.status_code != 200:
                    resp = await client.post(
                        f"{base_url}/api/services/fan/toggle",
                        headers=_headers(),
                        json={"entity_id": target_id},
                    )
                resp.raise_for_status()
                return f"🔄 Toggled `{target_id}`."

            elif act_type == "speed":
                if percentage is None:
                    return "[ha_fan] Please specify a percentage (0-100) for fan speed."
                try:
                    pct_val = int(percentage)
                except (ValueError, TypeError):
                    return f"[ha_fan] Invalid percentage value '{percentage}'. Must be an integer 0-100."

                resp = await client.post(
                    f"{base_url}/api/services/fan/set_percentage",
                    headers=_headers(),
                    json={"entity_id": target_id, "percentage": pct_val},
                )
                resp.raise_for_status()
                return f"⚡ Set speed of `{target_id}` to {pct_val}%."

            else:
                return f"[ha_fan] Unknown action '{action}'. Valid actions: on, off, toggle, speed, status."

    except Exception as exc:
        return f"[ha_fan error] {exc}"


async def ha_smart_plug(action: str = "status") -> str:
    """Control and read telemetry from Smart Plug 10A (socket state, power, voltage, current, energy).

    action: 'status' | 'on' | 'off' | 'toggle' | 'energy'
    """
    token = _get_token()
    if not token:
        return "[ha_smart_plug] Home Assistant token missing."

    base_url = _get_url()
    act = (action or "status").lower().strip()
    target_id = "switch.smart_plug_10a_socket_1"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            if act in ("on", "off", "toggle"):
                service = f"turn_{act}" if act in ("on", "off") else "toggle"
                resp = await client.post(
                    f"{base_url}/api/services/homeassistant/{service}",
                    headers=_headers(),
                    json={"entity_id": target_id},
                )
                resp.raise_for_status()

            socket_res = await client.get(f"{base_url}/api/states/{target_id}", headers=_headers())
            volt_res = await client.get(f"{base_url}/api/states/sensor.smart_plug_10a_voltage", headers=_headers())
            pow_res = await client.get(f"{base_url}/api/states/sensor.smart_plug_10a_power", headers=_headers())
            curr_res = await client.get(f"{base_url}/api/states/sensor.smart_plug_10a_current", headers=_headers())
            eng_res = await client.get(f"{base_url}/api/states/sensor.smart_plug_10a_total_energy", headers=_headers())

            socket_st = socket_res.json().get("state", "unknown").upper() if socket_res.status_code == 200 else "N/A"
            volt = volt_res.json().get("state", "0") if volt_res.status_code == 200 else "0"
            power = pow_res.json().get("state", "0") if pow_res.status_code == 200 else "0"
            curr = curr_res.json().get("state", "0") if curr_res.status_code == 200 else "0"
            energy = eng_res.json().get("state", "0") if eng_res.status_code == 200 else "0"

            return f"🔌 **Smart Plug 10A**: Socket = `{socket_st}` | Voltage = `{volt}V` | Power = `{power}W` | Current = `{curr}A` | Total Energy = `{energy} kWh`"

    except Exception as exc:
        return f"[ha_smart_plug error] {exc}"


async def ha_overview() -> str:
    """Get live status overview of all smart home devices in Home Assistant."""
    token = _get_token()
    if not token:
        return "[ha_overview] Home Assistant token missing."

    base_url = _get_url()
    devices = [
        (_AC_CLIMATE_ID, "❄️ Panasonic AC (Climate)"),
        (_AC_SWITCH_ID, "⚡ AC Power Switch"),
        ("switch.power_switch_switch_1", "🔊 Soundbar"),
        ("fan.fan_1", "🌀 FAN 1"),
        ("fan.fan_2", "🌀 FAN 2"),
        ("switch.power_switch_switch", "⚡ Main Power Switch"),
        ("switch.smart_plug_10a_socket_1", "🔌 Smart Plug 10A Socket 1"),
    ]

    lines = ["### 🏠 Home Assistant Device Overview", ""]
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            for eid, name in devices:
                resp = await client.get(f"{base_url}/api/states/{eid}", headers=_headers())
                if resp.status_code == 200:
                    data = resp.json()
                    st = data.get("state", "unknown").upper()
                    attrs = data.get("attributes", {})
                    extra = []
                    if "temperature" in attrs and attrs["temperature"] is not None:
                        extra.append(f"Target: {attrs['temperature']}°C")
                    if "current_temperature" in attrs and attrs["current_temperature"] is not None:
                        extra.append(f"Room: {attrs['current_temperature']}°C")
                    if "fan_mode" in attrs and attrs["fan_mode"] is not None:
                        extra.append(f"AC Fan: {attrs['fan_mode'].upper()}")
                    if "percentage" in attrs and attrs["percentage"] is not None:
                        extra.append(f"Speed: {attrs['percentage']}%")

                    extra_str = f" ({', '.join(extra)})" if extra else ""
                    lines.append(f"- **{name}** (`{eid}`): `{st}`{extra_str}")
                else:
                    lines.append(f"- **{name}** (`{eid}`): `OFFLINE/NOT FOUND`")

            volt_res = await client.get(f"{base_url}/api/states/sensor.smart_plug_10a_voltage", headers=_headers())
            pow_res = await client.get(f"{base_url}/api/states/sensor.smart_plug_10a_power", headers=_headers())
            v_val = volt_res.json().get("state", "N/A") if volt_res.status_code == 200 else "N/A"
            p_val = pow_res.json().get("state", "N/A") if pow_res.status_code == 200 else "N/A"
            lines.append("")
            lines.append(f"⚡ **Smart Plug Telemetry**: `{v_val} V` | `{p_val} W`")

        return "\n".join(lines)
    except Exception as exc:
        return f"[ha_overview error] {exc}"


async def ha_entity(action: str = "status", domain: str = "homeassistant", service: str = "toggle", entity_id: str = "fan.fan_2") -> str:
    """Get state or call service on any Home Assistant entity."""
    token = _get_token()
    if not token:
        return "[ha_entity] Home Assistant token missing."

    base_url = _get_url()
    act = (action or "status").lower().strip()
    target_id = entity_id or "fan.fan_2"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            if act in ("status", "get", "info", "state"):
                resp = await client.get(f"{base_url}/api/states/{target_id}", headers=_headers())
                if resp.status_code == 404:
                    return f"[ha_entity] Entity '{target_id}' not found."
                resp.raise_for_status()
                data = resp.json()
                state = data.get("state", "unknown")
                attrs = data.get("attributes", {})
                name = attrs.get("friendly_name", target_id)
                return f"🏠 **{name}** (`{target_id}`): State = `{state}`"

            elif act in ("call", "service", "toggle", "on", "off"):
                if act in ("on", "off", "toggle"):
                    domain = "homeassistant"
                    service = f"turn_{act}" if act in ("on", "off") else "toggle"
                resp = await client.post(
                    f"{base_url}/api/services/{domain}/{service}",
                    headers=_headers(),
                    json={"entity_id": target_id},
                )
                resp.raise_for_status()
                return f"✅ Service `{domain}.{service}` executed for `{target_id}`."

            else:
                return f"[ha_entity] Unknown action '{action}'. Valid actions: status, call, on, off, toggle."

    except Exception as exc:
        return f"[ha_entity error] {exc}"

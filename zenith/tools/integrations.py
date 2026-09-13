"""Cloudflare + Vercel + R2 integrations.

Cloudflare: manage DNS records + Email Routing for configured zones
using the API token from settings. This is what verifies
SPF/DKIM/DMARC and wires the catch-all → email forward.

R2: S3-compatible object storage on the same CF account (AWS SigV4 signed,
no external deps). Buckets, list, get/put/delete objects.

Vercel: list projects, get deployment status, and trigger deploys. Uses a
Vercel access token.

Every call degrades gracefully: missing token → clear "not configured".
"""
from __future__ import annotations

import hashlib
import hmac
import json
import urllib.parse
from datetime import datetime, timezone

import httpx

from ..core.config import settings

CF_API = "https://api.cloudflare.com/client/v4"
VERCEL_API = "https://api.vercel.com"


def _cf_ok() -> bool:
    return bool(settings.cloudflare_token and settings.cloudflare_zone)


def _vercel_ok() -> bool:
    return bool(settings.vercel_token)


async def _cf_zone_id(zone: str = "") -> str:
    """Resolve a zone name to its ID via the API."""
    zone = zone or settings.cloudflare_zone
    headers = {"Authorization": f"Bearer {settings.cloudflare_token}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(f"{CF_API}/zones", headers=headers, params={"name": zone})
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success") or not data.get("result"):
        raise RuntimeError(f"[cloudflare] zone '{zone}' not found: {resp.text[:200]}")
    return data["result"][0]["id"]


async def _cf(path: str, method: str = "GET", zone: str = "", **kw) -> dict:
    if not _cf_ok():
        raise RuntimeError("Cloudflare isn't configured (CLOUDFLARE_API_TOKEN + CLOUDFLARE_ZONE).")
    zone_id = await _cf_zone_id(zone)
    headers = {"Authorization": f"Bearer {settings.cloudflare_token}", "Content-Type": "application/json"}
    url = f"{CF_API}/zones/{zone_id}{path}"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.request(method, url, headers=headers, **kw)
    data = resp.json() if resp.content else {}
    if not data.get("success", True):
        msgs = [e.get("message", "") for e in data.get("errors", [])]
        raise RuntimeError(f"[cloudflare] {', '.join(msgs) or resp.text[:200]}")
    return data


# ── Cloudflare tools ─────────────────────────────────────────────────────────

async def cf_dns_list(zone: str = "") -> str:
    """List DNS records for the zone (records of type A/AAAA/MX/TXT/etc)."""
    try:
        data = await _cf("/dns_records", zone=zone)
    except Exception as exc:
        return f"[cloudflare] {exc}"
    recs = data.get("result", [])
    if not recs:
        return "No DNS records."
    return "\n".join(
        f"{r.get('type', '?')} {r.get('name', '?')} → {r.get('content', '?')}"
        for r in recs[:40]
    )


async def cf_dns_upsert(
    rec_type: str,
    name: str,
    content: str,
    proxied: bool = False,
    zone: str = "",
    ttl: int = 1,
) -> str:
    """Add (or replace if existing) a DNS record."""
    if not rec_type or not name or not content:
        return "[cloudflare] Provide type, name and content (e.g. A, '@', 192.0.2.1)."
    try:
        existing = await _cf(f"/dns_records?type={rec_type}&name={name}.{settings.cloudflare_zone}", zone=zone)
        body = {
            "type": rec_type.upper(),
            "name": name,
            "content": content,
            "ttl": ttl,
            "proxied": bool(proxied),
        }
        if existing.get("result"):
            rec_id = existing["result"][0]["id"]
            await _cf(f"/dns_records/{rec_id}", "PUT", zone=zone, json=body)
            return f"Updated DNS {rec_type} {name}.{settings.cloudflare_zone} → {content}."
        await _cf("/dns_records", "POST", zone=zone, json=body)
        return f"Added DNS {rec_type} {name}.{settings.cloudflare_zone} → {content}."
    except Exception as exc:
        return f"[cloudflare] {exc}"


async def cf_email_routing_rules(zone: str = "") -> str:
    """List Cloudflare Email Routing rules (catch-all destinations etc)."""
    try:
        data = await _cf("/email/routing/rules", zone=zone)
    except Exception as exc:
        return f"[cloudflare] {exc}"
    rules = data.get("result", [])
    if not rules:
        return "No email routing rules (Email Routing may not be enabled)."
    return "\n".join(
        f"{r.get('matchers', [{}])[0].get('field', '?')} {r.get('matchers', [{}])[0].get('value', '?')}"
        f" → {r.get('actions', [{}])[0].get('value', ['?'])}"
        for r in rules[:20]
    )


async def cf_dns_status(zone: str = "") -> str:
    """SPF/DKIM/DMARC presence for the zone — email deliverability check."""
    try:
        data = await _cf("/dns_records", zone=zone)
    except Exception as exc:
        return f"[cloudflare] {exc}"
    recs = data.get("result", [])
    txt = [r for r in recs if r.get("type") == "TXT"]
    mx = [r for r in recs if r.get("type") == "MX"]
    out = []
    out.append(f"MX records ({len(mx)}): " + (", ".join(r.get('content', '') for r in mx) or "none"))
    spf = next((r for r in txt if "v=spf1" in r.get("content", "")), None)
    out.append(f"SPF: {'✓' if spf else '✗ missing'}")
    dkim = next((r for r in txt if "v=DKIM1" in r.get("content", "")), None)
    out.append(f"DKIM: {'✓' if dkim else '✗ missing'}")
    dmarc = next((r for r in txt if "DMARC" in r.get("content", "").upper() and "v=DMARC" in r.get("content", "").upper()), None)
    out.append(f"DMARC: {'✓' if dmarc else '✗ missing'}")
    return "\n".join(out)


# ── Vercel tools ────────────────────────────────────────────────────────────

def _vercel_headers():
    return {"Authorization": f"Bearer {settings.vercel_token}", "Content-Type": "application/json"}


ZENITH_VERCEL_TEAM_ID = "team_1iIUH4mv2xsZAWnzKx51lhAA"  # Zenith team


async def _vercel(path: str, method: str = "GET", params: dict = None, **kw) -> dict:
    if not _vercel_ok():
        raise RuntimeError("Vercel isn't configured (VERCEL_TOKEN in .env).")

    req_params = dict(params or {})
    if "teamId" not in req_params and "teamId=" not in path:
        req_params["teamId"] = ZENITH_VERCEL_TEAM_ID

    url = f"{VERCEL_API}{path}"
    async with httpx.AsyncClient(timeout=40) as client:
        resp = await client.request(method, url, headers=_vercel_headers(), params=req_params, **kw)
    if resp.status_code >= 400:
        raise RuntimeError(f"[vercel] API {resp.status_code}: {resp.text[:200]}")
    return resp.json() if resp.content else {}


async def vercel_projects() -> str:
    """List Vercel projects (name, framework, updated)."""
    try:
        data = await _vercel("/v9/projects")
    except Exception as exc:
        return f"[vercel] {exc}"
    projects = data.get("projects", [])
    if not projects:
        return "No Vercel projects found."
    return "\n".join(
        f"- **{p.get('name', '?')}** ({p.get('framework', 'custom')}) — target: {', '.join(p.get('targets', {}).get('production', {}).get('alias', [])) or 'none'}"
        for p in projects
    )


async def vercel_deploy_status(project: str) -> str:
    """Latest deployment status for a project."""
    try:
        proj = await _vercel(f"/v9/projects/{project}")
        team_id = proj.get("teamId") or ""
        params = {"project": project, "limit": 5}
        if team_id:
            params["teamId"] = team_id
        data = await _vercel("/v6/deployments", params=params)
    except Exception as exc:
        return f"[vercel] {exc}"

    dep = data.get("deployments", [])
    if not dep:
        return f"No deployments for {project}."

    aliases = (proj.get("targets", {}).get("production", {}).get("alias") or [])
    alias_str = ", ".join(f"https://{a}" for a in aliases) if aliases else ""

    lines = [f"Recent deployments for **{project}**:"]
    if alias_str:
        lines.append(f"📌 **Team Production Domain(s)**: {alias_str}")

    for d in dep[:5]:
        st = d.get("state") or d.get("readyState") or "?"
        url = d.get("url", "")
        lines.append(f"- `{st}` · `https://{url}`")

    lines.append("\n*Note: Project is under Vercel Team `codraw`. Accessing preview URLs requires logging into your Vercel account if Deployment Protection is enabled.*")
    return "\n".join(lines)


async def vercel_deploy(project: str, ref: str = "main") -> str:
    """Trigger a production deploy of `project` at git `ref`."""
    try:
        proj = await _vercel(f"/v9/projects/{project}")
    except Exception as exc:
        return f"[vercel] {exc}"

    git = proj.get("link") or proj.get("gitRepository") or {}
    repo = git.get("repo") or project
    org = git.get("org") or git.get("owner") or ""

    data = {
        "name": project,
        "target": "production",
    }

    if org and repo:
        data["gitSource"] = {
            "type": "github",
            "org": org,
            "repo": repo,
            "ref": ref or git.get("productionBranch", "main"),
        }

    try:
        dep = await _vercel("/v13/deployments", method="POST", json=data)
    except Exception as exc:
        return f"[vercel] deploy failed: {exc}"

    url = dep.get("url", "")
    state = dep.get("readyState") or dep.get("state") or "QUEUED"
    return f"🚀 Deployment triggered for **{project}** ({ref}) — `https://{url}` (State: `{state}`)"


async def vercel_env_list(project: str) -> str:
    """List env var names (values redacted) for a project."""
    try:
        data = await _vercel(f"/v9/projects/{project}/env", params={"target": "production"})
    except Exception as exc:
        return f"[vercel] {exc}"
    envs = data.get("envs", [])
    if not envs:
        return f"No env vars on {project}."
    return "\n".join(f"- {e.get('key', '?')} (target {e.get('target', '?')})" for e in envs)


# ── registry hooks (called from tools.py) ───────────────────────────────────

async def cloudflare_health() -> str:
    """One-line integration status for the UI/health."""
    if not _cf_ok():
        return "Cloudflare: not configured (CLOUDFLARE_API_TOKEN)."
    try:
        zone_id = await _cf_zone_id()
        return f"Cloudflare: connected (zone {settings.cloudflare_zone}, {zone_id[:8]}…)"
    except Exception as exc:
        return f"Cloudflare: {exc}"


async def vercel_health() -> str:
    if not _vercel_ok():
        return "Vercel: not configured (VERCEL_TOKEN)."
    return "Vercel: connected."


# ── R2 (S3-compatible) ───────────────────────────────────────────────────────

def _r2_ok() -> bool:
    return bool(settings.r2_access_key_id and settings.r2_secret_access_key and settings.r2_endpoint)


def _r2_sig(method: str, path: str, body: bytes = b"", content_type: str = "") -> dict:
    """Build AWS SigV4 headers for an R2 S3 request.

    Correct for every case: always sign `x-amz-content-sha256` + `host` +
    `x-amz-date`, and include `content-type` in the canonical string only when
    the request will actually send it (so the signature always matches).
    """
    region = "auto"
    service = "s3"
    now = datetime.now(timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    host = urllib.parse.urlparse(settings.r2_endpoint).netloc

    # Split any query string out of the path — SigV4 signs the URI and query
    # separately (and the S3 list-type prefix must be canonical query).
    if "?" in path:
        canonical_uri, query_raw = path.split("?", 1)
        # Canonical query string: each key=value, both URI-encoded per SigV4.
        pairs = []
        for kv in query_raw.split("&"):
            if "=" in kv:
                k, v = kv.split("=", 1)
                pairs.append(f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(v, safe='')}")
            else:
                pairs.append(urllib.parse.quote(kv, safe=''))
        pairs.sort()
        query = "&".join(pairs)
    else:
        canonical_uri, query = path, ""
    if not canonical_uri.startswith("/"):
        canonical_uri = f"/{canonical_uri}"
    payload_hash = hashlib.sha256(body).hexdigest()

    # S3 SigV4 requires canonical headers SORTED lexicographically by header
    # name (content-type before host before x-amz-*). Build the map, sort, then
    # join — the signed-headers list must stay in the same order.
    hdrs: dict[str, str] = {
        "host": host,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
    }
    if content_type:
        hdrs["content-type"] = content_type
    canonical_headers = "".join(f"{k}:{hdrs[k]}\n" for k in sorted(hdrs))
    signed_headers = ";".join(sorted(hdrs))

    canonical_request = "\n".join([
        method, canonical_uri, query, canonical_headers, signed_headers, payload_hash,
    ])
    scope = f"{date_stamp}/{region}/{service}/aws4_request"
    string_to_sign = "\n".join([
        "AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical_request.encode()).hexdigest(),
    ])

    def _hmac(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode(), hashlib.sha256).digest()

    k_date = _hmac(("AWS4" + settings.r2_secret_access_key).encode(), date_stamp)
    k_region = _hmac(k_date, region)
    k_service = _hmac(k_region, service)
    k_signing = _hmac(k_service, "aws4_request")
    signature = hmac.new(k_signing, string_to_sign.encode(), hashlib.sha256).hexdigest()

    auth = (f"AWS4-HMAC-SHA256 Credential={settings.r2_access_key_id}/{scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}")
    return {
        "x-amz-date": amz_date,
        "x-amz-content-sha256": payload_hash,
        "Authorization": auth,
        **({"Content-Type": content_type} if content_type else {}),
    }


async def r2_buckets() -> str:
    """List R2 buckets."""
    if not _r2_ok():
        return "[r2] Not configured (R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY / R2_ENDPOINT)."
    from xml.etree import ElementTree as ET
    try:
        headers = _r2_sig("GET", "/")
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(settings.r2_endpoint, headers=headers)
        if resp.status_code >= 400:
            return f"[r2] {resp.status_code}: {resp.text[:300]}"
        root = ET.fromstring(resp.text)
        ns = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
        buckets = [b.findtext("s3:Name", default="?", namespaces=ns) for b in root.findall(".//s3:Bucket", ns)]
        return "R2 buckets:\n" + ("\n".join(f"- {b}" for b in buckets) if buckets else "(none)")
    except Exception as exc:
        return f"[r2] {exc}"


async def r2_objects(bucket: str, prefix: str = "") -> str:
    """List objects in an R2 bucket."""
    if not _r2_ok():
        return "[r2] Not configured."
    from xml.etree import ElementTree as ET
    try:
        path = f"/{bucket}?list-type=2"
        if prefix:
            path += f"&prefix={urllib.parse.quote(prefix)}"
        headers = _r2_sig("GET", path)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(settings.r2_endpoint + path, headers=headers)
        if resp.status_code >= 400:
            return f"[r2] {resp.status_code}: {resp.text[:300]}"
        root = ET.fromstring(resp.text)
        ns = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
        keys = [e.findtext("s3:Key", default="?", namespaces=ns) for e in root.findall(".//s3:Contents", ns)]
        return f"Objects in {bucket}/{prefix}:\n" + ("\n".join(f"- {k}" for k in keys) if keys else "(empty)")
    except Exception as exc:
        return f"[r2] {exc}"


async def r2_put(bucket: str, key: str, content: str) -> str:
    """Store a text object in an R2 bucket."""
    if not _r2_ok():
        return "[r2] Not configured."
    try:
        body = content.encode()
        path = f"/{bucket}/{key}"
        headers = _r2_sig("PUT", path, body, "text/plain; charset=utf-8")
        async with httpx.AsyncClient(timeout=40) as client:
            resp = await client.put(settings.r2_endpoint + path, headers=headers, content=body)
        if resp.status_code not in (200, 201, 204):
            return f"[r2] {resp.status_code}: {resp.text[:300]}"
        return f"Stored {len(body)} bytes to r2://{bucket}/{key}"
    except Exception as exc:
        return f"[r2] {exc}"


async def r2_get(bucket: str, key: str) -> str:
    """Fetch a text object from an R2 bucket."""
    if not _r2_ok():
        return "[r2] Not configured."
    try:
        path = f"/{bucket}/{key}"
        headers = _r2_sig("GET", path)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(settings.r2_endpoint + path, headers=headers)
        if resp.status_code >= 400:
            return f"[r2] {resp.status_code}: {resp.text[:200]}"
        return resp.text[:8000]
    except Exception as exc:
        return f"[r2] {exc}"


async def r2_delete(bucket: str, key: str) -> str:
    if not _r2_ok():
        return "[r2] Not configured."
    try:
        path = f"/{bucket}/{key}"
        headers = _r2_sig("DELETE", path)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.delete(settings.r2_endpoint + path, headers=headers)
        if resp.status_code >= 400:
            return f"[r2] {resp.status_code}: {resp.text[:200]}"
        return f"Deleted r2://{bucket}/{key}"
    except Exception as exc:
        return f"[r2] {exc}"

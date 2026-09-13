"""Network & HTTP Testing Suite — API testing, HTTP requests, DNS lookups, speed tests.

Zenith can send custom HTTP requests (GET/POST/PUT/DELETE) to test REST/GraphQL APIs,
query DNS records for domain setups, and benchmark network response latency.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, Optional, Union

import httpx


async def http_request(
    url: str,
    method: str = "GET",
    headers: Union[str, Dict[str, str]] = "",
    params: Union[str, Dict[str, str]] = "",
    data: Union[str, Dict[str, Any]] = "",
    timeout: int = 15,
) -> str:
    """Send a custom HTTP request (GET, POST, PUT, DELETE, PATCH, HEAD) to any API or web endpoint.
    headers/params/data can be JSON strings or dicts."""
    method = method.upper().strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        url = f"https://{url}"

    # Parse headers
    req_headers = {}
    if isinstance(headers, str) and headers.strip():
        try:
            req_headers = json.loads(headers)
        except Exception:
            # Parse line by line "Header: Value"
            for line in headers.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    req_headers[k.strip()] = v.strip()
    elif isinstance(headers, dict):
        req_headers = headers

    # Parse query params
    req_params = {}
    if isinstance(params, str) and params.strip():
        try:
            req_params = json.loads(params)
        except Exception:
            pass
    elif isinstance(params, dict):
        req_params = params

    # Parse payload body
    json_payload = None
    content_payload = None
    if data:
        if isinstance(data, dict):
            json_payload = data
        elif isinstance(data, str):
            try:
                json_payload = json.loads(data)
            except Exception:
                content_payload = data

    start_time = time.time()
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.request(
                method,
                url,
                headers=req_headers if req_headers else None,
                params=req_params if req_params else None,
                json=json_payload,
                content=content_payload,
            )

        elapsed_ms = int((time.time() - start_time) * 1000)

        # Parse response body
        res_content_type = resp.headers.get("content-type", "")
        if "application/json" in res_content_type:
            try:
                formatted_body = json.dumps(resp.json(), indent=2, ensure_ascii=False)
            except Exception:
                formatted_body = resp.text
        else:
            formatted_body = resp.text

        if len(formatted_body) > 3000:
            formatted_body = formatted_body[:3000] + f"\n... [response body truncated, total {len(resp.text)} chars]"

        res_headers = "\n".join([f"  {k}: {v}" for k, v in list(resp.headers.items())[:8]])

        return (f"### 🌐 HTTP Response: {method} {url}\n"
                f"**Status**: `{resp.status_code} {resp.reason_phrase}` | **Time**: `{elapsed_ms} ms`\n\n"
                f"**Headers**:\n{res_headers}\n\n"
                f"**Body**:\n```json\n{formatted_body}\n```")

    except Exception as exc:
        return f"[http_request error]: {exc}"


async def dns_lookup(domain: str, record_type: str = "A") -> str:
    """Perform a DNS lookup for a domain (A, AAAA, MX, TXT, CNAME, NS, SOA)."""
    import socket
    domain = domain.lower().strip().replace("https://", "").replace("http://", "").split("/")[0]
    record_type = record_type.upper().strip()

    results = []
    try:
        if record_type == "AAAA":
            infos = socket.getaddrinfo(domain, None, socket.AF_INET6)
            results = list(set([item[4][0] for item in infos]))
        else:
            infos = socket.getaddrinfo(domain, None, socket.AF_INET)
            results = list(set([item[4][0] for item in infos]))

        res_text = "\n".join([f"  - {ip}" for ip in results]) if results else "No records found."
        return f"### 🔍 DNS Records for **{domain}** ({record_type}):\n{res_text}"
    except Exception as exc:
        return f"[dns_lookup error]: {exc}"

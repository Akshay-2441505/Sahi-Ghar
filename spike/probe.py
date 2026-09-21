"""THROWAWAY spike tooling for docs/spikes/. Not imported by backend/.

Usage (from the repo root):
    SPIKE_CONTACT=<address-or-url> uv run --with httpx python spike/probe.py URL [URL ...]

Politeness: one request at a time, DELAY_SECONDS apart, identifiable User-Agent.
It only fetches and records. It never solves, works around or skips a CAPTCHA.
"""
import hashlib
import os
import re
import sys
import time
from pathlib import Path

import httpx

try:  # use the OS trust store (like a browser); some sites omit an intermediate certificate
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

DELAY_SECONDS = 3
SAMPLES = Path(__file__).parent / "samples"
CAPTCHA_HINTS = re.compile(r"captcha|g-recaptcha|hcaptcha|turnstile", re.I)


def mentions_captcha(html: str) -> bool:
    """A hint, not a verdict: a script bundle can mention 'captcha' without the page needing one."""
    return bool(CAPTCHA_HINTS.search(html))


def probe(client: httpx.Client, url: str) -> dict:
    response = client.get(url)
    SAMPLES.mkdir(exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", url.lower()).strip("-")[:80]
    saved = SAMPLES / f"{slug}-{hashlib.sha256(response.content).hexdigest()[:8]}.html"
    saved.write_bytes(response.content)
    return {
        "url": url,
        "final_url": str(response.url),
        "status": response.status_code,
        "content_type": response.headers.get("content-type", ""),
        "bytes": len(response.content),
        "mentions_captcha": mentions_captcha(response.text),
        "forms": len(re.findall(r"<form", response.text, re.I)),
        "saved": str(saved),
    }


def main(urls: list[str]) -> None:
    headers = {"User-Agent": f"SahiGharSpike/0.1 (research; {os.environ['SPIKE_CONTACT']})"}
    with httpx.Client(headers=headers, timeout=30, follow_redirects=True) as client:
        for i, url in enumerate(urls):
            if i:
                time.sleep(DELAY_SECONDS)
            try:
                print(probe(client, url), flush=True)
            except httpx.HTTPError as exc:
                print({"url": url, "error": f"{type(exc).__name__}: {exc}"}, flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])

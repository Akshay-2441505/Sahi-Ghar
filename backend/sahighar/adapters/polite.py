"""A deliberately polite HTTP fetcher. The rules are fixed here, not left to callers:

- one request at a time, at least `delay` seconds apart;
- an honest User-Agent that names the project and a contact;
- ANY refusal (401/403/429), any CAPTCHA, or a redirect to another host raises BlockedError. Callers stop.
  Nothing here retries, waits out, or works around a block or a CAPTCHA;
- an optional request budget, so a run can be bounded (BudgetExhausted is a normal stop, not an error).
"""
import re
import time
from dataclasses import dataclass

import httpx


class BlockedError(Exception):
    """The site refused or challenged the request. Stop and do not retry; do not work around it."""


class BudgetExhausted(Exception):
    """This run's request budget is used up. Normal stop: run again to continue."""


class FetchError(Exception):
    """A request failed for a non-blocking reason (server error, not found, network) after retries."""


@dataclass
class Fetched:
    url: str
    data: bytes
    content_type: str


_CAPTCHA = re.compile(r"captcha", re.I)


class PoliteFetcher:
    def __init__(self, contact: str, delay: float = 3.0, max_requests: int | None = None, retries: int = 2,
                 client: httpx.Client | None = None, sleep=time.sleep, clock=time.monotonic):
        self.headers = {"User-Agent": f"SahiGharBot/0.1 (research project, reads public RERA pages politely; contact: {contact})"}
        self.delay, self.max_requests, self.retries = delay, max_requests, retries
        self.client = client or self._default_client()
        self._sleep, self._clock = sleep, clock
        self._last: float | None = None
        self.requests = 0

    @staticmethod
    def _default_client() -> httpx.Client:
        try:  # use the operating system's certificate store, like a browser (some sites omit an intermediate certificate)
            import truststore
            truststore.inject_into_ssl()
        except ImportError:
            pass
        return httpx.Client(timeout=60, follow_redirects=True)

    def _wait(self) -> None:
        if self._last is not None:
            remaining = self.delay - (self._clock() - self._last)
            if remaining > 0:
                self._sleep(remaining)
        self._last = self._clock()

    def get(self, url: str) -> Fetched:
        problem = ""
        for attempt in range(self.retries + 1):
            if self.max_requests is not None and self.requests >= self.max_requests:
                raise BudgetExhausted(f"request budget of {self.max_requests} reached")
            if attempt:
                self._sleep(self.delay * 2 ** attempt)  # back off before retrying a server error
                self._last = self._clock()
            else:
                self._wait()
            self.requests += 1
            try:
                response = self.client.get(url, headers=self.headers)
            except httpx.TransportError as exc:
                problem = f"{type(exc).__name__}: {exc}"
                continue
            if response.status_code in (401, 403, 429):
                raise BlockedError(f"{url} answered HTTP {response.status_code}")
            if response.url.host != httpx.URL(url).host:
                raise BlockedError(f"{url} redirected to another host ({response.url.host})")
            if response.status_code >= 500:
                problem = f"HTTP {response.status_code}"
                continue
            if response.status_code != 200:
                raise FetchError(f"{url} answered HTTP {response.status_code}")
            content_type = response.headers.get("content-type", "")
            if "html" in content_type and _CAPTCHA.search(response.text):
                raise BlockedError(f"{url} shows a CAPTCHA")
            return Fetched(url, response.content, content_type)
        raise FetchError(f"{url} failed after {self.retries + 1} attempts ({problem})")

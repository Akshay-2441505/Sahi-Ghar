import httpx
import pytest

from sahighar.adapters.polite import BlockedError, BudgetExhausted, FetchError, PoliteFetcher


class Clock:
    def __init__(self):
        self.t, self.sleeps = 100.0, []

    def now(self):
        return self.t

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.t += seconds


def fetcher(handler, clock=None, **kwargs):
    clock = clock or Clock()
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return PoliteFetcher("me@example.test", client=client, sleep=clock.sleep, clock=clock.now, **kwargs), clock


def ok(request):
    return httpx.Response(200, text="<html>fine</html>", headers={"content-type": "text/html"})


def test_requests_are_spaced_and_carry_an_honest_user_agent():
    seen = []

    def handler(request):
        seen.append(request.headers["user-agent"])
        return ok(request)

    f, clock = fetcher(handler, delay=3.0)
    f.get("https://site.test/a")
    f.get("https://site.test/b")
    assert clock.sleeps == [3.0]  # nothing before the first request, a full delay before the second
    assert all("SahiGharBot" in ua and "me@example.test" in ua for ua in seen)
    assert f.requests == 2


def test_the_delay_counts_time_already_spent():
    f, clock = fetcher(ok, delay=3.0)
    f.get("https://site.test/a")
    clock.t += 2.0
    f.get("https://site.test/b")
    assert clock.sleeps == [1.0]


@pytest.mark.parametrize("status", [401, 403, 429])
def test_a_refusal_stops_everything_and_is_never_retried(status):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(status)

    f, _ = fetcher(handler)
    with pytest.raises(BlockedError):
        f.get("https://site.test/a")
    assert len(calls) == 1


def test_a_captcha_page_stops_everything():
    f, _ = fetcher(lambda r: httpx.Response(200, text="<div>Enter the CAPTCHA</div>", headers={"content-type": "text/html"}))
    with pytest.raises(BlockedError, match="CAPTCHA"):
        f.get("https://site.test/a")


def test_a_redirect_to_another_host_is_treated_as_a_block():
    def handler(request):
        if request.url.host == "site.test":
            return httpx.Response(302, headers={"location": "https://login.other.test/"})
        return ok(request)

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    clock = Clock()
    f = PoliteFetcher("me@example.test", client=client, sleep=clock.sleep, clock=clock.now)
    with pytest.raises(BlockedError, match="another host"):
        f.get("https://site.test/a")


def test_server_errors_are_retried_with_backoff_then_succeed():
    answers = iter([500, 200])
    f, clock = fetcher(lambda r: httpx.Response(next(answers), text="x", headers={"content-type": "text/html"}), delay=3.0)
    assert f.get("https://site.test/a").data == b"x"
    assert f.requests == 2 and clock.sleeps == [6.0]


def test_persistent_server_errors_give_up_with_a_fetch_error():
    f, _ = fetcher(lambda r: httpx.Response(503), retries=2)
    with pytest.raises(FetchError):
        f.get("https://site.test/a")
    assert f.requests == 3


def test_not_found_is_a_fetch_error_not_a_block():
    f, _ = fetcher(lambda r: httpx.Response(404))
    with pytest.raises(FetchError, match="404"):
        f.get("https://site.test/a")


def test_the_request_budget_is_a_normal_stop():
    f, _ = fetcher(ok, max_requests=2)
    f.get("https://site.test/a")
    f.get("https://site.test/b")
    with pytest.raises(BudgetExhausted):
        f.get("https://site.test/c")
    assert f.requests == 2

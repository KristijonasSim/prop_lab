"""The loop waits out a model limit instead of burning fresh scripts on it."""
from factory import tvloop


MSG = "model call failed: model exited 1: You've hit your session limit"


def test_limit_stops_fetching(monkeypatch):
    fetched = []
    monkeypatch.setattr(tvloop.tradingview, "retry",
                        lambda **kw: ([], [("tv_a", MSG)]))
    monkeypatch.setattr(tvloop.tvfetch, "fetch", lambda n: fetched.append(n) or [])
    out = tvloop.intake(20)
    assert out["limited"] and not fetched


def test_no_backlog_fetches_new(monkeypatch):
    monkeypatch.setattr(tvloop.tradingview, "retry", lambda **kw: ([], []))
    monkeypatch.setattr(tvloop.tvfetch, "fetch", lambda n: [])
    out = tvloop.intake(20)
    assert "limited" not in out and out["fetched"] == 0


def test_own_refusal_not_retried_again(monkeypatch):
    tvloop._retried.clear()
    monkeypatch.setattr(tvloop.tradingview, "retry",
                        lambda **kw: ([], [("tv_b", "invalid translation: x")]))
    tvloop.intake(20)
    assert "tv_b" in tvloop._retried

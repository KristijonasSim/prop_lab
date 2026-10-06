from factory import gapsort


def test_never_buckets():
    assert gapsort.bucket("grammar gap: request.security() on another symbol")[0] == "never"
    assert gapsort.bucket("grammar gap: No entry condition exists. DCA")[0] == "never"
    assert gapsort.bucket("grammar gap: close crosses down through any of 62 fixed price levels")[0] == "never"


def test_offset_gap_is_retry_but_stateful_fvg_is_not():
    assert gapsort.bucket("grammar gap: high[2] and low[2] - only lagged terms")[0] == "retry"
    assert gapsort.bucket("grammar gap: `var float bullTop` set when low > high[2]")[0] == "state"


def test_or_rule_is_case_sensitive():
    # "or" inside ordinary prose must not file a script under OR-logic.
    assert gapsort.bucket("grammar gap: round-number lattice, floor or modulo")[0] == "levels"


def test_retry_never_reasks_never(tmp_path, monkeypatch):
    import json
    from factory import queue
    from factory.sources import tradingview as tv
    (tmp_path / "skipped.jsonl").write_text(json.dumps(
        {"script": "x", "why": "grammar gap: xgb model", "gap": True}) + "\n")
    monkeypatch.setattr(queue, "DIR", tmp_path)
    called = []
    monkeypatch.setattr(tv, "_read_one", lambda *a: called.append(a))
    assert tv.retry(gaps=True, buckets=("never",)) == ([], [])
    assert not called

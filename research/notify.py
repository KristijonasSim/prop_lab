"""Ping Kris when the loop finds something. Email, and nothing clever.

WHY. Kris, 2026-09-18: *"when he finds something he needs to ping me, for
example sending me an email"*. A loop running unattended on a VM that nobody
reads is the same as no loop.

WHAT IT SENDS, AND WHAT IT REFUSES TO SEND. Only a survivor of the full screen,
and the mail says in its own body what that does and does not mean. A survivor
has earned a walk-forward; it is not a result and it is not a strategy. An alert
that reads like good news would be worse than no alert, because it would be
believed - and the loop's first survivor was one marginal pass in a search that
should have thrown up nine by luck.

IT ALSO REFUSES TO SPAM. One mail per candidate, ever; `SEEN` on disk is the
record. A loop that re-alerts on the same row every cycle gets filtered to junk
within a day and then the one that mattered is never seen.

SET UP - two minutes, and the password never touches this repo.

    1. Google account -> Security -> 2-Step Verification -> App passwords
    2. Make one called "prop_lab", copy the 16 characters
    3. mkdir -p ~/.config/prop_lab && cat > ~/.config/prop_lab/notify.env <<'EOF'
       SMTP_USER=you@gmail.com
       SMTP_PASS=the16characters
       SMTP_TO=you@gmail.com
       EOF
       chmod 600 ~/.config/prop_lab/notify.env

Unconfigured, `send()` returns False and says why. The loop treats that as
normal and keeps going - a missing password must never stop the research.
"""
from __future__ import annotations

import json
import os
import smtplib
import ssl
import sys
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CONF = Path.home() / ".config" / "prop_lab" / "notify.env"
SEEN = ROOT / "backtests" / "alerted.json"
HOST, PORT = "smtp.gmail.com", 465


def config() -> dict[str, str]:
    """Read the env file, then let real environment variables win."""
    out: dict[str, str] = {}
    if CONF.exists():
        for line in CONF.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    for k in ("SMTP_USER", "SMTP_PASS", "SMTP_TO", "SMTP_HOST", "SMTP_PORT"):
        if os.environ.get(k):
            out[k] = os.environ[k]
    return out


def configured() -> bool:
    c = config()
    return bool(c.get("SMTP_USER") and c.get("SMTP_PASS"))


def _seen() -> set[str]:
    if not SEEN.exists():
        return set()
    try:
        return set(json.loads(SEEN.read_text()))
    except ValueError:
        return set()


def _mark(key: str) -> None:
    s = _seen()
    s.add(key)
    SEEN.parent.mkdir(parents=True, exist_ok=True)
    SEEN.write_text(json.dumps(sorted(s), indent=0))


def push(subject: str, body: str) -> tuple[bool, str]:
    """ntfy.sh — sends TO Kris's inbox without holding any key to it.

    Kris, 2026-09-18: *"i dont want you to have access to my email, what i want
    is send notification to ksimsonas@gmail.com"*. That rules out the SMTP path
    below, which needs a Google app password and would give this box send rights
    on his account.

    ntfy relays instead. The VM posts a message to a public topic and ntfy's own
    server emails it onward — **no credentials, no inbox access, nothing to
    revoke.** The one line it needs:

        NTFY_EMAIL=ksimsonas@gmail.com
        NTFY_TOPIC=proplab-<long random string>

    **The topic string IS the only secret**, and it is weak by design: anyone
    who knows it can read the alerts and post to them. So make it long and
    random, and keep anything sensitive out of the message. Nothing here is —
    a feed name, a market, a few basis points. The detail lives on the board.

    Free ntfy caps forwarded emails per day, which is the right shape for this:
    alerts are rare and one per candidate.
    """
    c = config()
    topic = c.get("NTFY_TOPIC")
    email = c.get("NTFY_EMAIL")
    if not topic:
        return False, "no NTFY_TOPIC"
    import urllib.request
    url = c.get("NTFY_URL", "https://ntfy.sh").rstrip("/") + "/" + topic
    base = {"Title": subject[:200], "Priority": "default", "Tags": "microscope"}
    token = c.get("NTFY_TOKEN")
    if token:
        base["Authorization"] = f"Bearer {token}"
    data = body.encode()[:3800]

    def _post(h: dict) -> None:
        urllib.request.urlopen(
            urllib.request.Request(url, data=data, headers=h), timeout=30).read()

    # Email forwarding needs a (free) ntfy account token: anonymous email
    # sending was turned off - "code 40053, anonymous email sending is not
    # allowed", measured 2026-09-18. The push itself still works with no
    # account at all, so a rejected email must NOT swallow the alert: retry
    # without the header and say what happened.
    if email:
        try:
            _post({**base, "Email": email})
            return True, f"pushed + emailed {email}"
        except Exception as exc:                         # noqa: BLE001
            reason = f"email relay refused ({type(exc).__name__})"
    else:
        reason = ""

    try:
        _post(base)
        return True, f"pushed{'; ' + reason if reason else ''}"
    except Exception as exc:                             # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def send(subject: str, body: str) -> tuple[bool, str]:
    """Email if SMTP is set up, phone push if ntfy is, both if both are.

    Succeeds if EITHER lands, because the point is that Kris finds out.
    """
    ok_any, why = False, []
    p_ok, p_why = push(subject, body)
    if p_ok:
        ok_any = True
    elif p_why != "no NTFY_TOPIC":
        why.append(f"ntfy: {p_why}")

    e_ok, e_why = _send_email(subject, body)
    if e_ok:
        ok_any = True
    elif "no SMTP" not in e_why:
        why.append(f"smtp: {e_why}")

    if ok_any:
        return True, "sent"
    return False, "; ".join(why) or (
        f"nothing configured — add NTFY_TOPIC or SMTP_* to {CONF}")


def _send_email(subject: str, body: str) -> tuple[bool, str]:
    c = config()
    if not configured():
        return False, f"no SMTP credentials ({CONF} missing or incomplete)"
    msg = EmailMessage()
    msg["From"] = c["SMTP_USER"]
    msg["To"] = c.get("SMTP_TO", c["SMTP_USER"])
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(c.get("SMTP_HOST", HOST),
                              int(c.get("SMTP_PORT", PORT)),
                              context=ctx, timeout=45) as s:
            s.login(c["SMTP_USER"], c["SMTP_PASS"])
            s.send_message(msg)
        return True, "sent"
    except Exception as exc:                             # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def alert_survivor(result, total_screened: int, survivors: int) -> tuple[bool, str]:
    """One mail per candidate, with the honest reading attached.

    `total_screened` and `survivors` are the WHOLE loop's counts, not this
    cycle's, because a pass is only readable against how much was searched.
    """
    c = result.candidate
    if c.key in _seen():
        return False, "already alerted"

    s = result.screen
    chance = total_screened * 0.05
    verdict = ("FEWER than chance would give — most likely noise"
               if survivors <= chance else
               "more than chance would give — still only earns a real test")

    body = f"""The research loop found something that survived all five checks.

    {c.name}
    market      {c.market}
    watches     {c.feed}
    measure     {c.transform}{c.window or ''}, lag {c.lag}
    hold        {c.hold}
    direction   {'+' if c.direction > 0 else '-'}{abs(c.direction)}

    effect      {s.effect:+.1f} bps between top and bottom bucket
    median      {s.median_effect:+.1f} bps   (must agree in sign - it does)
    cost bar    {s.cost_bar:.2f} bps
    monotone    rho {s.rho:.2f}
    vs shuffle  p = {s.p_null if s.p_null is not None else float('nan'):.3f}
    events      {s.events}

WHY IT SHOULD EXIST
{c.mechanism}

WHAT THIS IS NOT
A survivor has earned a walk-forward with honest fills. It is not a result, not
a strategy, and not something to trade. The screen is the cheap filter.

READ IT AGAINST THE SEARCH
{total_screened:,} candidates screened so far, {survivors} survived.
At a 5% threshold chance alone gives {chance:.1f}.
-> {verdict}

Its pre-registration was written BEFORE the test ran:
{result.prereg_path}

Board: backtests/research.html
"""
    ok, why = send(f"[prop_lab] survivor: {c.name}", body)
    if ok:
        _mark(c.key)
    return ok, why


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="test the alert path")
    ap.add_argument("--test", action="store_true", help="send a test mail")
    a = ap.parse_args(argv)

    if not configured():
        print(f"NOT CONFIGURED — {CONF}")
        print(__doc__.split("SET UP")[1].split("Unconfigured")[0].rstrip())
        return 1
    c = config()
    print(f"configured: {c['SMTP_USER']} -> {c.get('SMTP_TO', c['SMTP_USER'])}")
    if a.test:
        ok, why = send("[prop_lab] test",
                       "If you are reading this, the loop can reach you.\n")
        print("sent" if ok else f"FAILED: {why}")
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

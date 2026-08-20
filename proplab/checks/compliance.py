"""Template-compliance and core-integrity checks."""
from __future__ import annotations

import hashlib
from pathlib import Path

from ..strategy.base import Strategy
from .lookahead import CheckResult

CORE_DIR = Path(__file__).resolve().parents[1] / "core"


def template_compliance(cls: type[Strategy]) -> CheckResult:
    problems = []
    if not issubclass(cls, Strategy):
        problems.append("does not subclass Strategy")
    if cls.name in ("unnamed", "", None):
        problems.append("missing `name`")
    if not (cls.mechanism or "").strip() and not cls.name.startswith("_"):
        problems.append("missing `mechanism` - the WHY is mandatory")
    if not (cls.hypothesis or "").strip() and not cls.name.startswith("_"):
        problems.append("missing `hypothesis` - must tie back to the idea given")
    if not isinstance(cls.params, dict) or not cls.params:
        problems.append("no declared `params` - tunables must be named and logged")
    for banned in ("run", "compute", "check"):
        if banned in cls.__dict__:
            problems.append(f"defines `{banned}` - engine/metrics logic belongs in core/")
    return CheckResult("template_compliance", not problems,
                       "conforms to template" if not problems else "; ".join(problems),
                       [{"problem": p} for p in problems])


def core_fingerprint() -> str:
    """Hash of the owner-fixed core, recorded with every run.

    If this changes between runs, results are not comparable - the rules of
    the game moved.
    """
    h = hashlib.sha256()
    for f in sorted(CORE_DIR.glob("*.py")):
        h.update(f.name.encode())
        h.update(f.read_bytes())
    return h.hexdigest()[:16]


def strategy_fingerprint(source: str) -> str:
    return hashlib.sha256(source.encode()).hexdigest()[:16]

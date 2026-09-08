"""Does a manifest actually name everything its result depends on?

The hole item 1 left open. `core/fingerprint.py` hashes the files a manifest
declares, so a kernel left OUT of the manifest never trips the stale flag - the
card stays green while the result rots. That is the same failure as before, one
level up, and nothing was checking it.

This walks the import graph statically, from the stage that writes the board
record, and reports every repo-local module reachable from it that the manifest
does not declare. Static (`ast`) rather than importing: importing a stage runs
its module-level code, and two stages were found rewriting `board.json` on
import while item 1 was being built.

Run: .venv/bin/python core/manifest_audit.py
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Reachable, but cannot change a number on the card. Declaring these would make
# every manifest noisy without buying anything - but the list is deliberately
# SHORT and each entry has to justify itself, because "it probably does not
# matter" is how look-aheads survive.
IGNORE = {
    "core/data.py",          # ccxt download path; load() is a plain parquet read
    "core/fx_data.py",       # same, for Dukascopy
    "core/nautilus_setup.py",  # second-engine harness, not the kernel
    "core/scorecard.py",     # runs at render time, cannot go stale (see fingerprint.py)
    "core/fingerprint.py",
    "core/manifest_audit.py",
}

# A manifest declares provenance; it does not compute anything. Hashing it would
# make every record stale the moment its own declaration was edited.
def _is_manifest(rel_path: str) -> bool:
    return rel_path.endswith("/manifest.py")


def _module_file(name: str) -> Path | None:
    """Resolve a dotted repo-local module name to a file, or None if it is not
    ours. `strategies.vwap.engine` -> strategies/vwap/engine.py"""
    if not name:
        return None
    parts = name.split(".")
    if parts[0] not in ("core", "strategies", "live"):
        return None
    p = ROOT.joinpath(*parts)
    if p.with_suffix(".py").is_file():
        return p.with_suffix(".py")
    if (p / "__init__.py").is_file():
        return p / "__init__.py"
    return None


def imports_of(path: Path) -> set[str]:
    """Dotted names this file imports, repo-local ones only."""
    try:
        tree = ast.parse(path.read_text(), filename=str(path))
    except (OSError, SyntaxError):
        return set()
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:                      # relative import
                continue
            mod = node.module or ""
            out.add(mod)
            # `from core import board` - the module is the submodule, not `core`
            for a in node.names:
                out.add(f"{mod}.{a.name}")
    return out


def reachable(root: Path) -> set[Path]:
    """Every repo-local .py reachable from `root`, transitively."""
    seen: set[Path] = set()
    stack = [root]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        for name in imports_of(cur):
            f = _module_file(name)
            if f and f not in seen:
                stack.append(f)
    return seen


def rel(p: Path) -> str:
    return p.resolve().relative_to(ROOT).as_posix()


def audit(sid: str) -> dict:
    """Compare one strategy's declared files against its real import graph."""
    mod = __import__(f"strategies.{sid}.manifest", fromlist=["MANIFEST"])
    man = mod.MANIFEST
    declared = {rel(Path(p)) for p in list(man["kernels"]) + list(man.get("scoring", []))}

    # ROOTS, not just the writer. The vwap board stage reads a cached trades
    # parquet and never imports the kernel that produced it - walking only the
    # writer would declare `engine.py` an unused extra and miss the whole
    # simulation. Every stage that produced a fingerprinted input is a root.
    roots = getattr(mod, "ROOTS", None) or (
        [getattr(mod, "WRITER")] if getattr(mod, "WRITER", None) else None)
    if not roots:
        return {"sid": sid, "error":
                f"strategies/{sid}/manifest.py declares no ROOTS - list the "
                f"stages that produce backtests/{sid}/board.json and every "
                f"cached input it reads"}

    graph: set[str] = set()
    for r in roots:
        graph |= {rel(p) for p in reachable(Path(r))}
    # __init__.py files are packaging, not arithmetic
    graph = {g for g in graph if not g.endswith("/__init__.py")
             and not _is_manifest(g)}
    missing = sorted(graph - declared - IGNORE)
    extra = sorted(declared - graph)
    return {"sid": sid, "roots": [rel(Path(r)) for r in roots],
            "declared": len(declared), "reachable": len(graph),
            "missing": missing, "extra": extra}


def main() -> int:
    sids = sorted(p.parent.name for p in (ROOT / "backtests").glob("*/board.json"))
    bad = 0
    for sid in sids:
        try:
            r = audit(sid)
        except Exception as exc:                             # noqa: BLE001
            print(f"{sid}: cannot audit - {type(exc).__name__}: {exc}")
            bad += 1
            continue
        if r.get("error"):
            print(f"{sid}: {r['error']}")
            bad += 1
            continue
        print(f"\n{sid}  roots={', '.join(r['roots'])}")
        print(f"  declared={r['declared']}  reachable={r['reachable']}")
        if r["missing"]:
            bad += 1
            print("  MISSING from the manifest - a change to these would NOT "
                  "flag the card stale:")
            for m in r["missing"]:
                print(f"    {m}")
        else:
            print("  complete: every reachable module is declared or ignored")
        if r["extra"]:
            # Not a failure. A manifest may name a file the writer does not
            # import - the walk-forward stage that produced a cached parquet,
            # for instance - and that is a correct thing to declare.
            print(f"  declared but not reachable from any root "
                  f"(harmless - it is hashed either way): {', '.join(r['extra'])}")
    print()
    print("manifests incomplete" if bad else "all manifests complete")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())

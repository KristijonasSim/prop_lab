"""A small linter for the Pine mistakes that keep reaching the editor.

Pine cannot be compiled locally, which is exactly why guessing at it by eye has
been costing round trips. These are the rules that have actually bitten:

  1. A function defined inside an `if` block.        -> "Syntax error at '=>'"
  2. A statement continued onto the next line,       -> "end of line without
     particularly a ternary broken before its ':'.      line continuation"
  3. Unbalanced brackets on a line, which is the
     same failure seen from the other side.

Rule 2 is stricter than Pine truly requires - Pine allows continuation when the
next line is indented further - but multi-line ternaries are where it breaks
down, and one-statement-per-line costs nothing.

    python crosscheck/pine_lint.py crosscheck/*.pine
"""
from __future__ import annotations

import sys
from pathlib import Path

DANGLING = ("?", ":", "+", "-", "*", "/", "and", "or", ",", "=", "==", "!=",
            ">", "<", ">=", "<=", "%")


def lint(path: Path) -> list[str]:
    problems = []
    lines = path.read_text().split("\n")
    for i, raw in enumerate(lines, 1):
        code = raw.split("//")[0].rstrip() if not raw.lstrip().startswith("//") else ""
        if not code.strip():
            continue
        indent = len(code) - len(code.lstrip())
        stripped = code.strip()

        if "=>" in stripped and indent > 0:
            problems.append(f"{path}:{i}: function defined at indent {indent}; "
                            f"Pine requires global scope -> {stripped[:60]}")

        for op in sorted(DANGLING, key=len, reverse=True):
            if stripped.endswith(op) and not stripped.endswith("=>"):
                problems.append(f"{path}:{i}: line ends with '{op}', continuing the "
                                f"statement onto the next line -> {stripped[:60]}")
                break

        for open_c, close_c in (("(", ")"), ("[", "]")):
            if stripped.count(open_c) != stripped.count(close_c):
                problems.append(f"{path}:{i}: unbalanced '{open_c}{close_c}' on one "
                                f"line -> {stripped[:60]}")
                break
    return problems


def main(argv: list[str]) -> int:
    files = [Path(a) for a in argv[1:]] or sorted(Path("crosscheck").glob("*.pine"))
    all_problems = []
    for f in files:
        all_problems += lint(f)
    if all_problems:
        print("\n".join(all_problems))
        print(f"\n{len(all_problems)} problem(s)")
        return 1
    print(f"{len(files)} file(s) clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

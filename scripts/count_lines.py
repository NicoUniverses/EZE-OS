"""Count lines of code in EZE OS, by module."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
total = 0
rows = []
for path in sorted(ROOT.rglob("*.py")):
    if any(part.startswith(".") or part in ("build", "dist") for part in path.relative_to(ROOT).parts):
        continue
    n = sum(1 for _ in path.open(encoding="utf-8"))
    rows.append((n, path.relative_to(ROOT)))
    total += n
for n, p in sorted(rows, reverse=True):
    print(f"{n:7d}  {p}")
print(f"{total:7d}  TOTAL")

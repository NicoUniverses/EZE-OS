"""Write stats.json: the live numbers that ezeos.org reads (version, lines, tests, downloads)."""
import json
import pathlib
import re
import subprocess
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def count_lines() -> int:
    total = 0
    for path in [*ROOT.rglob("*.py"), *ROOT.rglob("*.php")]:
        if any(p.startswith(".") or p in ("build", "dist", "third_party", "vendor") for p in path.relative_to(ROOT).parts):
            continue
        total += sum(1 for _ in path.open(encoding="utf-8"))
    return total


def count_tests() -> int:
    out = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q"], cwd=ROOT,
                         capture_output=True, text=True).stdout
    m = re.search(r"(\d+) tests? collected", out)
    return int(m.group(1)) if m else 0


version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
base = f"https://github.com/NicoUniverses/EZE-OS/releases/download/v{version}/"
stats = {
    "version": version,
    "lines": count_lines(),
    "tests": count_tests(),
    "wheel": base + f"ezeos-{version}-py3-none-any.whl",
    "sdist": base + f"ezeos-{version}.tar.gz",
    "release": f"https://github.com/NicoUniverses/EZE-OS/releases/tag/v{version}",
}
(ROOT / "stats.json").write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
print(json.dumps(stats))

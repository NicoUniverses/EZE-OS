"""Print the CHANGELOG section for one version, plus the standard disclaimer."""
import pathlib
import sys

version = sys.argv[1]
text = pathlib.Path(__file__).resolve().parent.parent.joinpath("CHANGELOG.md").read_text(encoding="utf-8")
out, keep = [], False
for line in text.splitlines():
    if line.startswith("## "):
        keep = line.startswith(f"## [{version}]")
        continue
    if keep:
        out.append(line)
print("\n".join(out).strip() or f"EZE OS {version}.")
print("\n**Experimental.** Provided AS IS, without warranty or liability (GPL-2.0-only, sections 11-12).")
print("Author: Nicolás E. Veiga Palacios · Maintained by EZE Capital (Switzerland)")

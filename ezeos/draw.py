"""ASCII circuit drawing."""
from __future__ import annotations

from typing import List

from .circuit import Circuit

_LABEL = {
    "measure": "M", "reset": "|0>", "sdg": "S+", "tdg": "T+", "sxdg": "SX+",
}


def _label(name: str, params) -> str:
    base = _LABEL.get(name, name.upper())
    if params:
        base += "(" + ",".join(f"{p:.2f}" for p in params) + ")"
    return base


def text_drawing(circuit: Circuit) -> str:
    """Return a column-per-layer ASCII drawing of ``circuit``."""
    n = circuit.num_qubits
    rows: List[List[str]] = [[] for _ in range(2 * n - 1)]
    for layer in circuit.layers():
        cells = ["-"] * n
        links = [" "] * max(0, n - 1)
        for ins in layer:
            qs = ins.qubits
            if len(qs) == 1:
                cells[qs[0]] = _label(ins.name, ins.params)
                continue
            lo, hi = min(qs), max(qs)
            for q in range(lo, hi + 1):
                cells[q] = "|"
            for k in range(lo, hi):
                links[k] = "|"
            if ins.name in ("cx", "ccx"):
                for c in qs[:-1]:
                    cells[c] = "@"
                cells[qs[-1]] = "X"
            elif ins.name == "cz":
                cells[qs[0]] = cells[qs[1]] = "@"
            elif ins.name in ("swap", "cswap"):
                if ins.name == "cswap":
                    cells[qs[0]] = "@"
                cells[qs[-2]] = cells[qs[-1]] = "x"
            else:
                lab = _label(ins.name, ins.params)
                cells[qs[0]] = lab + "_0"
                for k, q in enumerate(qs[1:], 1):
                    cells[q] = lab + f"_{k}"
        width = max(len(c) for c in cells) + 2
        for q in range(n):
            rows[2 * q].append(cells[q].center(width, "-"))
            if q < n - 1:
                rows[2 * q + 1].append(links[q].center(width))
    out = []
    for q in range(n):
        out.append(f"q{q}: " + "".join(rows[2 * q]))
        if q < n - 1:
            out.append(" " * (len(f"q{q}: ")) + "".join(rows[2 * q + 1]))
    return "\n".join(out)

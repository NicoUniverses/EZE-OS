"""OpenQASM 2.0 / 3.0 export and an OpenQASM 2.0 parser.

OpenQASM is the lingua franca accepted by IBM Quantum, Amazon Braket, IQM,
Quantinuum (via pytket) and most control stacks, so it is the main bridge
between EZE OS and real hardware.
"""
from __future__ import annotations

import math
import re
from typing import Dict, List, Tuple

from .circuit import Circuit

_QASM2_NAMES = {
    "id": "id", "x": "x", "y": "y", "z": "z", "h": "h", "s": "s", "sdg": "sdg",
    "t": "t", "tdg": "tdg", "sx": "sx", "sxdg": "sxdg", "rx": "rx", "ry": "ry",
    "rz": "rz", "p": "u1", "u": "u3", "cx": "cx", "cy": "cy", "cz": "cz", "ch": "ch",
    "cp": "cu1", "crz": "crz", "swap": "swap", "rxx": "rxx", "rzz": "rzz",
    "ccx": "ccx", "cswap": "cswap",
}

_QASM3_NAMES = dict(_QASM2_NAMES, p="p", u="U", cp="cp", sxdg="sxdg")


def _fmt(x: float) -> str:
    for k, label in ((1, "pi"), (2, "pi/2"), (4, "pi/4"), (8, "pi/8")):
        if abs(x - math.pi / k) < 1e-12:
            return label
        if abs(x + math.pi / k) < 1e-12:
            return "-" + label
    return repr(round(x, 15))


def to_qasm2(circuit: Circuit) -> str:
    lines = ["OPENQASM 2.0;", 'include "qelib1.inc";',
             f"qreg q[{circuit.num_qubits}];", f"creg c[{circuit.num_clbits}];"]
    for ins in circuit:
        qs = ",".join(f"q[{q}]" for q in ins.qubits)
        if ins.name == "measure":
            lines.append(f"measure q[{ins.qubits[0]}] -> c[{ins.clbits[0]}];")
        elif ins.name == "barrier":
            lines.append(f"barrier {qs};")
        elif ins.name == "reset":
            lines.append(f"reset {qs};")
        else:
            if ins.name not in _QASM2_NAMES:
                raise ValueError(f"gate {ins.name} has no OpenQASM 2 equivalent; transpile first")
            name = _QASM2_NAMES[ins.name]
            par = f"({','.join(_fmt(p) for p in ins.params)})" if ins.params else ""
            lines.append(f"{name}{par} {qs};")
    return "\n".join(lines) + "\n"


def to_qasm3(circuit: Circuit) -> str:
    lines = ["OPENQASM 3.0;", 'include "stdgates.inc";',
             f"qubit[{circuit.num_qubits}] q;", f"bit[{circuit.num_clbits}] c;"]
    for ins in circuit:
        qs = ", ".join(f"q[{q}]" for q in ins.qubits)
        if ins.name == "measure":
            lines.append(f"c[{ins.clbits[0]}] = measure q[{ins.qubits[0]}];")
        elif ins.name == "barrier":
            lines.append(f"barrier {qs};")
        elif ins.name == "reset":
            lines.append(f"reset {qs};")
        else:
            name = _QASM3_NAMES.get(ins.name, ins.name)
            par = f"({', '.join(_fmt(p) for p in ins.params)})" if ins.params else ""
            lines.append(f"{name}{par} {qs};")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# parser (OpenQASM 2.0 subset: one qreg, one creg, standard gates)
# --------------------------------------------------------------------------

_REVERSE = {v: k for k, v in _QASM2_NAMES.items()}
_REVERSE.update({"u1": "p", "u3": "u", "u": "u", "p": "p", "cu1": "cp", "cp": "cp", "CX": "cx", "U": "u"})

def _eval_angle(expr: str) -> float:
    """Safely evaluate an angle expression such as ``-pi/4`` or ``3*pi/2``."""
    tokens = re.findall(r"\d+\.?\d*(?:[eE][-+]?\d+)?|\.\d+|pi|[-+*/()]", expr.replace(" ", ""))
    pos = 0

    def peek():
        return tokens[pos] if pos < len(tokens) else None

    def take():
        nonlocal pos
        tok = tokens[pos]
        pos += 1
        return tok

    def atom():
        tok = take()
        if tok == "(":
            v = add()
            take()
            return v
        if tok == "-":
            return -atom()
        if tok == "+":
            return atom()
        if tok == "pi":
            return math.pi
        return float(tok)

    def mul():
        v = atom()
        while peek() in ("*", "/"):
            op = take()
            r = atom()
            v = v * r if op == "*" else v / r
        return v

    def add():
        v = mul()
        while peek() in ("+", "-"):
            op = take()
            r = mul()
            v = v + r if op == "+" else v - r
        return v

    value = add()
    if pos != len(tokens):
        raise ValueError(f"cannot parse angle '{expr}'")
    return value


def from_qasm2(text: str, name: str = "qasm") -> Circuit:
    text = re.sub(r"//[^\n]*", "", text)
    stmts = [s.strip() for s in text.split(";") if s.strip()]
    qregs: Dict[str, Tuple[int, int]] = {}
    cregs: Dict[str, Tuple[int, int]] = {}
    nq = nc = 0
    body: List[str] = []
    for s in stmts:
        if s.startswith("OPENQASM") or s.startswith("include"):
            continue
        m = re.match(r"qreg\s+(\w+)\[(\d+)\]", s)
        if m:
            qregs[m.group(1)] = (nq, int(m.group(2)))
            nq += int(m.group(2))
            continue
        m = re.match(r"creg\s+(\w+)\[(\d+)\]", s)
        if m:
            cregs[m.group(1)] = (nc, int(m.group(2)))
            nc += int(m.group(2))
            continue
        body.append(s)
    if nq == 0:
        raise ValueError("no qreg declared")
    circ = Circuit(nq, max(nc, 1), name=name)

    def qidx(ref: str) -> List[int]:
        ref = ref.strip()
        m = re.match(r"(\w+)\[(\d+)\]", ref)
        if m:
            off, size = qregs[m.group(1)]
            return [off + int(m.group(2))]
        off, size = qregs[ref]
        return list(range(off, off + size))

    def cidx(ref: str) -> List[int]:
        ref = ref.strip()
        m = re.match(r"(\w+)\[(\d+)\]", ref)
        if m:
            off, _ = cregs[m.group(1)]
            return [off + int(m.group(2))]
        off, size = cregs[ref]
        return list(range(off, off + size))

    for s in body:
        m = re.match(r"measure\s+(.+?)\s*->\s*(.+)", s)
        if m:
            for q, c in zip(qidx(m.group(1)), cidx(m.group(2))):
                circ.measure(q, c)
            continue
        m = re.match(r"(barrier|reset)\s+(.+)", s)
        if m:
            qs = [q for ref in m.group(2).split(",") for q in qidx(ref)]
            if m.group(1) == "barrier":
                circ.barrier(*qs)
            else:
                for q in qs:
                    circ.reset(q)
            continue
        m = re.match(r"(\w+)\s*(?:\((.*?)\))?\s+(.+)", s)
        if not m:
            raise ValueError(f"cannot parse statement '{s}'")
        gname = _REVERSE.get(m.group(1), m.group(1).lower())
        params = [_eval_angle(p) for p in m.group(2).split(",")] if m.group(2) else []
        if gname == "u2":
            gname, params = "u", [math.pi / 2] + params
        operands = [qidx(r) for r in m.group(3).split(",")]
        width = max(len(o) for o in operands)
        for k in range(width):
            qs = [o[k] if len(o) > 1 else o[0] for o in operands]
            circ.append(gname, qs, params)
    return circ

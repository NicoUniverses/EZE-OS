"""Quantum circuit intermediate representation (IR) for EZE OS.

A :class:`Circuit` is an ordered list of :class:`Instruction` objects. The IR
is hardware-neutral: the transpiler (``ezeos.transpile``) lowers it to the
native gate set and connectivity of a concrete device from ``ezeos.devices``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

from . import gates as G


@dataclass
class Instruction:
    """One operation in a circuit.

    ``name`` is a gate name from :mod:`ezeos.gates`, or one of the special
    operations ``measure``, ``barrier`` and ``reset``.
    """

    name: str
    qubits: Tuple[int, ...]
    params: Tuple[float, ...] = ()
    clbits: Tuple[int, ...] = ()

    def __post_init__(self) -> None:
        self.name = self.name.lower()
        self.qubits = tuple(int(q) for q in self.qubits)
        self.params = tuple(float(p) for p in self.params)
        self.clbits = tuple(int(c) for c in self.clbits)
        if self.name in ("measure", "barrier", "reset"):
            return
        spec = G.get(self.name)
        if len(self.qubits) != spec.num_qubits:
            raise ValueError(f"{self.name} acts on {spec.num_qubits} qubit(s), got {self.qubits}")
        if len(set(self.qubits)) != len(self.qubits):
            raise ValueError(f"{self.name} has repeated qubits {self.qubits}")
        if len(self.params) != spec.num_params:
            raise ValueError(f"{self.name} expects {spec.num_params} parameter(s)")

    @property
    def is_gate(self) -> bool:
        return self.name not in ("measure", "barrier", "reset")

    def unitary(self) -> G.Matrix:
        return G.get(self.name).unitary(self.params)

    def __repr__(self) -> str:
        p = f"({', '.join(f'{x:.4g}' for x in self.params)})" if self.params else ""
        c = f" -> c{list(self.clbits)}" if self.clbits else ""
        return f"{self.name}{p} q{list(self.qubits)}{c}"


@dataclass
class Circuit:
    """A quantum circuit on ``num_qubits`` qubits and ``num_clbits`` classical bits."""

    num_qubits: int
    num_clbits: int = 0
    name: str = "circuit"
    instructions: List[Instruction] = field(default_factory=list)
    metadata: Dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.num_qubits < 1:
            raise ValueError("a circuit needs at least one qubit")
        if self.num_clbits == 0:
            self.num_clbits = self.num_qubits

    # ------------------------------------------------------------------
    # container protocol
    # ------------------------------------------------------------------
    def __iter__(self) -> Iterator[Instruction]:
        return iter(self.instructions)

    def __len__(self) -> int:
        return len(self.instructions)

    def __repr__(self) -> str:
        return f"Circuit({self.name!r}, qubits={self.num_qubits}, ops={len(self)}, depth={self.depth()})"

    # ------------------------------------------------------------------
    # building
    # ------------------------------------------------------------------
    def append(self, name: str, qubits: Sequence[int], params: Sequence[float] = (),
               clbits: Sequence[int] = ()) -> "Circuit":
        for q in qubits:
            if not 0 <= q < self.num_qubits:
                raise IndexError(f"qubit {q} out of range for {self.num_qubits}-qubit circuit")
        for c in clbits:
            if not 0 <= c < self.num_clbits:
                raise IndexError(f"clbit {c} out of range")
        self.instructions.append(Instruction(name, tuple(qubits), tuple(params), tuple(clbits)))
        return self

    def extend(self, other: "Circuit", qubit_map: Optional[Sequence[int]] = None) -> "Circuit":
        qmap = list(qubit_map) if qubit_map is not None else list(range(other.num_qubits))
        for ins in other:
            self.append(ins.name, [qmap[q] for q in ins.qubits], ins.params, ins.clbits)
        return self

    def copy(self, name: Optional[str] = None) -> "Circuit":
        c = Circuit(self.num_qubits, self.num_clbits, name or self.name, metadata=dict(self.metadata))
        c.instructions = [Instruction(i.name, i.qubits, i.params, i.clbits) for i in self.instructions]
        return c

    # fluent single-qubit API -------------------------------------------
    def id(self, q: int) -> "Circuit": return self.append("id", [q])
    def x(self, q: int) -> "Circuit": return self.append("x", [q])
    def y(self, q: int) -> "Circuit": return self.append("y", [q])
    def z(self, q: int) -> "Circuit": return self.append("z", [q])
    def h(self, q: int) -> "Circuit": return self.append("h", [q])
    def s(self, q: int) -> "Circuit": return self.append("s", [q])
    def sdg(self, q: int) -> "Circuit": return self.append("sdg", [q])
    def t(self, q: int) -> "Circuit": return self.append("t", [q])
    def tdg(self, q: int) -> "Circuit": return self.append("tdg", [q])
    def sx(self, q: int) -> "Circuit": return self.append("sx", [q])
    def rx(self, theta: float, q: int) -> "Circuit": return self.append("rx", [q], [theta])
    def ry(self, theta: float, q: int) -> "Circuit": return self.append("ry", [q], [theta])
    def rz(self, theta: float, q: int) -> "Circuit": return self.append("rz", [q], [theta])
    def p(self, lam: float, q: int) -> "Circuit": return self.append("p", [q], [lam])
    def u(self, theta: float, phi: float, lam: float, q: int) -> "Circuit":
        return self.append("u", [q], [theta, phi, lam])

    # fluent multi-qubit API --------------------------------------------
    def cx(self, c: int, t: int) -> "Circuit": return self.append("cx", [c, t])
    def cy(self, c: int, t: int) -> "Circuit": return self.append("cy", [c, t])
    def cz(self, a: int, b: int) -> "Circuit": return self.append("cz", [a, b])
    def ch(self, c: int, t: int) -> "Circuit": return self.append("ch", [c, t])
    def cp(self, lam: float, c: int, t: int) -> "Circuit": return self.append("cp", [c, t], [lam])
    def crz(self, theta: float, c: int, t: int) -> "Circuit": return self.append("crz", [c, t], [theta])
    def swap(self, a: int, b: int) -> "Circuit": return self.append("swap", [a, b])
    def iswap(self, a: int, b: int) -> "Circuit": return self.append("iswap", [a, b])
    def rxx(self, theta: float, a: int, b: int) -> "Circuit": return self.append("rxx", [a, b], [theta])
    def ryy(self, theta: float, a: int, b: int) -> "Circuit": return self.append("ryy", [a, b], [theta])
    def rzz(self, theta: float, a: int, b: int) -> "Circuit": return self.append("rzz", [a, b], [theta])
    def ccx(self, c0: int, c1: int, t: int) -> "Circuit": return self.append("ccx", [c0, c1, t])
    def cswap(self, c: int, a: int, b: int) -> "Circuit": return self.append("cswap", [c, a, b])

    def barrier(self, *qubits: int) -> "Circuit":
        return self.append("barrier", qubits or range(self.num_qubits))

    def reset(self, q: int) -> "Circuit":
        return self.append("reset", [q])

    def measure(self, q: int, c: Optional[int] = None) -> "Circuit":
        return self.append("measure", [q], clbits=[q if c is None else c])

    def measure_all(self) -> "Circuit":
        for q in range(self.num_qubits):
            self.measure(q, q)
        return self

    # ------------------------------------------------------------------
    # analysis
    # ------------------------------------------------------------------
    def count_ops(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for ins in self.instructions:
            out[ins.name] = out.get(ins.name, 0) + 1
        return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))

    def depth(self, include_barriers: bool = False) -> int:
        level = [0] * self.num_qubits
        for ins in self.instructions:
            if ins.name == "barrier" and not include_barriers:
                if ins.qubits:
                    top = max(level[q] for q in ins.qubits)
                    for q in ins.qubits:
                        level[q] = top
                continue
            top = max(level[q] for q in ins.qubits) + 1
            for q in ins.qubits:
                level[q] = top
        return max(level) if level else 0

    def two_qubit_count(self) -> int:
        return sum(1 for i in self.instructions if i.is_gate and len(i.qubits) == 2)

    def used_qubits(self) -> List[int]:
        return sorted({q for i in self.instructions for q in i.qubits})

    def has_measurements(self) -> bool:
        return any(i.name == "measure" for i in self.instructions)

    def layers(self) -> List[List[Instruction]]:
        """Group gates into layers that can run in parallel."""
        level = [0] * self.num_qubits
        out: List[List[Instruction]] = []
        for ins in self.instructions:
            if ins.name == "barrier":
                continue
            lv = max(level[q] for q in ins.qubits)
            while len(out) <= lv:
                out.append([])
            out[lv].append(ins)
            for q in ins.qubits:
                level[q] = lv + 1
        return out

    # ------------------------------------------------------------------
    # transformations
    # ------------------------------------------------------------------
    def inverse(self) -> "Circuit":
        """Return the inverse circuit (measurements and resets are not allowed)."""
        inv = Circuit(self.num_qubits, self.num_clbits, self.name + "_dg")
        for ins in reversed(self.instructions):
            if ins.name == "barrier":
                inv.append("barrier", ins.qubits)
                continue
            if not ins.is_gate:
                raise ValueError("cannot invert a circuit that contains measure or reset")
            name, params = _inverse_of(ins.name, ins.params)
            inv.append(name, ins.qubits, params)
        return inv

    def remove_final_measurements(self) -> "Circuit":
        c = self.copy()
        while c.instructions and c.instructions[-1].name in ("measure", "barrier"):
            c.instructions.pop()
        return c

    def to_matrix(self) -> G.Matrix:
        """Full unitary of the circuit (small circuits only, up to ~10 qubits)."""
        from .simulator import circuit_unitary

        return circuit_unitary(self)

    def draw(self) -> str:
        """Plain-text drawing of the circuit."""
        from .draw import text_drawing

        return text_drawing(self)


_SELF_INVERSE = {"id", "x", "y", "z", "h", "cx", "cy", "cz", "ch", "swap", "ccx", "cswap"}
_PAIR = {"s": "sdg", "sdg": "s", "t": "tdg", "tdg": "t", "sx": "sxdg", "sxdg": "sx"}
_NEG = {"rx", "ry", "rz", "p", "cp", "crz", "rxx", "ryy", "rzz"}


def _inverse_of(name: str, params: Tuple[float, ...]) -> Tuple[str, Tuple[float, ...]]:
    if name in _SELF_INVERSE:
        return name, params
    if name in _PAIR:
        return _PAIR[name], params
    if name in _NEG:
        return name, tuple(-p for p in params)
    if name == "u":
        theta, phi, lam = params
        return "u", (-theta, -lam, -phi)
    if name == "prx":
        theta, phi = params
        return "prx", (-theta, phi)
    if name == "gpi":
        return "gpi", params
    if name == "gpi2":
        return "gpi2", (params[0] + math.pi,)
    if name == "iswap":
        # iSWAP^-1 = iSWAP^3; expressed with rzz/rxx/ryy for simplicity
        raise ValueError("inverse of iswap is not supported yet")
    if name in ("ecr", "ms"):
        raise ValueError(f"inverse of {name} is not supported yet")
    raise ValueError(f"no inverse rule for {name}")


def from_instructions(num_qubits: int, items: Iterable[Tuple[str, Sequence[int], Sequence[float]]],
                      name: str = "circuit") -> Circuit:
    c = Circuit(num_qubits, name=name)
    for gname, qs, ps in items:
        c.append(gname, qs, ps)
    return c

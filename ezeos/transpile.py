"""EZE OS transpiler: lower a hardware-neutral circuit to a concrete device.

Pipeline
--------
1. ``lower_to_cx``      every multi-qubit gate -> CX + single-qubit gates
2. ``route``            insert SWAPs so every CX acts on coupled qubits
3. ``merge_1q``         fuse runs of single-qubit gates into one unitary
4. ``to_native``        rewrite CX and 1q unitaries in the device's native set
5. ``cancel``           remove identities and cancel adjacent inverse pairs

Every rewrite rule in this module is checked against the exact unitary in the
test-suite (``tests/test_transpile.py``).
"""
from __future__ import annotations

import cmath
import math
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from . import gates as G
from .circuit import Circuit, Instruction
from .devices import Device

PI = math.pi
TOL = 1e-9


# --------------------------------------------------------------------------
# single-qubit synthesis
# --------------------------------------------------------------------------

def zyz_angles(u: G.Matrix) -> Tuple[float, float, float, float]:
    """Return (theta, phi, lam, phase) with u = e^{i phase} RZ(phi) RY(theta) RZ(lam)."""
    det = u[0][0] * u[1][1] - u[0][1] * u[1][0]
    phase = cmath.phase(det) / 2
    k = cmath.exp(-1j * phase)
    a, b = u[0][0] * k, u[0][1] * k
    c, d = u[1][0] * k, u[1][1] * k
    theta = 2 * math.atan2(abs(c), abs(a))
    if abs(c) < TOL:            # diagonal
        phi_plus_lam = 2 * cmath.phase(d)
        return 0.0, phi_plus_lam, 0.0, phase
    if abs(a) < TOL:            # anti-diagonal
        phi_minus_lam = 2 * cmath.phase(c)
        return theta, phi_minus_lam, 0.0, phase
    s = cmath.phase(d)          # (phi + lam) / 2
    t = cmath.phase(c)          # (phi - lam) / 2
    return theta, s + t, s - t, phase


def _wrap(x: float) -> float:
    x = math.fmod(x + PI, 2 * PI)
    if x < 0:
        x += 2 * PI
    return x - PI


def _is_zero_angle(x: float) -> bool:
    return abs(_wrap(x)) < 1e-10


def synth_1q(u: G.Matrix, q: int, basis: Sequence[str]) -> List[Instruction]:
    """Synthesize a 2x2 unitary on qubit ``q`` using gates from ``basis``."""
    theta, phi, lam, _ = zyz_angles(u)
    out: List[Instruction] = []
    b = set(basis)

    def rz(a):
        if not _is_zero_angle(a):
            out.append(Instruction("rz", (q,), (_wrap(a),)))

    if "u" in b:
        if not (_is_zero_angle(theta) and _is_zero_angle(phi + lam)):
            out.append(Instruction("u", (q,), (theta, phi, lam)))
        return out
    if {"rz", "sx"} <= b:                        # IBM: RZ SX RZ SX RZ
        if _is_zero_angle(theta):
            rz(phi + lam)
            return out
        rz(lam)
        out.append(Instruction("sx", (q,)))
        rz(theta + PI)
        out.append(Instruction("sx", (q,)))
        rz(phi + PI)
        return out
    if "prx" in b:                               # IQM / Quantinuum: PRX + (virtual) RZ
        # u = RZ(phi) RY(theta) RZ(lam) = PRX(theta, phi + pi/2) . RZ(phi + lam)
        z = phi + lam
        if not _is_zero_angle(z):
            if "rz" in b:
                rz(z)
            else:   # RZ(z) = RX(pi/2) RY(z)... expressed with PRX only
                out.append(Instruction("prx", (q,), (-PI / 2, 0.0)))
                out.append(Instruction("prx", (q,), (_wrap(z), PI / 2)))
                out.append(Instruction("prx", (q,), (PI / 2, 0.0)))
        if not _is_zero_angle(theta):
            out.append(Instruction("prx", (q,), (theta, _wrap(phi + PI / 2))))
        return out
    if "gpi2" in b:                              # IonQ: GPI2 + virtual RZ (frame tracked later)
        # RY(theta) = RX(pi/2) RZ(-theta) RX(-pi/2); RX(+-pi/2) = GPI2(0) / GPI2(pi)
        rz(lam)
        if not _is_zero_angle(theta):
            out.append(Instruction("gpi2", (q,), (PI,)))
            rz(-theta)
            out.append(Instruction("gpi2", (q,), (0.0,)))
        rz(phi)
        return out
    if {"rx", "rz"} <= b and "ry" not in b:      # Rigetti: RY via RZ-conjugated RX
        rz(lam)
        if not _is_zero_angle(theta):
            rz(-PI / 2)
            out.append(Instruction("rx", (q,), (_wrap(theta),)))
            rz(PI / 2)
        rz(phi)
        return _cleanup_rz(out)
    if {"ry", "rz"} <= b:                        # generic ZYZ
        rz(lam)
        if not _is_zero_angle(theta):
            out.append(Instruction("ry", (q,), (_wrap(theta),)))
        rz(phi)
        return out
    raise ValueError(f"cannot synthesize single-qubit gates for basis {sorted(b)}")


def _cleanup_rz(seq: List[Instruction]) -> List[Instruction]:
    out: List[Instruction] = []
    for ins in seq:
        if out and ins.name == "rz" and out[-1].name == "rz":
            a = _wrap(out[-1].params[0] + ins.params[0])
            out.pop()
            if not _is_zero_angle(a):
                out.append(Instruction("rz", ins.qubits, (a,)))
        else:
            out.append(ins)
    return out


# --------------------------------------------------------------------------
# pass 1: lower everything to {1q, cx}
# --------------------------------------------------------------------------

def _rules(ins: Instruction) -> Optional[List[Tuple[str, Tuple[int, ...], Tuple[float, ...]]]]:
    n, q, p = ins.name, ins.qubits, ins.params
    if n == "cz":
        a, b = q
        return [("h", (b,), ()), ("cx", (a, b), ()), ("h", (b,), ())]
    if n == "cy":
        c, t = q
        return [("sdg", (t,), ()), ("cx", (c, t), ()), ("s", (t,), ())]
    if n == "ch":
        c, t = q
        return [("ry", (t,), (PI / 4,)), ("cx", (c, t), ()), ("ry", (t,), (-PI / 4,))]
    if n == "cp":
        c, t = q
        lam = p[0]
        return [("p", (c,), (lam / 2,)), ("cx", (c, t), ()), ("p", (t,), (-lam / 2,)),
                ("cx", (c, t), ()), ("p", (t,), (lam / 2,))]
    if n == "crz":
        c, t = q
        th = p[0]
        return [("rz", (t,), (th / 2,)), ("cx", (c, t), ()), ("rz", (t,), (-th / 2,)), ("cx", (c, t), ())]
    if n == "swap":
        a, b = q
        return [("cx", (a, b), ()), ("cx", (b, a), ()), ("cx", (a, b), ())]
    if n == "rzz":
        a, b = q
        return [("cx", (a, b), ()), ("rz", (b,), (p[0],)), ("cx", (a, b), ())]
    if n == "rxx":
        a, b = q
        return [("h", (a,), ()), ("h", (b,), ()), ("rzz", (a, b), p), ("h", (a,), ()), ("h", (b,), ())]
    if n == "ryy":
        a, b = q
        return [("rx", (a,), (PI / 2,)), ("rx", (b,), (PI / 2,)), ("rzz", (a, b), p),
                ("rx", (a,), (-PI / 2,)), ("rx", (b,), (-PI / 2,))]
    if n == "iswap":
        a, b = q
        return [("s", (a,), ()), ("s", (b,), ()), ("h", (a,), ()), ("cx", (a, b), ()),
                ("cx", (b, a), ()), ("h", (b,), ())]
    if n == "ms":
        a, b = q
        p0, p1 = p
        return [("rz", (a,), (-p0,)), ("rz", (b,), (-p1,)), ("rxx", (a, b), (PI / 2,)),
                ("rz", (a,), (p0,)), ("rz", (b,), (p1,))]
    if n == "ccx":
        a, b, t = q
        return [("h", (t,), ()), ("cx", (b, t), ()), ("tdg", (t,), ()), ("cx", (a, t), ()),
                ("t", (t,), ()), ("cx", (b, t), ()), ("tdg", (t,), ()), ("cx", (a, t), ()),
                ("t", (b,), ()), ("t", (t,), ()), ("h", (t,), ()), ("cx", (a, b), ()),
                ("t", (a,), ()), ("tdg", (b,), ()), ("cx", (a, b), ())]
    if n == "cswap":
        c, a, b = q
        return [("cx", (b, a), ()), ("ccx", (c, a, b), ()), ("cx", (b, a), ())]
    return None


def lower_to_cx(circuit: Circuit) -> Circuit:
    out = Circuit(circuit.num_qubits, circuit.num_clbits, circuit.name, metadata=dict(circuit.metadata))
    stack = list(reversed(circuit.instructions))
    while stack:
        ins = stack.pop()
        if not ins.is_gate or len(ins.qubits) == 1 or ins.name == "cx":
            out.instructions.append(ins)
            continue
        rule = _rules(ins)
        if rule is None:
            raise ValueError(f"no lowering rule for gate '{ins.name}'")
        for item in reversed(rule):
            stack.append(Instruction(*item))
    return out


# --------------------------------------------------------------------------
# pass 2: routing
# --------------------------------------------------------------------------

@dataclass
class Layout:
    """Mapping logical qubit -> physical qubit."""

    l2p: List[int]

    @classmethod
    def trivial(cls, n: int) -> "Layout":
        return cls(list(range(n)))

    def p2l(self) -> Dict[int, int]:
        return {p: l for l, p in enumerate(self.l2p)}

    def swap_physical(self, pa: int, pb: int) -> None:
        inv = self.p2l()
        la, lb = inv.get(pa), inv.get(pb)
        if la is not None:
            self.l2p[la] = pb
        if lb is not None:
            self.l2p[lb] = pa


def _shortest_path(nb: Dict[int, List[int]], a: int, b: int) -> List[int]:
    prev = {a: None}
    dq = deque([a])
    while dq:
        x = dq.popleft()
        if x == b:
            break
        for y in nb[x]:
            if y not in prev:
                prev[y] = x
                dq.append(y)
    if b not in prev:
        raise ValueError(f"physical qubits {a} and {b} are not connected")
    path = [b]
    while path[-1] != a:
        path.append(prev[path[-1]])
    return list(reversed(path))


def initial_layout(circuit: Circuit, device: Device) -> Layout:
    """Place the most-interacting logical qubits on the best-connected physical qubits."""
    n = circuit.num_qubits
    if n > device.qubits:
        raise ValueError(f"circuit needs {n} qubits but {device.model} has {device.qubits}")
    nb = device.neighbors()
    if not any(nb.values()):
        return Layout.trivial(n)
    weight = [0] * n
    for ins in circuit:
        if ins.is_gate and len(ins.qubits) > 1:
            for q in ins.qubits:
                weight[q] += 1
    order = sorted(range(n), key=lambda q: -weight[q])
    start = max(nb, key=lambda p: len(nb[p]))
    phys: List[int] = []
    seen = {start}
    dq = deque([start])
    while dq and len(phys) < n:
        x = dq.popleft()
        phys.append(x)
        for y in sorted(nb[x], key=lambda y: -len(nb[y])):
            if y not in seen:
                seen.add(y)
                dq.append(y)
    if len(phys) < n:
        phys += [p for p in range(device.qubits) if p not in phys][: n - len(phys)]
    l2p = [0] * n
    for lq, pq in zip(order, phys):
        l2p[lq] = pq
    return Layout(l2p)


def route(circuit: Circuit, device: Device, layout: Optional[Layout] = None) -> Tuple[Circuit, Layout, Layout]:
    """Map a {1q, cx} circuit onto ``device``. Returns (circuit, initial, final) layouts."""
    lay = layout or initial_layout(circuit, device)
    init = Layout(list(lay.l2p))
    nb = device.neighbors()
    out = Circuit(device.qubits, circuit.num_clbits, circuit.name, metadata=dict(circuit.metadata))
    edges = set(device.coupling_map()) | {(b, a) for a, b in device.coupling_map()}
    for ins in circuit:
        phys = [lay.l2p[q] for q in ins.qubits]
        if ins.name == "cx":
            a, b = phys
            if (a, b) not in edges:
                path = _shortest_path(nb, a, b)
                for k in range(len(path) - 2):
                    x, y = path[k], path[k + 1]
                    for c, t in ((x, y), (y, x), (x, y)):
                        out.instructions.append(Instruction("cx", (c, t)))
                    lay.swap_physical(x, y)
                a, b = lay.l2p[ins.qubits[0]], lay.l2p[ins.qubits[1]]
            out.instructions.append(Instruction("cx", (a, b)))
            continue
        out.instructions.append(Instruction(ins.name, tuple(phys), ins.params, ins.clbits))
    return out, init, lay


# --------------------------------------------------------------------------
# pass 3: merge single-qubit runs
# --------------------------------------------------------------------------

def merge_1q(circuit: Circuit) -> Circuit:
    pending: Dict[int, G.Matrix] = {}
    out = Circuit(circuit.num_qubits, circuit.num_clbits, circuit.name, metadata=dict(circuit.metadata))

    def flush(q: int) -> None:
        if q in pending:
            m = pending.pop(q)
            if not G.equal_up_to_phase(m, G.identity(2)):
                theta, phi, lam, _ = zyz_angles(m)
                out.instructions.append(Instruction("u", (q,), (theta, phi, lam)))

    for ins in circuit:
        if ins.is_gate and len(ins.qubits) == 1:
            q = ins.qubits[0]
            pending[q] = G.matmul(ins.unitary(), pending.get(q, G.identity(2)))
            continue
        qs = ins.qubits if ins.name != "barrier" else ins.qubits or range(circuit.num_qubits)
        for q in qs:
            flush(q)
        out.instructions.append(ins)
    for q in list(pending):
        flush(q)
    return out


# --------------------------------------------------------------------------
# pass 4: native rewriting
# --------------------------------------------------------------------------

def _cx_native(c: int, t: int, native: Sequence[str]) -> List[Instruction]:
    nset = set(native)
    if "cx" in nset:
        return [Instruction("cx", (c, t))]
    if "cz" in nset:
        return [Instruction("h", (t,)), Instruction("cz", (c, t)), Instruction("h", (t,))]
    if "rzz" in nset:   # CZ = RZZ(pi/2) RZ(-pi/2) RZ(-pi/2) up to phase
        return [Instruction("h", (t,)), Instruction("rzz", (c, t), (PI / 2,)),
                Instruction("rz", (c,), (-PI / 2,)), Instruction("rz", (t,), (-PI / 2,)),
                Instruction("h", (t,))]
    if "ms" in nset or "rxx" in nset:
        ent = Instruction("ms", (c, t), (0.0, 0.0)) if "ms" in nset else Instruction("rxx", (c, t), (PI / 2,))
        return [Instruction("ry", (c,), (PI / 2,)), ent, Instruction("rx", (c,), (-PI / 2,)),
                Instruction("rx", (t,), (-PI / 2,)), Instruction("ry", (c,), (-PI / 2,))]
    raise ValueError(f"no CX rule for native set {sorted(nset)}")


def to_native(circuit: Circuit, device: Device) -> Circuit:
    native = device.native_gates
    basis_1q = [g for g in native if G.GATES.get(g) and G.GATES[g].num_qubits == 1]
    # expand cx first, then merge the extra 1q gates and synthesize
    expanded = Circuit(circuit.num_qubits, circuit.num_clbits, circuit.name, metadata=dict(circuit.metadata))
    for ins in circuit:
        if ins.name == "cx":
            expanded.instructions.extend(_cx_native(ins.qubits[0], ins.qubits[1], native))
        else:
            expanded.instructions.append(ins)
    merged = merge_1q(expanded)
    out = Circuit(circuit.num_qubits, circuit.num_clbits, circuit.name, metadata=dict(circuit.metadata))
    for ins in merged:
        if ins.is_gate and len(ins.qubits) == 1:
            out.instructions.extend(synth_1q(ins.unitary(), ins.qubits[0], basis_1q))
        else:
            out.instructions.append(ins)
    if "gpi2" in native:
        out = _ionq_virtual_z(out)
    return out


def _ionq_virtual_z(circuit: Circuit) -> Circuit:
    """Absorb RZ gates into the phases of following GPI/GPI2/MS gates (IonQ style)."""
    frame = [0.0] * circuit.num_qubits
    out = Circuit(circuit.num_qubits, circuit.num_clbits, circuit.name, metadata=dict(circuit.metadata))
    for ins in circuit:
        if ins.name == "rz":
            frame[ins.qubits[0]] += ins.params[0]
            continue
        if ins.name in ("gpi", "gpi2"):
            q = ins.qubits[0]
            out.instructions.append(Instruction(ins.name, ins.qubits, (_wrap(ins.params[0] - frame[q]),)))
            continue
        if ins.name == "ms":
            a, b = ins.qubits
            out.instructions.append(Instruction("ms", ins.qubits, (_wrap(ins.params[0] - frame[a]),
                                                                   _wrap(ins.params[1] - frame[b]))))
            continue
        out.instructions.append(ins)
    out.metadata["final_z_frame"] = frame
    return out


# --------------------------------------------------------------------------
# pass 5: peephole cancellation
# --------------------------------------------------------------------------

def cancel(circuit: Circuit) -> Circuit:
    changed = True
    ins = list(circuit.instructions)
    while changed:
        changed = False
        out: List[Instruction] = []
        last_on: Dict[int, int] = {}
        for i in ins:
            if i.name == "rz" and _is_zero_angle(i.params[0]):
                changed = True
                continue
            if i.is_gate and i.name in ("cx", "cz", "h", "x", "swap"):
                idxs = {last_on.get(q) for q in i.qubits}
                if len(idxs) == 1 and None not in idxs:
                    j = idxs.pop()
                    prev = out[j]
                    if prev is not None and prev.name == i.name and prev.qubits == i.qubits:
                        out[j] = None  # type: ignore[assignment]
                        for q in i.qubits:
                            last_on.pop(q, None)
                        changed = True
                        continue
            out.append(i)
            for q in (i.qubits if i.name != "barrier" else []):
                last_on[q] = len(out) - 1
        ins = [x for x in out if x is not None]
    c = Circuit(circuit.num_qubits, circuit.num_clbits, circuit.name, metadata=dict(circuit.metadata))
    c.instructions = ins
    return c


# --------------------------------------------------------------------------
# public entry point
# --------------------------------------------------------------------------

@dataclass
class TranspileReport:
    device: str
    initial_layout: List[int]
    final_layout: List[int]
    swaps_inserted: int
    depth_before: int
    depth_after: int
    two_qubit_before: int
    two_qubit_after: int
    ops_after: Dict[str, int] = field(default_factory=dict)

    def __str__(self) -> str:
        return (f"device={self.device} depth {self.depth_before}->{self.depth_after} "
                f"2q {self.two_qubit_before}->{self.two_qubit_after} swaps={self.swaps_inserted} "
                f"ops={self.ops_after}")


def transpile(circuit: Circuit, device: Device, layout: Optional[Layout] = None) -> Tuple[Circuit, TranspileReport]:
    if not device.gate_model:
        raise ValueError(f"{device.model} is not a gate-model device; use ezeos.annealing instead")
    lowered = lower_to_cx(circuit)
    cx_before = sum(1 for i in lowered if i.name == "cx")
    routed, init, final = route(lowered, device, layout)
    swaps = (sum(1 for i in routed if i.name == "cx") - cx_before) // 3
    native = cancel(to_native(cancel(routed), device))
    report = TranspileReport(
        device=device.key, initial_layout=init.l2p, final_layout=final.l2p, swaps_inserted=swaps,
        depth_before=circuit.depth(), depth_after=native.depth(),
        two_qubit_before=circuit.two_qubit_count(), two_qubit_after=native.two_qubit_count(),
        ops_after=native.count_ops(),
    )
    native.metadata.update({"device": device.key, "initial_layout": init.l2p, "final_layout": final.l2p})
    return native, report

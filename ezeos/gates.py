"""Gate library for EZE OS.

Every gate is described by a name, the number of qubits it acts on, the
number of real parameters it takes and a function that returns its unitary
matrix. Matrices are plain nested Python lists of complex numbers so that the
core of EZE OS has no third-party dependencies.

Qubit ordering convention: qubit 0 is the least significant bit of a basis
state index, so ``|q2 q1 q0>`` reads right to left.
"""
from __future__ import annotations

import cmath
import math
from dataclasses import dataclass
from typing import Callable, Dict, List, Sequence

Matrix = List[List[complex]]

SQRT1_2 = 1 / math.sqrt(2)


@dataclass(frozen=True)
class GateSpec:
    """Static description of a gate type."""

    name: str
    num_qubits: int
    num_params: int
    matrix: Callable[..., Matrix]
    doc: str = ""

    def unitary(self, params: Sequence[float] = ()) -> Matrix:
        if len(params) != self.num_params:
            raise ValueError(
                f"gate {self.name} expects {self.num_params} parameter(s), got {len(params)}"
            )
        return self.matrix(*params)


# --------------------------------------------------------------------------
# matrix helpers
# --------------------------------------------------------------------------

def identity(n: int) -> Matrix:
    return [[1 + 0j if i == j else 0j for j in range(n)] for i in range(n)]


def matmul(a: Matrix, b: Matrix) -> Matrix:
    n, m, p = len(a), len(b), len(b[0])
    out = [[0j] * p for _ in range(n)]
    for i in range(n):
        ai = a[i]
        oi = out[i]
        for k in range(m):
            aik = ai[k]
            if aik == 0:
                continue
            bk = b[k]
            for j in range(p):
                oi[j] += aik * bk[j]
    return out


def dagger(a: Matrix) -> Matrix:
    return [[a[j][i].conjugate() for j in range(len(a))] for i in range(len(a[0]))]


def kron(a: Matrix, b: Matrix) -> Matrix:
    out: Matrix = []
    for ai in a:
        for bi in b:
            out.append([x * y for x in ai for y in bi])
    return out


def allclose(a: Matrix, b: Matrix, tol: float = 1e-9) -> bool:
    return all(abs(x - y) <= tol for ra, rb in zip(a, b) for x, y in zip(ra, rb))


def equal_up_to_phase(a: Matrix, b: Matrix, tol: float = 1e-8) -> bool:
    """True when ``a == e^{i phi} b`` for some global phase ``phi``."""
    phase = None
    for ra, rb in zip(a, b):
        for x, y in zip(ra, rb):
            if abs(y) > tol:
                phase = x / y
                break
        if phase is not None:
            break
    if phase is None or abs(abs(phase) - 1) > 1e-6:
        return False
    return all(abs(x - phase * y) <= tol for ra, rb in zip(a, b) for x, y in zip(ra, rb))


def is_unitary(a: Matrix, tol: float = 1e-9) -> bool:
    return allclose(matmul(a, dagger(a)), identity(len(a)), tol)


# --------------------------------------------------------------------------
# single-qubit gates
# --------------------------------------------------------------------------

def _i() -> Matrix:
    return identity(2)


def _x() -> Matrix:
    return [[0j, 1 + 0j], [1 + 0j, 0j]]


def _y() -> Matrix:
    return [[0j, -1j], [1j, 0j]]


def _z() -> Matrix:
    return [[1 + 0j, 0j], [0j, -1 + 0j]]


def _h() -> Matrix:
    return [[SQRT1_2 + 0j, SQRT1_2 + 0j], [SQRT1_2 + 0j, -SQRT1_2 + 0j]]


def _s() -> Matrix:
    return [[1 + 0j, 0j], [0j, 1j]]


def _sdg() -> Matrix:
    return [[1 + 0j, 0j], [0j, -1j]]


def _t() -> Matrix:
    return [[1 + 0j, 0j], [0j, cmath.exp(1j * math.pi / 4)]]


def _tdg() -> Matrix:
    return [[1 + 0j, 0j], [0j, cmath.exp(-1j * math.pi / 4)]]


def _sx() -> Matrix:
    return [[(1 + 1j) / 2, (1 - 1j) / 2], [(1 - 1j) / 2, (1 + 1j) / 2]]


def _sxdg() -> Matrix:
    return dagger(_sx())


def _rx(theta: float) -> Matrix:
    c, s = math.cos(theta / 2), math.sin(theta / 2)
    return [[c + 0j, -1j * s], [-1j * s, c + 0j]]


def _ry(theta: float) -> Matrix:
    c, s = math.cos(theta / 2), math.sin(theta / 2)
    return [[c + 0j, -s + 0j], [s + 0j, c + 0j]]


def _rz(theta: float) -> Matrix:
    return [[cmath.exp(-1j * theta / 2), 0j], [0j, cmath.exp(1j * theta / 2)]]


def _p(lam: float) -> Matrix:
    return [[1 + 0j, 0j], [0j, cmath.exp(1j * lam)]]


def _u(theta: float, phi: float, lam: float) -> Matrix:
    c, s = math.cos(theta / 2), math.sin(theta / 2)
    return [
        [c + 0j, -cmath.exp(1j * lam) * s],
        [cmath.exp(1j * phi) * s, cmath.exp(1j * (phi + lam)) * c],
    ]


def _prx(theta: float, phi: float) -> Matrix:
    """IQM native phased-RX: rotation by ``theta`` about an axis at angle ``phi`` in the XY plane."""
    c, s = math.cos(theta / 2), math.sin(theta / 2)
    return [
        [c + 0j, -1j * cmath.exp(-1j * phi) * s],
        [-1j * cmath.exp(1j * phi) * s, c + 0j],
    ]


def _gpi(phi: float) -> Matrix:
    """IonQ native GPI gate (``phi`` in radians)."""
    return [[0j, cmath.exp(-1j * phi)], [cmath.exp(1j * phi), 0j]]


def _gpi2(phi: float) -> Matrix:
    """IonQ native GPI2 gate (``phi`` in radians)."""
    return [
        [SQRT1_2 + 0j, -1j * cmath.exp(-1j * phi) * SQRT1_2],
        [-1j * cmath.exp(1j * phi) * SQRT1_2, SQRT1_2 + 0j],
    ]


# --------------------------------------------------------------------------
# two-qubit gates (matrix index = 2*q1 + q0 for operands (q0, q1))
# The first operand is the less significant qubit of the 4x4 matrix.
# For controlled gates the first operand is the control.
# --------------------------------------------------------------------------

def _controlled(u: Matrix) -> Matrix:
    """Controlled-U where operand 0 (LSB) is the control, operand 1 the target."""
    m = identity(4)
    # basis index b = 2*t + c ; control set when c == 1 -> indices 1 and 3
    m[1][1], m[1][3] = u[0][0], u[0][1]
    m[3][1], m[3][3] = u[1][0], u[1][1]
    return m


def _cx() -> Matrix:
    return _controlled(_x())


def _cy() -> Matrix:
    return _controlled(_y())


def _cz() -> Matrix:
    m = identity(4)
    m[3][3] = -1 + 0j
    return m


def _ch() -> Matrix:
    return _controlled(_h())


def _cp(lam: float) -> Matrix:
    m = identity(4)
    m[3][3] = cmath.exp(1j * lam)
    return m


def _crz(theta: float) -> Matrix:
    return _controlled(_rz(theta))


def _swap() -> Matrix:
    m = [[0j] * 4 for _ in range(4)]
    m[0][0] = m[3][3] = 1 + 0j
    m[1][2] = m[2][1] = 1 + 0j
    return m


def _iswap() -> Matrix:
    m = [[0j] * 4 for _ in range(4)]
    m[0][0] = m[3][3] = 1 + 0j
    m[1][2] = m[2][1] = 1j
    return m


def _ecr() -> Matrix:
    """IBM echoed cross-resonance gate (operand 0 = control, operand 1 = target)."""
    a = SQRT1_2
    # Standard ECR in big-endian |c t> ordering:
    # 1/sqrt2 [[0,1,0,i],[1,0,-i,0],[0,i,0,1],[-i,0,1,0]]
    big = [
        [0j, a + 0j, 0j, 1j * a],
        [a + 0j, 0j, -1j * a, 0j],
        [0j, 1j * a, 0j, a + 0j],
        [-1j * a, 0j, a + 0j, 0j],
    ]
    return _big_to_little(big)


def _rxx(theta: float) -> Matrix:
    c, s = math.cos(theta / 2), math.sin(theta / 2)
    return [
        [c + 0j, 0j, 0j, -1j * s],
        [0j, c + 0j, -1j * s, 0j],
        [0j, -1j * s, c + 0j, 0j],
        [-1j * s, 0j, 0j, c + 0j],
    ]


def _ryy(theta: float) -> Matrix:
    c, s = math.cos(theta / 2), math.sin(theta / 2)
    return [
        [c + 0j, 0j, 0j, 1j * s],
        [0j, c + 0j, -1j * s, 0j],
        [0j, -1j * s, c + 0j, 0j],
        [1j * s, 0j, 0j, c + 0j],
    ]


def _rzz(theta: float) -> Matrix:
    e0, e1 = cmath.exp(-1j * theta / 2), cmath.exp(1j * theta / 2)
    return [
        [e0, 0j, 0j, 0j],
        [0j, e1, 0j, 0j],
        [0j, 0j, e1, 0j],
        [0j, 0j, 0j, e0],
    ]


def _zz(theta: float) -> Matrix:
    """IonQ Forte native ZZ gate, ``exp(-i theta/2 Z⊗Z)`` with ``theta`` in radians.

    IonQ documents ZZ(t) = exp(-i pi t Z⊗Z) with ``t`` in turns (1 turn = 2 pi rad),
    so ``theta = 2 pi t``; the IonQ backend converts back to turns. It has the same
    matrix as :func:`_rzz` but is kept as its own name so the transpiler and the
    IonQ payload emit exactly the gate Forte-class systems accept.
    Source: https://docs.ionq.com/guides/getting-started-with-native-gates
    """
    return _rzz(theta)


def _ms(phi0: float, phi1: float) -> Matrix:
    """IonQ native fully entangling Molmer-Sorensen gate (angles in radians)."""
    a = SQRT1_2
    big = [
        [a + 0j, 0j, 0j, -1j * a * cmath.exp(-1j * (phi0 + phi1))],
        [0j, a + 0j, -1j * a * cmath.exp(-1j * (phi0 - phi1)), 0j],
        [0j, -1j * a * cmath.exp(1j * (phi0 - phi1)), a + 0j, 0j],
        [-1j * a * cmath.exp(1j * (phi0 + phi1)), 0j, 0j, a + 0j],
    ]
    return _big_to_little(big)


def _big_to_little(big: Matrix) -> Matrix:
    """Convert a 4x4 matrix written in |q0 q1> (big-endian) order to EZE OS order."""
    perm = [0, 2, 1, 3]
    return [[big[perm[i]][perm[j]] for j in range(4)] for i in range(4)]


# --------------------------------------------------------------------------
# three-qubit gates
# --------------------------------------------------------------------------

def _ccx() -> Matrix:
    """Toffoli: operands (c0, c1, target)."""
    m = identity(8)
    # control bits 0 and 1 set: indices 3 (t=0) and 7 (t=1)
    m[3][3], m[3][7], m[7][3], m[7][7] = 0j, 1 + 0j, 1 + 0j, 0j
    return m


def _cswap() -> Matrix:
    """Fredkin: operands (control, a, b)."""
    m = identity(8)
    # control = bit0 ; swap bit1 and bit2 -> indices 3 (011) and 5 (101)
    m[3][3], m[3][5], m[5][3], m[5][5] = 0j, 1 + 0j, 1 + 0j, 0j
    return m


GATES: Dict[str, GateSpec] = {}


def _register(name: str, nq: int, npar: int, fn: Callable[..., Matrix], doc: str) -> None:
    GATES[name] = GateSpec(name, nq, npar, fn, doc)


_register("id", 1, 0, _i, "Identity")
_register("x", 1, 0, _x, "Pauli X (NOT)")
_register("y", 1, 0, _y, "Pauli Y")
_register("z", 1, 0, _z, "Pauli Z")
_register("h", 1, 0, _h, "Hadamard")
_register("s", 1, 0, _s, "Phase S = sqrt(Z)")
_register("sdg", 1, 0, _sdg, "S dagger")
_register("t", 1, 0, _t, "T = fourth root of Z")
_register("tdg", 1, 0, _tdg, "T dagger")
_register("sx", 1, 0, _sx, "sqrt(X)")
_register("sxdg", 1, 0, _sxdg, "sqrt(X) dagger")
_register("rx", 1, 1, _rx, "Rotation about X")
_register("ry", 1, 1, _ry, "Rotation about Y")
_register("rz", 1, 1, _rz, "Rotation about Z")
_register("p", 1, 1, _p, "Phase gate")
_register("u", 1, 3, _u, "Generic single-qubit gate U(theta, phi, lambda)")
_register("prx", 1, 2, _prx, "IQM native phased RX")
_register("gpi", 1, 1, _gpi, "IonQ native GPI")
_register("gpi2", 1, 1, _gpi2, "IonQ native GPI2")
_register("cx", 2, 0, _cx, "Controlled-X (CNOT)")
_register("cy", 2, 0, _cy, "Controlled-Y")
_register("cz", 2, 0, _cz, "Controlled-Z")
_register("ch", 2, 0, _ch, "Controlled-Hadamard")
_register("cp", 2, 1, _cp, "Controlled phase")
_register("crz", 2, 1, _crz, "Controlled RZ")
_register("swap", 2, 0, _swap, "SWAP")
_register("iswap", 2, 0, _iswap, "iSWAP")
_register("ecr", 2, 0, _ecr, "IBM echoed cross-resonance")
_register("rxx", 2, 1, _rxx, "XX rotation")
_register("ryy", 2, 1, _ryy, "YY rotation")
_register("rzz", 2, 1, _rzz, "ZZ rotation (Quantinuum native family)")
_register("ms", 2, 2, _ms, "IonQ native Molmer-Sorensen (Aria-class systems)")
_register("zz", 2, 1, _zz, "IonQ native ZZ (Forte-class systems)")
_register("ccx", 3, 0, _ccx, "Toffoli")
_register("cswap", 3, 0, _cswap, "Fredkin")


def get(name: str) -> GateSpec:
    try:
        return GATES[name.lower()]
    except KeyError as exc:  # pragma: no cover - message path
        raise KeyError(f"unknown gate '{name}'. Known gates: {', '.join(sorted(GATES))}") from exc

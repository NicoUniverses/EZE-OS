"""Stabilizer (Clifford) simulator for EZE OS.

Circuits built only from Clifford gates (H, S, CX, CZ, SWAP, iSWAP, ECR, ...)
can be simulated in polynomial time with the tableau method of Aaronson and
Gottesman ("Improved simulation of stabilizer circuits", Phys. Rev. A 70,
052328, 2004, arXiv:quant-ph/0406196). The state of ``n`` qubits is stored as
``n`` destabilizer and ``n`` stabilizer generators instead of ``2**n``
amplitudes, so GHZ states, surface-code patches and randomized-benchmarking
sequences with hundreds or thousands of qubits run on a laptop.

Gate rules are not typed in by hand. For every gate, the module conjugates the
Pauli generators X_j and Z_j with the exact unitary from :mod:`ezeos.gates`
and decomposes the result back into a signed Pauli string. A gate (with its
parameters) is accepted only if every image is a single Pauli, so the rules
are checked against the exact unitary by construction and any parameterised
gate at a Clifford angle (``rz(pi/2)``, ``rxx(pi/2)``, ``gpi2(0)``, ``u`` after
transpilation, ...) is supported automatically.

Pauli convention: a row is ``i**r * X**x * Z**z`` where ``x`` and ``z`` are
bit masks (bit ``q`` = qubit ``q``, the same little-endian order as
:class:`ezeos.simulator.StateVector`) and the X factor is written to the left
of the Z factor on each qubit. With this convention Y = i X Z.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from . import gates as G
from .circuit import Circuit
from .simulator import NoiseModel, Result, StateVector

Pauli = Tuple[int, int, int]  # (phase r mod 4, x mask, z mask)

_TOL = 1e-9
_PHASES = (1 + 0j, 1j, -1 + 0j, -1j)


class NotCliffordError(ValueError):
    """Raised when a gate (with its parameters) is not a Clifford operation."""


def _popcount(v: int) -> int:
    return bin(v).count("1")


def pauli_mul(a: Pauli, b: Pauli) -> Pauli:
    """Product ``a * b`` of two Pauli operators in the ``i**r X**x Z**z`` form.

    Moving ``Z**z1`` to the right past ``X**x2`` gives a factor ``(-1)**|z1 & x2|``.
    """
    ra, xa, za = a
    rb, xb, zb = b
    r = (ra + rb + 2 * (_popcount(za & xb) & 1)) & 3
    return (r, xa ^ xb, za ^ zb)


def pauli_from_string(label: str) -> Pauli:
    """Parse ``"+XZI"``, ``"-iYY"`` or ``"ZZ"`` (leftmost character = highest qubit)."""
    s = label.strip()
    r = 0
    if s.startswith("+"):
        s = s[1:]
    elif s.startswith("-"):
        r, s = 2, s[1:]
    if s.startswith("i"):
        r, s = (r + 1) & 3, s[1:]
    x = z = 0
    for q, ch in enumerate(reversed(s.upper())):
        if ch == "I":
            continue
        if ch == "X":
            x |= 1 << q
        elif ch == "Z":
            z |= 1 << q
        elif ch == "Y":          # Y = i X Z
            x |= 1 << q
            z |= 1 << q
            r = (r + 1) & 3
        else:
            raise ValueError(f"invalid Pauli character {ch!r} in {label!r}")
    return (r, x, z)


def pauli_to_string(p: Pauli, n: int) -> str:
    """Inverse of :func:`pauli_from_string` (Y is written explicitly)."""
    r, x, z = p
    chars = []
    for q in range(n):
        xb, zb = (x >> q) & 1, (z >> q) & 1
        if xb and zb:
            chars.append("Y")
            r = (r - 1) & 3
        else:
            chars.append("X" if xb else "Z" if zb else "I")
    sign = ("+", "+i", "-", "-i")[r]
    return sign + "".join(reversed(chars))


# ----------------------------------------------------------------------
# Clifford rules derived from exact unitaries
# ----------------------------------------------------------------------
def _local_pauli_coeff(m: G.Matrix, x: int, z: int) -> complex:
    """``tr((X**x Z**z)^dagger m) / d`` using ``(X**x Z**z)|b> = (-1)**|z&b| |b^x>``."""
    d = len(m)
    total = 0j
    for b in range(d):
        sign = -1 if _popcount(z & b) & 1 else 1
        total += sign * m[b ^ x][b]
    return total / d


def _local_pauli_matrix(x: int, z: int, d: int) -> G.Matrix:
    m = [[0j] * d for _ in range(d)]
    for b in range(d):
        m[b ^ x][b] = -1 + 0j if _popcount(z & b) & 1 else 1 + 0j
    return m


def _decompose_pauli(m: G.Matrix) -> Optional[Pauli]:
    """Return ``(r, x, z)`` with ``m == i**r X**x Z**z``, or ``None``."""
    d = len(m)
    for x in range(d):
        for z in range(d):
            c = _local_pauli_coeff(m, x, z)
            if abs(c) < 0.5:
                continue
            for r, ph in enumerate(_PHASES):
                if abs(c - ph) < 1e-7:
                    return (r, x, z)
            return None
    return None


@dataclass(frozen=True)
class CliffordRule:
    """Images of the local generators under conjugation by a gate.

    ``images[2*j]`` is ``U X_j U^dagger`` and ``images[2*j + 1]`` is
    ``U Z_j U^dagger``, both as local Paulis on the gate's ``k`` operands.
    """

    name: str
    params: Tuple[float, ...]
    num_qubits: int
    images: Tuple[Pauli, ...]


_RULE_CACHE: Dict[Tuple[str, Tuple[float, ...]], CliffordRule] = {}


def clifford_rule(name: str, params: Sequence[float] = ()) -> CliffordRule:
    """Derive (and cache) the conjugation rule of a gate from its exact unitary."""
    key = (name.lower(), tuple(round(float(p), 12) for p in params))
    rule = _RULE_CACHE.get(key)
    if rule is not None:
        return rule
    spec = G.get(key[0])
    u = spec.unitary(tuple(float(p) for p in params))
    if not G.is_unitary(u):
        raise NotCliffordError(f"{name} is not unitary")
    k = spec.num_qubits
    d = 1 << k
    ud = G.dagger(u)
    images: List[Pauli] = []
    for j in range(k):
        for gen in (_local_pauli_matrix(1 << j, 0, d), _local_pauli_matrix(0, 1 << j, d)):
            img = _decompose_pauli(G.matmul(u, G.matmul(gen, ud)))
            if img is None:
                raise NotCliffordError(f"{name}{tuple(params)} is not a Clifford gate")
            images.append(img)
    rule = CliffordRule(key[0], key[1], k, tuple(images))
    _RULE_CACHE[key] = rule
    return rule


def is_clifford_gate(name: str, params: Sequence[float] = ()) -> bool:
    try:
        clifford_rule(name, params)
        return True
    except NotCliffordError:
        return False


def is_clifford(circuit: Circuit) -> bool:
    """True if every gate of ``circuit`` is Clifford (measure/reset/barrier are allowed)."""
    return all(not ins.is_gate or is_clifford_gate(ins.name, ins.params) for ins in circuit)


def _spread(local: int, qubits: Sequence[int]) -> int:
    out = 0
    for j, q in enumerate(qubits):
        if (local >> j) & 1:
            out |= 1 << q
    return out


# ----------------------------------------------------------------------
# Tableau state
# ----------------------------------------------------------------------
class StabilizerState:
    """Stabilizer tableau of ``n`` qubits, initialised to ``|0...0>``.

    Rows ``0 .. n-1`` are destabilizers (initially X_q), rows ``n .. 2n-1``
    are stabilizers (initially Z_q). Each row is a :data:`Pauli` triple.
    """

    def __init__(self, num_qubits: int):
        if num_qubits < 1:
            raise ValueError("a stabilizer state needs at least one qubit")
        self.n = num_qubits
        self.rows: List[Pauli] = [(0, 1 << q, 0) for q in range(num_qubits)]
        self.rows += [(0, 0, 1 << q) for q in range(num_qubits)]

    def copy(self) -> "StabilizerState":
        other = StabilizerState.__new__(StabilizerState)
        other.n = self.n
        other.rows = list(self.rows)
        return other

    # ------------------------------------------------------------------
    def apply(self, name: str, qubits: Sequence[int], params: Sequence[float] = ()) -> None:
        """Conjugate every generator by the gate ``name`` acting on ``qubits``."""
        rule = clifford_rule(name, params)
        if len(qubits) != rule.num_qubits:
            raise ValueError(f"{name} acts on {rule.num_qubits} qubit(s)")
        for q in qubits:
            if not 0 <= q < self.n:
                raise ValueError(f"qubit {q} out of range")
        mask = 0
        for q in qubits:
            mask |= 1 << q
        imgs = [(r, _spread(x, qubits), _spread(z, qubits)) for r, x, z in rule.images]
        rows = self.rows
        for i, (r, x, z) in enumerate(rows):
            if not ((x | z) & mask):
                continue
            acc: Pauli = (r, x & ~mask, z & ~mask)
            for j, q in enumerate(qubits):
                if (x >> q) & 1:
                    acc = pauli_mul(acc, imgs[2 * j])
                if (z >> q) & 1:
                    acc = pauli_mul(acc, imgs[2 * j + 1])
            rows[i] = acc

    def apply_pauli(self, label: str, qubit: int) -> None:
        """Apply X, Y or Z to one qubit (used for Pauli noise): flips anticommuting signs."""
        ch = label.upper()
        bit = 1 << qubit
        for i, (r, x, z) in enumerate(self.rows):
            anti = ((x & bit) and ch in "ZY") ^ ((z & bit) and ch in "XY")
            if anti:
                self.rows[i] = ((r + 2) & 3, x, z)

    # ------------------------------------------------------------------
    def measure(self, qubit: int, rng: random.Random) -> int:
        """Measure Z on ``qubit``, collapse the tableau and return 0 or 1."""
        n, rows, bit = self.n, self.rows, 1 << qubit
        p = next((i for i in range(n, 2 * n) if rows[i][1] & bit), None)
        if p is not None:
            pivot = rows[p]
            for i in range(2 * n):
                if i != p and rows[i][1] & bit:
                    rows[i] = pauli_mul(rows[i], pivot)
            outcome = rng.randrange(2)
            rows[p - n] = pivot
            rows[p] = (2 * outcome, 0, bit)
            return outcome
        acc: Pauli = (0, 0, 0)
        for i in range(n):
            if rows[i][1] & bit:
                acc = pauli_mul(acc, rows[i + n])
        return 1 if acc[0] == 2 else 0

    def is_deterministic(self, qubit: int) -> bool:
        bit = 1 << qubit
        return not any(self.rows[i][1] & bit for i in range(self.n, 2 * self.n))

    def reset(self, qubit: int, rng: random.Random) -> None:
        if self.measure(qubit, rng):
            self.apply("x", [qubit])

    # ------------------------------------------------------------------
    def stabilizers(self) -> List[str]:
        return [pauli_to_string(self.rows[i], self.n) for i in range(self.n, 2 * self.n)]

    def destabilizers(self) -> List[str]:
        return [pauli_to_string(self.rows[i], self.n) for i in range(self.n)]

    def expectation_pauli(self, label: str) -> float:
        """``<P>`` for a Hermitian Pauli string: +1, -1 or 0."""
        target = pauli_from_string(label)
        if len(label.lstrip("+-i")) != self.n:
            raise ValueError("Pauli string length must equal the number of qubits")
        r, x, z = target
        n, rows = self.n, self.rows
        # P commutes with every stabilizer iff it is (up to sign) in the group.
        for i in range(n, 2 * n):
            _, sx, sz = rows[i]
            if (_popcount(x & sz) + _popcount(z & sx)) & 1:
                return 0.0
        acc: Pauli = (0, 0, 0)
        for i in range(n):
            _, dx, dz = rows[i]
            if (_popcount(x & dz) + _popcount(z & dx)) & 1:
                acc = pauli_mul(acc, rows[i + n])
        if acc[1] != x or acc[2] != z:
            raise RuntimeError("inconsistent tableau")
        diff = (r - acc[0]) & 3
        if diff == 0:
            return 1.0
        if diff == 2:
            return -1.0
        raise ValueError(f"{label} is not Hermitian")

    def to_statevector(self) -> StateVector:
        """Dense amplitudes (global phase fixed by the projection). Limited to 16 qubits."""
        if self.n > 16:
            raise ValueError("to_statevector is limited to 16 qubits")
        dim = 1 << self.n
        stabs = self.rows[self.n:]
        for seed in range(dim):
            amps = [0j] * dim
            amps[seed] = 1 + 0j
            for r, x, z in stabs:   # apply (I + S) / 2 for every generator
                ph = _PHASES[r]
                new = list(amps)
                for b, a in enumerate(amps):
                    if a == 0:
                        continue
                    sign = -1 if _popcount(z & b) & 1 else 1
                    new[b ^ x] += ph * sign * a
                amps = [v / 2 for v in new]
            if sum(abs(a) ** 2 for a in amps) > 1e-12:
                return StateVector(self.n, amps)
        raise RuntimeError("empty stabilizer projection")  # pragma: no cover

    def __repr__(self) -> str:
        shown = ", ".join(self.stabilizers()[:6])
        return f"StabilizerState(n={self.n}, stabilizers=[{shown}{', ...' if self.n > 6 else ''}])"


# ----------------------------------------------------------------------
# Simulator
# ----------------------------------------------------------------------
class StabilizerSimulator:
    """Runs Clifford circuits with measurements, resets and Pauli noise.

    The :class:`ezeos.simulator.NoiseModel` is honoured exactly as in the
    state-vector simulator: depolarizing noise is a random Pauli after each
    gate (still Clifford) and readout noise flips the recorded bit.
    """

    name = "ezeos.stabilizer"

    def __init__(self, seed: Optional[int] = None, noise: Optional[NoiseModel] = None,
                 max_qubits: int = 5000):
        self.seed = seed
        self.noise = noise or NoiseModel()
        self.max_qubits = max_qubits

    def _check(self, circuit: Circuit) -> None:
        if circuit.num_qubits > self.max_qubits:
            raise ValueError(f"stabilizer simulator limited to {self.max_qubits} qubits")
        for ins in circuit:
            if ins.is_gate and not is_clifford_gate(ins.name, ins.params):
                raise NotCliffordError(f"{ins!r} is not Clifford; use ezeos.Simulator instead")

    def state(self, circuit: Circuit) -> StabilizerState:
        """Final tableau of a circuit without measurements (noise is ignored)."""
        self._check(circuit)
        st = StabilizerState(circuit.num_qubits)
        rng = random.Random(self.seed)
        for ins in circuit:
            if ins.name == "barrier":
                continue
            if ins.name == "measure":
                raise ValueError("state() requires a circuit without measurements")
            if ins.name == "reset":
                st.reset(ins.qubits[0], rng)
                continue
            st.apply(ins.name, ins.qubits, ins.params)
        return st

    def _readout(self, bit: int, rng: random.Random) -> int:
        if self.noise.readout and rng.random() < self.noise.readout:
            return 1 - bit
        return bit

    def _gate(self, st: StabilizerState, ins, rng: random.Random) -> None:
        st.apply(ins.name, ins.qubits, ins.params)
        p = self.noise.p1 if len(ins.qubits) == 1 else self.noise.p2
        if p:
            for q in ins.qubits:
                if rng.random() < p:
                    st.apply_pauli(rng.choice("XYZ"), q)

    def run(self, circuit: Circuit, shots: int = 1024) -> Result:
        self._check(circuit)
        rng = random.Random(self.seed)
        nc = circuit.num_clbits
        measured = circuit.has_measurements()
        ideal = self.noise.p1 == 0 and self.noise.p2 == 0
        prefix: Optional[StabilizerState] = None
        start = 0
        if ideal:   # evolve the measurement-free prefix once, reuse it for every shot
            prefix = StabilizerState(circuit.num_qubits)
            for start, ins in enumerate(circuit.instructions):
                if not ins.is_gate:
                    if ins.name != "barrier":
                        break
                    continue
                prefix.apply(ins.name, ins.qubits, ins.params)
            else:
                start = len(circuit.instructions)
        counts: Dict[str, int] = {}
        for _ in range(shots):
            st = prefix.copy() if prefix is not None else StabilizerState(circuit.num_qubits)
            cbits = [0] * nc
            for ins in circuit.instructions[start:]:
                if ins.name == "barrier":
                    continue
                if ins.name == "measure":
                    cbits[ins.clbits[0]] = self._readout(st.measure(ins.qubits[0], rng), rng)
                elif ins.name == "reset":
                    st.reset(ins.qubits[0], rng)
                else:
                    self._gate(st, ins, rng)
            if not measured:
                for q in range(min(nc, circuit.num_qubits)):
                    cbits[q] = self._readout(st.measure(q, rng), rng)
            key = "".join(str(b) for b in reversed(cbits))
            counts[key] = counts.get(key, 0) + 1
        return Result(counts, shots, circuit.num_qubits, self.name, None, {"method": "stabilizer"})


def random_clifford_circuit(num_qubits: int, depth: int, rng: random.Random,
                            gates: Sequence[str] = ("h", "s", "sdg", "x", "y", "z", "sx", "cx", "cz", "swap")
                            ) -> Circuit:
    """Random circuit over Clifford gates, used for benchmarking and tests."""
    c = Circuit(num_qubits, name=f"rand_clifford{num_qubits}x{depth}")
    two = [g for g in gates if G.get(g).num_qubits == 2]
    one = [g for g in gates if G.get(g).num_qubits == 1]
    for _ in range(depth):
        if num_qubits > 1 and two and rng.random() < 0.4:
            a, b = rng.sample(range(num_qubits), 2)
            c.append(rng.choice(two), [a, b])
        else:
            c.append(rng.choice(one), [rng.randrange(num_qubits)])
    return c


def run(circuit: Circuit, shots: int = 1024, seed: Optional[int] = None,
        noise: Optional[NoiseModel] = None) -> Result:
    """Convenience: run a Clifford circuit on the stabilizer simulator."""
    return StabilizerSimulator(seed=seed, noise=noise).run(circuit, shots)

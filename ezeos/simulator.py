"""State-vector simulator for EZE OS.

Pure Python, no dependencies. Practical up to roughly 18-20 qubits. Supports
mid-circuit measurement, reset, a seeded random generator and an optional
depolarizing noise model so results look like a real device.
"""
from __future__ import annotations

import cmath
import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from . import gates as G
from .circuit import Circuit, Instruction


class StateVector:
    """A pure quantum state on ``n`` qubits."""

    def __init__(self, num_qubits: int, amplitudes: Optional[Sequence[complex]] = None):
        self.n = num_qubits
        dim = 1 << num_qubits
        if amplitudes is None:
            self.amp: List[complex] = [0j] * dim
            self.amp[0] = 1 + 0j
        else:
            if len(amplitudes) != dim:
                raise ValueError("amplitude vector has the wrong length")
            self.amp = [complex(a) for a in amplitudes]
            self.normalize()

    # ------------------------------------------------------------------
    def copy(self) -> "StateVector":
        return StateVector(self.n, list(self.amp))

    def normalize(self) -> None:
        norm = math.sqrt(sum(abs(a) ** 2 for a in self.amp))
        if norm == 0:
            raise ValueError("zero state vector")
        self.amp = [a / norm for a in self.amp]

    def probabilities(self) -> List[float]:
        return [abs(a) ** 2 for a in self.amp]

    def probability_of(self, bitstring: str) -> float:
        return abs(self.amp[int(bitstring, 2)]) ** 2

    def expectation_z(self, qubit: int) -> float:
        bit = 1 << qubit
        return sum((-1 if i & bit else 1) * abs(a) ** 2 for i, a in enumerate(self.amp))

    def expectation_pauli(self, pauli: str) -> float:
        """Expectation value of a Pauli string such as ``"ZZI"`` (leftmost = highest qubit)."""
        if len(pauli) != self.n:
            raise ValueError("Pauli string length must equal the number of qubits")
        psi = self.copy()
        for k, ch in enumerate(reversed(pauli.upper())):
            if ch == "I":
                continue
            psi.apply_matrix(G.get(ch.lower()).unitary(), [k])
        return sum((a.conjugate() * b).real for a, b in zip(self.amp, psi.amp))

    def fidelity(self, other: "StateVector") -> float:
        ov = sum(a.conjugate() * b for a, b in zip(self.amp, other.amp))
        return abs(ov) ** 2

    def bloch(self, qubit: int) -> Tuple[float, float, float]:
        """Bloch vector (x, y, z) of the reduced state of one qubit."""
        bit = 1 << qubit
        rho00 = rho11 = 0.0
        rho01 = 0j
        for i, a in enumerate(self.amp):
            if i & bit:
                continue
            b = self.amp[i | bit]
            rho00 += abs(a) ** 2
            rho11 += abs(b) ** 2
            rho01 += a * b.conjugate()
        return (2 * rho01.real, -2 * rho01.imag, rho00 - rho11)

    # ------------------------------------------------------------------
    def apply_matrix(self, m: G.Matrix, qubits: Sequence[int]) -> None:
        k = len(qubits)
        if k == 1:
            self._apply1(m, qubits[0])
            return
        if k == 2:
            self._apply2(m, qubits[0], qubits[1])
            return
        self._apply_k(m, list(qubits))

    def _apply1(self, m: G.Matrix, q: int) -> None:
        bit = 1 << q
        a = self.amp
        m00, m01 = m[0]
        m10, m11 = m[1]
        for i in range(len(a)):
            if i & bit:
                continue
            j = i | bit
            x, y = a[i], a[j]
            a[i] = m00 * x + m01 * y
            a[j] = m10 * x + m11 * y

    def _apply2(self, m: G.Matrix, q0: int, q1: int) -> None:
        b0, b1 = 1 << q0, 1 << q1
        a = self.amp
        for i in range(len(a)):
            if i & b0 or i & b1:
                continue
            idx = (i, i | b0, i | b1, i | b0 | b1)
            v = [a[t] for t in idx]
            for r in range(4):
                row = m[r]
                a[idx[r]] = row[0] * v[0] + row[1] * v[1] + row[2] * v[2] + row[3] * v[3]

    def _apply_k(self, m: G.Matrix, qubits: List[int]) -> None:
        k = len(qubits)
        bits = [1 << q for q in qubits]
        mask = sum(bits)
        a = self.amp
        for base in range(len(a)):
            if base & mask:
                continue
            idx = []
            for local in range(1 << k):
                i = base
                for p in range(k):
                    if local >> p & 1:
                        i |= bits[p]
                idx.append(i)
            v = [a[t] for t in idx]
            for r in range(1 << k):
                row = m[r]
                a[idx[r]] = sum(row[c] * v[c] for c in range(1 << k))

    def measure(self, qubit: int, rng: random.Random) -> int:
        bit = 1 << qubit
        p1 = sum(abs(a) ** 2 for i, a in enumerate(self.amp) if i & bit)
        outcome = 1 if rng.random() < p1 else 0
        keep = p1 if outcome else 1 - p1
        norm = math.sqrt(keep) if keep > 0 else 1.0
        for i in range(len(self.amp)):
            if bool(i & bit) != bool(outcome):
                self.amp[i] = 0j
            else:
                self.amp[i] /= norm
        return outcome

    def reset(self, qubit: int, rng: random.Random) -> None:
        if self.measure(qubit, rng):
            self._apply1(G.get("x").unitary(), qubit)

    def __repr__(self) -> str:
        terms = []
        for i, a in enumerate(self.amp):
            if abs(a) > 1e-6:
                terms.append(f"({a.real:+.3f}{a.imag:+.3f}j)|{i:0{self.n}b}>")
        return " ".join(terms[:16]) + (" ..." if len(terms) > 16 else "")


@dataclass
class NoiseModel:
    """Simple depolarizing + readout noise model.

    ``p1``/``p2`` are depolarizing probabilities after 1- and 2-qubit gates;
    ``readout`` is the probability that a measured bit is flipped.
    """

    p1: float = 0.0
    p2: float = 0.0
    readout: float = 0.0

    @classmethod
    def from_device(cls, device) -> "NoiseModel":
        return cls(p1=1 - device.fidelity_1q, p2=1 - device.fidelity_2q, readout=1 - device.fidelity_readout)

    @property
    def is_ideal(self) -> bool:
        return self.p1 == 0 and self.p2 == 0 and self.readout == 0


@dataclass
class Result:
    counts: Dict[str, int]
    shots: int
    num_qubits: int
    backend: str = "ezeos.local"
    statevector: Optional[StateVector] = None
    metadata: Dict[str, object] = field(default_factory=dict)

    def probabilities(self) -> Dict[str, float]:
        return {k: v / self.shots for k, v in self.counts.items()}

    def most_likely(self) -> str:
        return max(self.counts.items(), key=lambda kv: kv[1])[0]

    def entropy(self) -> float:
        h = 0.0
        for p in self.probabilities().values():
            if p > 0:
                h -= p * math.log2(p)
        return h

    def expectation_z(self, qubit: int) -> float:
        total = 0
        for bits, c in self.counts.items():
            total += c * (-1 if bits[-1 - qubit] == "1" else 1)
        return total / self.shots

    def top(self, k: int = 8) -> List[Tuple[str, int]]:
        return sorted(self.counts.items(), key=lambda kv: -kv[1])[:k]

    def __repr__(self) -> str:
        top = ", ".join(f"{b}:{c}" for b, c in self.top(4))
        return f"Result(backend={self.backend!r}, shots={self.shots}, top=[{top}])"


_PAULIS = None


def _paulis():
    global _PAULIS
    if _PAULIS is None:
        _PAULIS = [G.get("x").unitary(), G.get("y").unitary(), G.get("z").unitary()]
    return _PAULIS


class Simulator:
    """Executes circuits on a state vector."""

    name = "ezeos.local"

    def __init__(self, seed: Optional[int] = None, noise: Optional[NoiseModel] = None, max_qubits: int = 22):
        self.seed = seed
        self.noise = noise or NoiseModel()
        self.max_qubits = max_qubits

    def statevector(self, circuit: Circuit) -> StateVector:
        """Final state of a circuit without measurements (noise is ignored)."""
        self._check(circuit)
        sv = StateVector(circuit.num_qubits)
        rng = random.Random(self.seed)
        for ins in circuit:
            if ins.name == "barrier":
                continue
            if ins.name == "measure":
                raise ValueError("statevector() requires a circuit without measurements")
            if ins.name == "reset":
                sv.reset(ins.qubits[0], rng)
                continue
            sv.apply_matrix(ins.unitary(), ins.qubits)
        return sv

    def run(self, circuit: Circuit, shots: int = 1024) -> Result:
        self._check(circuit)
        rng = random.Random(self.seed)
        meas_only_at_end = self._terminal_measurements(circuit)
        if meas_only_at_end and self.noise.p1 == 0 and self.noise.p2 == 0:
            return self._run_sampling(circuit, shots, rng)
        return self._run_trajectories(circuit, shots, rng)

    # ------------------------------------------------------------------
    def _check(self, circuit: Circuit) -> None:
        if circuit.num_qubits > self.max_qubits:
            raise ValueError(f"local simulator limited to {self.max_qubits} qubits")

    @staticmethod
    def _terminal_measurements(circuit: Circuit) -> bool:
        seen = set()
        for ins in circuit:
            if ins.name == "measure":
                seen.add(ins.qubits[0])
            elif ins.name == "reset" or (ins.is_gate and seen.intersection(ins.qubits)):
                return False
        return True

    def _readout(self, bit: int, rng: random.Random) -> int:
        if self.noise.readout and rng.random() < self.noise.readout:
            return 1 - bit
        return bit

    def _run_sampling(self, circuit: Circuit, shots: int, rng: random.Random) -> Result:
        sv = StateVector(circuit.num_qubits)
        measures: List[Tuple[int, int]] = []
        for ins in circuit:
            if ins.name == "barrier":
                continue
            if ins.name == "measure":
                measures.append((ins.qubits[0], ins.clbits[0]))
                continue
            sv.apply_matrix(ins.unitary(), ins.qubits)
        if not measures:
            measures = [(q, q) for q in range(circuit.num_qubits)]
        probs = sv.probabilities()
        cdf, acc = [], 0.0
        for p in probs:
            acc += p
            cdf.append(acc)
        counts: Dict[str, int] = {}
        nc = circuit.num_clbits
        for _ in range(shots):
            u = rng.random() * acc
            lo, hi = 0, len(cdf) - 1
            while lo < hi:
                mid = (lo + hi) // 2
                if cdf[mid] < u:
                    lo = mid + 1
                else:
                    hi = mid
            basis = lo
            cbits = [0] * nc
            for q, c in measures:
                cbits[c] = self._readout((basis >> q) & 1, rng)
            key = "".join(str(b) for b in reversed(cbits))
            counts[key] = counts.get(key, 0) + 1
        return Result(counts, shots, circuit.num_qubits, self.name, sv, {"method": "sampling"})

    def _run_trajectories(self, circuit: Circuit, shots: int, rng: random.Random) -> Result:
        counts: Dict[str, int] = {}
        nc = circuit.num_clbits
        has_meas = circuit.has_measurements()
        for _ in range(shots):
            sv = StateVector(circuit.num_qubits)
            cbits = [0] * nc
            for ins in circuit:
                if ins.name == "barrier":
                    continue
                if ins.name == "measure":
                    cbits[ins.clbits[0]] = self._readout(sv.measure(ins.qubits[0], rng), rng)
                    continue
                if ins.name == "reset":
                    sv.reset(ins.qubits[0], rng)
                    continue
                sv.apply_matrix(ins.unitary(), ins.qubits)
                p = self.noise.p1 if len(ins.qubits) == 1 else self.noise.p2
                if p:
                    for q in ins.qubits:
                        if rng.random() < p:
                            sv.apply_matrix(rng.choice(_paulis()), [q])
            if not has_meas:
                for q in range(min(nc, circuit.num_qubits)):
                    cbits[q] = self._readout(sv.measure(q, rng), rng)
            key = "".join(str(b) for b in reversed(cbits))
            counts[key] = counts.get(key, 0) + 1
        return Result(counts, shots, circuit.num_qubits, self.name, None, {"method": "trajectories"})


def circuit_unitary(circuit: Circuit) -> G.Matrix:
    """Unitary matrix of a measurement-free circuit, built column by column."""
    n = circuit.num_qubits
    if n > 10:
        raise ValueError("circuit_unitary is limited to 10 qubits")
    dim = 1 << n
    cols = []
    for basis in range(dim):
        amps = [0j] * dim
        amps[basis] = 1 + 0j
        sv = StateVector(n, amps)
        for ins in circuit:
            if ins.name == "barrier":
                continue
            if not ins.is_gate:
                raise ValueError("circuit_unitary requires a circuit without measure/reset")
            sv.apply_matrix(ins.unitary(), ins.qubits)
        cols.append(sv.amp)
    return [[cols[c][r] for c in range(dim)] for r in range(dim)]


def run(circuit: Circuit, shots: int = 1024, seed: Optional[int] = None,
        noise: Optional[NoiseModel] = None) -> Result:
    """Convenience: run a circuit on the local simulator."""
    return Simulator(seed=seed, noise=noise).run(circuit, shots)


def statevector(circuit: Circuit) -> StateVector:
    return Simulator().statevector(circuit)

"""Reference quantum algorithms, written against the EZE OS circuit API."""
from __future__ import annotations

import math
import random
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from ..circuit import Circuit
from ..simulator import Simulator, StateVector

PI = math.pi


def bell() -> Circuit:
    c = Circuit(2, name="bell")
    c.h(0).cx(0, 1).measure_all()
    return c


def ghz(n: int) -> Circuit:
    c = Circuit(n, name=f"ghz{n}")
    c.h(0)
    for q in range(n - 1):
        c.cx(q, q + 1)
    return c.measure_all()


def qft(n: int, swaps: bool = True, inverse: bool = False) -> Circuit:
    c = Circuit(n, name=f"{'i' if inverse else ''}qft{n}")
    for j in reversed(range(n)):
        c.h(j)
        for k in reversed(range(j)):
            c.cp(PI / 2 ** (j - k), k, j)
    if swaps:
        for q in range(n // 2):
            c.swap(q, n - 1 - q)
    return c.inverse() if inverse else c


def bernstein_vazirani(secret: str) -> Circuit:
    """Recover a hidden bit string with one oracle query."""
    n = len(secret)
    c = Circuit(n + 1, n, name=f"bv_{secret}")
    c.x(n).h(n)
    for q in range(n):
        c.h(q)
    for q, bit in enumerate(reversed(secret)):
        if bit == "1":
            c.cx(q, n)
    for q in range(n):
        c.h(q)
        c.measure(q, q)
    return c


def deutsch_jozsa(n: int, balanced: bool = True, seed: int = 7) -> Circuit:
    rng = random.Random(seed)
    c = Circuit(n + 1, n, name=f"dj{n}_{'bal' if balanced else 'const'}")
    c.x(n).h(n)
    for q in range(n):
        c.h(q)
    if balanced:
        for q in range(n):
            if rng.random() < 0.5 or q == 0:
                c.cx(q, n)
    for q in range(n):
        c.h(q)
        c.measure(q, q)
    return c


def grover(marked: str, iterations: Optional[int] = None) -> Circuit:
    """Grover search for a single marked bit string (2-6 qubits recommended)."""
    n = len(marked)
    k = iterations if iterations is not None else max(1, int(math.floor(PI / 4 * math.sqrt(2 ** n))))
    c = Circuit(n, name=f"grover_{marked}")
    for q in range(n):
        c.h(q)
    for _ in range(k):
        _phase_oracle(c, marked)
        _diffusion(c, n)
    return c.measure_all()


def _mcz(c: Circuit, n: int) -> None:
    """Multi-controlled Z on all n qubits (n <= 3 exact, larger via ancilla-free CCX ladder)."""
    if n == 1:
        c.z(0)
    elif n == 2:
        c.cz(0, 1)
    elif n == 3:
        c.h(2).ccx(0, 1, 2).h(2)
    else:
        # recursive decomposition with controlled phase gates (exact, O(2^n) gates)
        lam = PI
        _mcp(c, lam, list(range(n - 1)), n - 1)


def _mcp(c: Circuit, lam: float, controls: List[int], target: int) -> None:
    if len(controls) == 1:
        c.cp(lam, controls[0], target)
        return
    last = controls[-1]
    rest = controls[:-1]
    c.cp(lam / 2, last, target)
    _mcx(c, rest, last)
    c.cp(-lam / 2, last, target)
    _mcx(c, rest, last)
    _mcp(c, lam / 2, rest, target)


def _mcx(c: Circuit, controls: List[int], target: int) -> None:
    if len(controls) == 1:
        c.cx(controls[0], target)
    elif len(controls) == 2:
        c.ccx(controls[0], controls[1], target)
    else:
        c.h(target)
        _mcp(c, PI, controls, target)
        c.h(target)


def _phase_oracle(c: Circuit, marked: str) -> None:
    n = len(marked)
    flips = [q for q, b in enumerate(reversed(marked)) if b == "0"]
    for q in flips:
        c.x(q)
    _mcz(c, n)
    for q in flips:
        c.x(q)


def _diffusion(c: Circuit, n: int) -> None:
    for q in range(n):
        c.h(q).x(q)
    _mcz(c, n)
    for q in range(n):
        c.x(q).h(q)


def qaoa_maxcut(edges: Sequence[Tuple[int, int]], n: int, gammas: Sequence[float],
                betas: Sequence[float]) -> Circuit:
    c = Circuit(n, name="qaoa_maxcut")
    for q in range(n):
        c.h(q)
    for g, b in zip(gammas, betas):
        for a, bq in edges:
            c.rzz(2 * g, a, bq)
        for q in range(n):
            c.rx(2 * b, q)
    return c


def maxcut_value(bits: str, edges: Sequence[Tuple[int, int]]) -> int:
    x = [int(b) for b in reversed(bits)]
    return sum(1 for a, b in edges if x[a] != x[b])


def solve_maxcut(edges: Sequence[Tuple[int, int]], n: int, layers: int = 1, grid: int = 12,
                 shots: int = 512, seed: int = 11) -> Dict[str, object]:
    """Grid-search QAOA parameters on the simulator and return the best cut found."""
    sim = Simulator(seed=seed)
    best = {"value": -1.0}
    for i in range(grid):
        for j in range(grid):
            g, b = PI * i / grid, PI / 2 * j / grid
            circ = qaoa_maxcut(edges, n, [g] * layers, [b] * layers)
            sv = sim.statevector(circ)
            exp = sum(p * maxcut_value(format(k, f"0{n}b"), edges) for k, p in enumerate(sv.probabilities()))
            if exp > best["value"]:
                best = {"value": exp, "gamma": g, "beta": b}
    circ = qaoa_maxcut(edges, n, [best["gamma"]] * layers, [best["beta"]] * layers).measure_all()
    res = sim.run(circ, shots)
    top = max(res.counts, key=lambda k: (maxcut_value(k, edges), res.counts[k]))
    best.update({"bitstring": top, "cut": maxcut_value(top, edges), "counts": res.counts})
    return best


def phase_estimation(phase: float, precision: int = 4) -> Circuit:
    """Estimate the eigenphase of P(2*pi*phase) on |1> with ``precision`` counting qubits."""
    n = precision
    c = Circuit(n + 1, n, name=f"qpe_{phase:.3f}")
    c.x(n)
    for q in range(n):
        c.h(q)
    for q in range(n):
        c.cp(2 * PI * phase * (2 ** q), q, n)
    iq = qft(n, inverse=True)
    c.extend(iq, list(range(n)))
    for q in range(n):
        c.measure(q, q)
    return c


def random_number(bits: int = 8, seed: Optional[int] = None) -> int:
    """Quantum random number from Hadamard + measurement (simulated)."""
    c = Circuit(bits, name="qrng")
    for q in range(bits):
        c.h(q)
    res = Simulator(seed=seed).run(c.measure_all(), shots=1)
    return int(next(iter(res.counts)), 2)


def vqe_h2_like(theta_grid: int = 64) -> Dict[str, float]:
    """Toy VQE: minimise <H> for H = 0.2*ZZ + 0.6*XX - 0.4*(Z0 + Z1) with a 1-parameter ansatz.

    The ansatz RY(theta)-CX spans cos|00> + sin|11>, so E(theta) = 0.2 + 0.6 sin(theta) - 0.8 cos(theta)
    and the exact minimum is -0.8.
    """
    best = (float("inf"), 0.0)
    for k in range(theta_grid):
        th = 2 * PI * k / theta_grid
        c = Circuit(2, name="ansatz")
        c.ry(th, 0).cx(0, 1)
        sv = Simulator().statevector(c)
        e = 0.2 * sv.expectation_pauli("ZZ") + 0.6 * sv.expectation_pauli("XX") \
            - 0.4 * (sv.expectation_pauli("IZ") + sv.expectation_pauli("ZI"))
        if e < best[0]:
            best = (e, th)
    return {"energy": best[0], "theta": best[1]}


ALGORITHMS: Dict[str, Callable[..., Circuit]] = {
    "bell": bell,
    "ghz": ghz,
    "qft": qft,
    "bernstein_vazirani": bernstein_vazirani,
    "deutsch_jozsa": deutsch_jozsa,
    "grover": grover,
    "phase_estimation": phase_estimation,
}

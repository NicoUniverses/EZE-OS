"""QUBO / Ising problems for quantum annealers (D-Wave Advantage2).

EZE OS builds the problem, solves small instances exactly or with simulated
annealing on the CPU, and can hand the same model to D-Wave's Ocean SDK.
"""
from __future__ import annotations

import itertools
import math
import random
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

Var = int


@dataclass
class QUBO:
    """Minimise sum_i a_i x_i + sum_{i<j} b_ij x_i x_j + offset over x in {0,1}^n."""

    linear: Dict[Var, float] = field(default_factory=dict)
    quadratic: Dict[Tuple[Var, Var], float] = field(default_factory=dict)
    offset: float = 0.0

    def add(self, i: Var, j: Optional[Var] = None, w: float = 1.0) -> "QUBO":
        if j is None or i == j:
            self.linear[i] = self.linear.get(i, 0.0) + w
        else:
            key = (min(i, j), max(i, j))
            self.quadratic[key] = self.quadratic.get(key, 0.0) + w
        return self

    @property
    def variables(self) -> List[Var]:
        vs = set(self.linear)
        for a, b in self.quadratic:
            vs.update((a, b))
        return sorted(vs)

    def energy(self, x: Dict[Var, int]) -> float:
        e = self.offset
        for i, a in self.linear.items():
            e += a * x.get(i, 0)
        for (i, j), b in self.quadratic.items():
            e += b * x.get(i, 0) * x.get(j, 0)
        return e

    def brute_force(self) -> Tuple[Dict[Var, int], float]:
        vs = self.variables
        if len(vs) > 22:
            raise ValueError("brute force limited to 22 variables")
        best, best_e = None, math.inf
        for bits in itertools.product((0, 1), repeat=len(vs)):
            x = dict(zip(vs, bits))
            e = self.energy(x)
            if e < best_e:
                best, best_e = x, e
        return best, best_e

    def simulated_annealing(self, sweeps: int = 2000, t0: float = 5.0, t1: float = 0.01,
                            seed: Optional[int] = None) -> Tuple[Dict[Var, int], float]:
        rng = random.Random(seed)
        vs = self.variables
        x = {v: rng.randint(0, 1) for v in vs}
        nb: Dict[Var, List[Tuple[Var, float]]] = {v: [] for v in vs}
        for (i, j), b in self.quadratic.items():
            nb[i].append((j, b))
            nb[j].append((i, b))
        e = self.energy(x)
        best, best_e = dict(x), e
        for s in range(sweeps):
            t = t0 * (t1 / t0) ** (s / max(1, sweeps - 1))
            order = list(vs)
            rng.shuffle(order)          # random sweep order avoids deterministic flip cycles
            for v in order:
                d = (1 - 2 * x[v]) * (self.linear.get(v, 0.0) + sum(b * x[u] for u, b in nb[v]))
                if d < 0 or rng.random() < math.exp(-d / t) * (0.5 if d == 0 else 1.0):
                    x[v] ^= 1
                    e += d
                    if e < best_e:
                        best, best_e = dict(x), e
        return best, best_e

    def to_ising(self) -> Tuple[Dict[Var, float], Dict[Tuple[Var, Var], float], float]:
        """x = (1 - s) / 2 mapping (s in {-1, +1}), as used by annealers."""
        h: Dict[Var, float] = {}
        J: Dict[Tuple[Var, Var], float] = {}
        off = self.offset
        for i, a in self.linear.items():
            h[i] = h.get(i, 0.0) - a / 2
            off += a / 2
        for (i, j), b in self.quadratic.items():
            J[(i, j)] = J.get((i, j), 0.0) + b / 4
            h[i] = h.get(i, 0.0) - b / 4
            h[j] = h.get(j, 0.0) - b / 4
            off += b / 4
        return h, J, off

    def to_dwave(self):
        """Return a dimod.BinaryQuadraticModel (requires dwave-ocean-sdk)."""
        from .backends.base import require

        dimod = require("dimod", "dwave-ocean-sdk")
        return dimod.BinaryQuadraticModel(self.linear, self.quadratic, self.offset, dimod.BINARY)


def maxcut_qubo(edges: Iterable[Tuple[int, int]]) -> QUBO:
    q = QUBO()
    for i, j in edges:
        q.add(i, w=-1)
        q.add(j, w=-1)
        q.add(i, j, w=2)
    return q


def portfolio_qubo(returns: List[float], risk: List[List[float]], budget: int,
                   risk_aversion: float = 0.5, penalty: float = 4.0) -> QUBO:
    """Pick exactly ``budget`` assets maximising return minus risk (Markowitz-style, binary).

    Illustrative model only; this is not investment advice.
    """
    n = len(returns)
    q = QUBO()
    for i in range(n):
        q.add(i, w=-returns[i] + risk_aversion * risk[i][i] + penalty * (1 - 2 * budget))
        for j in range(i + 1, n):
            q.add(i, j, w=2 * risk_aversion * risk[i][j] + 2 * penalty)
    q.offset = penalty * budget * budget
    return q


def solve_with_dwave(qubo: QUBO, num_reads: int = 100):  # pragma: no cover - needs hardware access
    from .backends.base import require

    system = require("dwave.system", "dwave-ocean-sdk")
    sampler = system.EmbeddingComposite(system.DWaveSampler())
    return sampler.sample(qubo.to_dwave(), num_reads=num_reads)

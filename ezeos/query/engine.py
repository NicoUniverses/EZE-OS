"""Quantum query engine: QQL statement + table rows -> quantum plan -> kernel -> rows.

Layering (top to bottom)::

    Doctrine DBAL (PHP)          fetches rows from MySQL / PostgreSQL / SQLite ...
    EZE OS Doctrine bridge (PHP) builds QQL, ships rows + query as JSON
    ezeos.query (this module)    parses QQL, plans a quantum algorithm per statement
    ezeos.kernel                 schedules the job on a device, keeps an audit log
    ezeos.transpile              compiles to the chip's native gates and wiring
    ezeos.backends               simulator or vendor hardware

Honesty notes
-------------
* SEARCH builds the Grover oracle from the WHERE clause, which the engine
  evaluates classically on the rows it received. On today's hardware this is a
  demonstration of the quantum workflow, not a speed-up over SQL.
* OPTIMIZE solves the same QUBO exactly on the CPU (when small) and reports the
  gap between the quantum answer and the true optimum.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence

from ..algorithms.library import _diffusion, _mcx, _phase_oracle
from ..annealing import QUBO
from ..circuit import Circuit
from ..devices import get as get_device
from ..kernel import Job, JobState, Kernel
from ..simulator import Simulator
from .qql import Query, evaluate, parse

MAX_SEARCH_QUBITS = 10      # 1024 rows
MAX_SAMPLE_QUBITS = 6       # 64 rows
MAX_QAOA_VARS = 10
MAX_EXACT_VARS = 20


class QueryError(RuntimeError):
    pass


@dataclass
class QueryResult:
    kind: str
    columns: List[str]
    rows: List[Dict[str, Any]]
    plan: Dict[str, Any] = field(default_factory=dict)
    stats: Dict[str, Any] = field(default_factory=dict)
    counts: Dict[str, int] = field(default_factory=dict)
    log: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["ok"] = True
        return d


# ----------------------------------------------------------------------------
def _run_on_kernel(circuit: Circuit, q: Query, device: str, shots: int, seed: Optional[int]):
    kernel = Kernel()
    options = {"seed": seed, "noisy": q.noisy}
    jid = kernel.submit(Job(circuit, shots=shots, device=device, backend="local", options=options))
    kernel.run_all()
    job = kernel.jobs[jid]
    log = [{"event": e.event, "detail": e.detail} for e in kernel.log]
    if job.state != JobState.DONE:
        raise QueryError(job.error or "quantum job failed")
    return job, log


def _rows_of(tables: Mapping[str, Sequence[Mapping[str, Any]]], name: str) -> List[Dict[str, Any]]:
    if name not in tables:
        raise QueryError(f"table '{name}' was not provided")
    return [dict(r) for r in tables[name]]


def _columns(rows: List[Dict[str, Any]], extra: Sequence[str]) -> List[str]:
    cols: List[str] = []
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    return cols + [c for c in extra if c not in cols]


# SEARCH -------------------------------------------------------------------------
def grover_search_circuit(marked: Sequence[int], n: int) -> Circuit:
    space = 2 ** n
    m = len(marked)
    theta = math.asin(math.sqrt(m / space))
    iterations = max(0, int(round(math.pi / (4 * theta) - 0.5)))
    c = Circuit(n, name="qql_search")
    for qb in range(n):
        c.h(qb)
    for _ in range(iterations):
        for idx in marked:
            _phase_oracle(c, format(idx, f"0{n}b"))
        _diffusion(c, n)
    c.metadata.update({"iterations": iterations, "theoretical_success": math.sin((2 * iterations + 1) * theta) ** 2})
    return c.measure_all()


def _search(q: Query, rows: List[Dict[str, Any]], device: str, shots: int, seed: Optional[int]) -> QueryResult:
    marked = [i for i, r in enumerate(rows) if evaluate(q.where, r, q.params)]
    cols = _columns(rows, ["_index", "_hits", "_probability"])
    plan: Dict[str, Any] = {"algorithm": "grover", "device": device, "rows": len(rows), "marked": len(marked)}
    if not rows or not marked:
        plan["note"] = "no row satisfies the condition; nothing to amplify"
        return QueryResult("SEARCH", cols, [], plan, {"success_probability": 0.0})
    n = max(1, math.ceil(math.log2(len(rows))))
    if n > MAX_SEARCH_QUBITS:
        raise QueryError(f"SEARCH supports up to {2 ** MAX_SEARCH_QUBITS} rows per query")
    circ = grover_search_circuit(marked, n)
    job, log = _run_on_kernel(circ, q, device, shots, seed)
    counts = job.result.counts
    hits = {int(b, 2): c for b, c in counts.items()}
    found = sorted((i for i in hits if i in set(marked)), key=lambda i: -hits[i])
    if q.limit is not None:
        found = found[: q.limit]
    out = [dict(rows[i], _index=i, _hits=hits[i], _probability=round(hits[i] / shots, 4)) for i in found]
    success = sum(hits.get(i, 0) for i in marked) / shots
    plan.update({"qubits": n, "search_space": 2 ** n, "iterations": circ.metadata["iterations"],
                 "theoretical_success": round(circ.metadata["theoretical_success"], 4),
                 "transpile": str(job.report)})
    stats = {"success_probability": round(success, 4), "uniform_baseline": round(len(marked) / 2 ** n, 4),
             "shots": shots}
    return QueryResult("SEARCH", cols, out, plan, stats, counts, log)


# OPTIMIZE ---------------------------------------------------------------------
def selection_qubo(gain: Sequence[float], cost: Sequence[float], weight: float, k: int) -> QUBO:
    """Pick exactly k items maximising sum(gain) - weight*sum(cost)."""
    n = len(gain)
    a = [-g + weight * c for g, c in zip(gain, cost)]
    penalty = 1.0 + sum(abs(x) for x in a)
    q = QUBO()
    for i in range(n):
        q.add(i, w=a[i] + penalty * (1 - 2 * k))
        for j in range(i + 1, n):
            q.add(i, j, w=2 * penalty)
    q.offset = penalty * k * k
    return q


def qaoa_circuit(qubo: QUBO, n: int, gamma: float, beta: float) -> Circuit:
    h, J, _ = qubo.to_ising()
    c = Circuit(n, name="qql_qaoa")
    for i in range(n):
        c.h(i)
    for (i, j), v in J.items():
        if v:
            c.rzz(2 * gamma * v, i, j)
    for i, v in h.items():
        if v:
            c.rz(2 * gamma * v, i)
    for i in range(n):
        c.rx(2 * beta, i)
    return c


def _bits_to_x(bits: str, n: int) -> Dict[int, int]:
    return {i: int(bits[-1 - i]) for i in range(n)}


def _optimize(q: Query, rows: List[Dict[str, Any]], device: str, shots: int, seed: Optional[int]) -> QueryResult:
    cand = [r for r in rows if evaluate(q.where, r, q.params)]
    k = int(q.pick or 0)
    if k <= 0 or k > len(cand):
        raise QueryError(f"cannot pick {k} rows out of {len(cand)} candidates")
    for r in cand:
        for col in (q.maximize, q.minimize):
            if col and col not in r:
                raise QueryError(f"unknown column '{col}'")
    gain = [float(r[q.maximize]) for r in cand]
    cost = [float(r[q.minimize]) if q.minimize else 0.0 for r in cand]
    n = len(cand)
    qubo = selection_qubo(gain, cost, q.weight if q.minimize else 0.0, k)
    plan: Dict[str, Any] = {"device": device, "candidates": n, "pick": k, "objective":
                            f"maximize {q.maximize}" + (f" - {q.weight:g}*{q.minimize}" if q.minimize else "")}
    exact = qubo.brute_force() if n <= MAX_EXACT_VARS else None
    dev = get_device(device)
    counts: Dict[str, int] = {}
    log: List[Dict[str, Any]] = []
    if not dev.gate_model or n > MAX_QAOA_VARS:
        x, e = qubo.simulated_annealing(sweeps=3000, seed=seed)
        plan.update({"algorithm": "qubo_annealing", "solver": "simulated annealing (D-Wave Ocean handoff available)"})
        chosen = x
    else:
        sim = Simulator()
        best = None
        grid = 10
        for gi in range(1, grid + 1):
            for bi in range(1, grid + 1):
                g, b = math.pi * gi / (grid * 2), math.pi * bi / (grid * 2)
                probs = sim.statevector(qaoa_circuit(qubo, n, g, b)).probabilities()
                exp_e = sum(p * qubo.energy(_bits_to_x(format(i, f"0{n}b"), n)) for i, p in enumerate(probs))
                if best is None or exp_e < best[0]:
                    best = (exp_e, g, b)
        circ = qaoa_circuit(qubo, n, best[1], best[2]).measure_all()
        job, log = _run_on_kernel(circ, q, device, shots, seed)
        counts = job.result.counts
        feasible = [(qubo.energy(_bits_to_x(bits, n)), bits) for bits in counts
                    if sum(int(c) for c in bits) == k]
        plan.update({"algorithm": "qaoa", "layers": 1, "gamma": round(best[1], 4), "beta": round(best[2], 4),
                     "qubits": n, "transpile": str(job.report),
                     "feasible_fraction": round(sum(counts[b] for _, b in feasible) / shots, 4)})
        if feasible:
            chosen = _bits_to_x(min(feasible)[1], n)
        else:
            chosen, _ = qubo.simulated_annealing(sweeps=3000, seed=seed)
            plan["fallback"] = "no feasible sample; simulated annealing used"
    picked = [i for i in range(n) if chosen.get(i, 0) == 1]
    value = sum(gain[i] for i in picked) - (q.weight if q.minimize else 0.0) * sum(cost[i] for i in picked)
    stats: Dict[str, Any] = {"objective_value": round(value, 6), "picked": len(picked)}
    if exact is not None:
        ex = [i for i in range(n) if exact[0].get(i, 0) == 1]
        best_val = sum(gain[i] for i in ex) - (q.weight if q.minimize else 0.0) * sum(cost[i] for i in ex)
        stats.update({"exact_optimum": round(best_val, 6), "optimality_gap": round(best_val - value, 6)})
    out = [dict(cand[i]) for i in picked]
    return QueryResult("OPTIMIZE", _columns(cand, []), out, plan, stats, counts, log)


# SAMPLE -------------------------------------------------------------------------
def _mcry(c: Circuit, theta: float, controls: List[int], target: int) -> None:
    if not controls:
        c.ry(theta, target)
        return
    c.ry(theta / 2, target)
    _mcx(c, controls, target)
    c.ry(-theta / 2, target)
    _mcx(c, controls, target)


def state_preparation(probs: Sequence[float], n: int) -> Circuit:
    """Prepare sum_i sqrt(p_i)|i> with a binary tree of (multi-)controlled RY rotations."""
    size = 2 ** n
    p = list(probs) + [0.0] * (size - len(probs))
    total = sum(p)
    if total <= 0:
        raise QueryError("all sampling weights are zero")
    p = [x / total for x in p]
    c = Circuit(n, name="qql_sample")

    def node(qb: int, prefix: int) -> None:
        # indices whose bits above qb equal `prefix`
        span = 2 ** qb
        base = prefix * 2 * span
        p0 = sum(p[base: base + span])
        p1 = sum(p[base + span: base + 2 * span])
        if p0 + p1 <= 0:
            return
        theta = 2 * math.acos(math.sqrt(min(1.0, p0 / (p0 + p1))))
        controls = list(range(qb + 1, n))
        zeros = [cq for cq in controls if not (prefix >> (cq - qb - 1)) & 1]
        for z in zeros:
            c.x(z)
        if abs(theta) > 1e-12:
            _mcry(c, theta, controls, qb)
        for z in zeros:
            c.x(z)
        if qb > 0:
            node(qb - 1, prefix * 2)
            node(qb - 1, prefix * 2 + 1)

    node(n - 1, 0)
    return c


def _sample(q: Query, rows: List[Dict[str, Any]], device: str, shots: int, seed: Optional[int]) -> QueryResult:
    cand = [r for r in rows if evaluate(q.where, r, q.params)]
    if not cand:
        raise QueryError("no rows to sample from")
    if q.weight_by not in cand[0]:
        raise QueryError(f"unknown column '{q.weight_by}'")
    w = [max(0.0, float(r[q.weight_by])) for r in cand]
    n = max(1, math.ceil(math.log2(len(cand))))
    if n > MAX_SAMPLE_QUBITS:
        raise QueryError(f"SAMPLE supports up to {2 ** MAX_SAMPLE_QUBITS} rows per query")
    circ = state_preparation(w, n).measure_all()
    samples = int(q.samples or shots)
    job, log = _run_on_kernel(circ, q, device, samples, seed)
    counts = job.result.counts
    total = sum(w)
    out = []
    for bits, cnt in sorted(counts.items(), key=lambda kv: -kv[1]):
        i = int(bits, 2)
        if i < len(cand):
            out.append(dict(cand[i], _count=cnt, _frequency=round(cnt / samples, 4),
                            _expected=round(w[i] / total, 4)))
    tvd = 0.5 * sum(abs(counts.get(format(i, f"0{n}b"), 0) / samples - w[i] / total) for i in range(len(cand)))
    plan = {"algorithm": "amplitude_encoding", "device": device, "qubits": n, "rows": len(cand),
            "transpile": str(job.report)}
    stats = {"samples": samples, "total_variation_distance": round(tvd, 4)}
    return QueryResult("SAMPLE", _columns(cand, ["_count", "_frequency", "_expected"]), out, plan, stats, counts, log)


# public API -------------------------------------------------------------------
def execute(qql: str, tables: Mapping[str, Sequence[Mapping[str, Any]]], params: Optional[Mapping[str, Any]] = None,
            device: Optional[str] = None, shots: Optional[int] = None, seed: Optional[int] = None) -> QueryResult:
    q = parse(qql, params)
    dev = q.device or device or "ezeos_sim"
    get_device(dev)  # validates the key
    n_shots = int(q.shots or shots or 1024)
    s = q.seed if q.seed is not None else seed
    rows = _rows_of(tables, q.table)
    if q.kind == "SEARCH":
        res = _search(q, rows, dev, n_shots, s)
    elif q.kind == "OPTIMIZE":
        res = _optimize(q, rows, dev, n_shots, s)
    else:
        res = _sample(q, rows, dev, n_shots, s)
    res.plan["qql"] = qql
    return res


def handle_request(request: Mapping[str, Any]) -> Dict[str, Any]:
    """JSON protocol used by the Doctrine bridge (and any other client)."""
    try:
        res = execute(request["qql"], request.get("tables", {}), request.get("params"),
                      request.get("device"), request.get("shots"), request.get("seed"))
        return res.to_dict()
    except Exception as exc:  # noqa: BLE001 - errors are returned to the client as data
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

import cmath
import math
import random

import pytest

from ezeos import Circuit, Simulator, algorithms as A, annealing, devices as D, gates as G, qasm
from ezeos.kernel import Job, JobState, Kernel
from ezeos.simulator import circuit_unitary
from ezeos.transpile import cancel, lower_to_cx, synth_1q, transpile, zyz_angles

PI = math.pi


def rand_u(rng):
    th, ph, la = rng.uniform(0, PI), rng.uniform(-PI, PI), rng.uniform(-PI, PI)
    return G.get("u").unitary((th, ph, la))


def unitary_of(seq, n=1):
    c = Circuit(n)
    for ins in seq:
        c.append(ins.name, ins.qubits, ins.params)
    return circuit_unitary(c)


# --------------------------------------------------------------------- gates
@pytest.mark.parametrize("name", sorted(G.GATES))
def test_every_gate_is_unitary(name):
    spec = G.GATES[name]
    params = [0.37 * (k + 1) for k in range(spec.num_params)]
    assert G.is_unitary(spec.unitary(params))


def test_zyz_roundtrip():
    rng = random.Random(1)
    for _ in range(200):
        u = rand_u(rng)
        th, ph, la, phase = zyz_angles(u)
        rec = G.matmul(G.get("rz").unitary((ph,)), G.matmul(G.get("ry").unitary((th,)), G.get("rz").unitary((la,))))
        assert G.equal_up_to_phase(u, rec)


@pytest.mark.parametrize("basis", [("u",), ("rz", "sx"), ("prx",), ("prx", "rz"), ("gpi2", "rz"),
                                   ("rx", "rz"), ("ry", "rz")])
def test_synth_1q_every_vendor_basis(basis):
    rng = random.Random(hash(basis) & 0xFFFF)
    for _ in range(60):
        u = rand_u(rng)
        seq = synth_1q(u, 0, basis)
        assert all(i.name in basis for i in seq), (basis, [i.name for i in seq])
        assert G.equal_up_to_phase(unitary_of(seq), u)


@pytest.mark.parametrize("gate,params", [("cz", ()), ("cy", ()), ("ch", ()), ("cp", (0.7,)), ("crz", (1.1,)),
                                         ("swap", ()), ("rzz", (0.4,)), ("rxx", (0.9,)), ("ryy", (-0.6,)),
                                         ("iswap", ()), ("ms", (0.3, -1.2))])
def test_two_qubit_lowering_rules(gate, params):
    c = Circuit(2)
    c.append(gate, [0, 1], params)
    low = lower_to_cx(c)
    assert {i.name for i in low} <= {"cx", "h", "s", "sdg", "t", "tdg", "rx", "ry", "rz", "p", "u"}
    assert G.equal_up_to_phase(circuit_unitary(low), circuit_unitary(c))


@pytest.mark.parametrize("gate", ["ccx", "cswap"])
def test_three_qubit_lowering_rules(gate):
    c = Circuit(3)
    c.append(gate, [0, 1, 2])
    assert G.equal_up_to_phase(circuit_unitary(lower_to_cx(c)), circuit_unitary(c))


# ----------------------------------------------------------------- simulator
def test_bell_state():
    res = Simulator(seed=4).run(A.bell(), 2000)
    assert set(res.counts) <= {"00", "11"}
    assert abs(res.counts.get("00", 0) / 2000 - 0.5) < 0.05


def test_ghz_entropy():
    res = Simulator(seed=5).run(A.ghz(5), 4000)
    assert set(res.counts) == {"00000", "11111"}
    assert abs(res.entropy() - 1.0) < 0.02


def test_bernstein_vazirani_recovers_secret():
    for secret in ("1", "101", "110010"):
        res = Simulator(seed=1).run(A.bernstein_vazirani(secret), 64)
        assert res.most_likely() == secret


def test_deutsch_jozsa():
    assert Simulator(seed=1).run(A.deutsch_jozsa(3, balanced=False), 64).most_likely() == "000"
    assert "000" not in Simulator(seed=1).run(A.deutsch_jozsa(3, balanced=True), 64).counts


@pytest.mark.parametrize("marked", ["11", "101", "0110"])
def test_grover_finds_marked(marked):
    res = Simulator(seed=2).run(A.grover(marked), 1000)
    assert res.most_likely() == marked
    assert res.counts[marked] / 1000 > 0.45


def test_qft_inverse_is_identity():
    c = A.qft(3)
    c.extend(A.qft(3, inverse=True))
    assert G.equal_up_to_phase(circuit_unitary(c), G.identity(8))


def test_phase_estimation():
    res = Simulator(seed=3).run(A.phase_estimation(0.375, 4), 256)
    # clbits only hold the counting register
    assert int(res.most_likely(), 2) == 6


def test_vqe_and_qaoa():
    assert abs(A.vqe_h2_like()["energy"] + 0.8) < 0.01
    sol = A.solve_maxcut([(0, 1), (1, 2), (2, 3), (3, 0)], 4, grid=8, shots=256)
    assert sol["cut"] == 4


def test_noise_changes_results():
    dev = D.get("spinq_gemini_mini")
    ideal = Simulator(seed=9).run(A.bell(), 2000)
    noisy = Simulator(seed=9, noise=__import__("ezeos").NoiseModel.from_device(dev)).run(A.bell(), 2000)
    assert set(ideal.counts) <= {"00", "11"}
    assert set(noisy.counts) - {"00", "11"}


# --------------------------------------------------------------------- qasm
def test_qasm_roundtrip():
    c = Circuit(3, name="rt")
    c.h(0).cx(0, 1).rz(PI / 3, 2).cp(0.25, 1, 2).u(0.1, 0.2, 0.3, 0)
    back = qasm.from_qasm2(qasm.to_qasm2(c))
    assert G.equal_up_to_phase(circuit_unitary(back), circuit_unitary(c))
    assert "OPENQASM 3" in qasm.to_qasm3(c)


def test_qasm_rejects_code_injection():
    with pytest.raises(Exception):
        qasm.from_qasm2('OPENQASM 2.0;\nqreg q[1];\nrz(__import__("os").system("x")) q[0];')


# ---------------------------------------------------------------- transpile
GATE_DEVICES = [d.key for d in D.unique() if d.gate_model]


def _random_circuit(rng, n, k):
    c = Circuit(n)
    for _ in range(k):
        g = rng.choice(["h", "t", "rx", "ry", "cx", "cz", "swap", "rzz", "ccx", "cp", "u"])
        if g in ("h", "t"):
            getattr(c, g)(rng.randrange(n))
        elif g in ("rx", "ry"):
            getattr(c, g)(rng.uniform(-3, 3), rng.randrange(n))
        elif g == "u":
            c.u(rng.uniform(0, 3), rng.uniform(-3, 3), rng.uniform(-3, 3), rng.randrange(n))
        elif g == "ccx" and n >= 3:
            a, b, t = rng.sample(range(n), 3)
            c.ccx(a, b, t)
        elif g in ("cx", "cz", "swap"):
            a, b = rng.sample(range(n), 2)
            getattr(c, g)(a, b)
        elif g in ("rzz", "cp"):
            a, b = rng.sample(range(n), 2)
            getattr(c, g)(rng.uniform(-3, 3), a, b)
    return c


def _logical_probs(native, report, n):
    used = sorted({q for i in native for q in i.qubits} | set(report.final_layout))
    idx = {p: k for k, p in enumerate(used)}
    red = Circuit(len(used))
    for i in native:
        red.append(i.name, [idx[q] for q in i.qubits], i.params)
    probs = Simulator().statevector(red).probabilities()
    fl = [idx[p] for p in report.final_layout]
    out = [0.0] * (1 << n)
    for b, p in enumerate(probs):
        out[sum(((b >> fl[q]) & 1) << q for q in range(n))] += p
    return out


@pytest.mark.parametrize("key", GATE_DEVICES)
def test_transpile_preserves_semantics_on_every_device(key):
    dev = D.get(key)
    rng = random.Random(key)
    n = min(3, dev.qubits)
    for _ in range(4):
        c = _random_circuit(rng, n, 12)
        native, rep = transpile(c, dev)
        assert {i.name for i in native} <= set(dev.native_gates), key
        ref = Simulator().statevector(c).probabilities()
        got = _logical_probs(native, rep, n)
        assert max(abs(a - b) for a, b in zip(ref, got)) < 1e-6


def test_routing_respects_coupling():
    dev = D.get("iqm_spark")      # star topology
    c = Circuit(4)
    c.cx(1, 2).cx(2, 3).cx(1, 3)
    native, _ = transpile(c, dev)
    for i in native:
        if len(i.qubits) == 2:
            assert dev.is_connected(*i.qubits)


def test_annealer_is_rejected_by_gate_transpiler():
    with pytest.raises(ValueError):
        transpile(A.bell(), D.get("dwave_advantage2"))


def test_cancel_removes_inverse_pairs():
    c = Circuit(2)
    c.cx(0, 1).cx(0, 1).h(0).h(0).rz(0.0, 1)
    assert len(cancel(c)) == 0


# ------------------------------------------------------------------- kernel
def test_kernel_priority_and_log():
    k = Kernel()
    low = k.submit(Job(A.ghz(3), shots=100, priority=9, device="ezeos_sim", options={"seed": 1}))
    high = k.submit(Job(A.bell(), shots=100, priority=0, device="rigetti_novera", options={"seed": 1}))
    done = k.run_all()
    assert [j.id for j in done] == [high, low]
    assert all(j.state == JobState.DONE for j in done)
    assert any(e.event == "transpiled" for e in k.log)


def test_kernel_reports_failure():
    k = Kernel()
    jid = k.submit(Job(A.ghz(12), device="spinq_gemini_mini"))
    k.run_all()
    assert k.jobs[jid].state == JobState.FAILED


def test_kernel_cancel():
    k = Kernel()
    jid = k.submit(Job(A.bell()))
    assert k.cancel(jid)
    assert k.run_all() == []


# ---------------------------------------------------------------- annealing
def test_maxcut_qubo_triangle_and_square():
    x, e = annealing.maxcut_qubo([(0, 1), (1, 2), (2, 0)]).brute_force()
    assert -e == 2
    x, e = annealing.maxcut_qubo([(0, 1), (1, 2), (2, 3), (3, 0)]).simulated_annealing(seed=3)
    assert -e == 4


def test_ising_conversion_preserves_energy():
    q = annealing.QUBO().add(0, w=1.5).add(1, w=-2).add(0, 1, w=3)
    q.offset = 0.25
    h, J, off = q.to_ising()
    for x0 in (0, 1):
        for x1 in (0, 1):
            s = {0: 1 - 2 * x0, 1: 1 - 2 * x1}
            ising = off + sum(h[i] * s[i] for i in h) + sum(v * s[a] * s[b] for (a, b), v in J.items())
            assert abs(ising - q.energy({0: x0, 1: x1})) < 1e-12


def test_portfolio_qubo_respects_budget():
    r = [0.10, 0.07, 0.12, 0.03]
    cov = [[0.05 if i == j else 0.01 for j in range(4)] for i in range(4)]
    x, _ = annealing.portfolio_qubo(r, cov, budget=2).brute_force()
    assert sum(x.values()) == 2


# ------------------------------------------------------------------ devices
def test_catalog_is_consistent():
    for d in D.unique():
        assert d.qubits >= 1 and d.vendor and d.model and d.source.startswith("https://")
        for a, b in d.coupling_map():
            assert 0 <= a < d.qubits and 0 <= b < d.qubits
        if d.gate_model:
            for g in d.native_gates:
                assert g in G.GATES
    assert "QuantWare" in D.table()


def test_ionq_payload_shape():
    from ezeos.backends import IonQBackend

    dev = D.get("ionq_forte_enterprise")
    native, _ = transpile(A.bell(), dev)
    payload = IonQBackend(dev).payload(native, 100)
    gates = {op["gate"] for op in payload["input"]["circuit"]}
    assert gates <= {"gpi", "gpi2", "ms"} and "ms" in gates


def test_export_backend(tmp_path):
    from ezeos.backends import backend_for

    dev = D.get("quantware_soprano_d5")
    native, _ = transpile(A.ghz(3), dev)
    path = tmp_path / "ghz.qasm"
    res = backend_for(dev, "export", path=str(path)).run(native, 10)
    assert path.read_text().count("cz") >= 2 and res.metadata["path"] == str(path)


def test_cli(capsys):
    from ezeos.cli import main

    assert main(["devices"]) == 0
    assert main(["run", "ghz:3", "--seed", "1", "--shots", "64"]) == 0
    assert main(["transpile", "grover:11", "--device", "ibm_system_two_heron"]) == 0
    assert main(["anneal", "0-1,1-2,2-0"]) == 0
    out = capsys.readouterr().out
    assert "EZE OS" in out and "cut=2" in out

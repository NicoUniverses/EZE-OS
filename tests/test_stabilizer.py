import math
import random

import pytest

from ezeos import Circuit, Simulator, algorithms as A, devices as D, gates as G
from ezeos.backends import backend_for
from ezeos.cli import main
from ezeos.kernel import Job, Kernel
from ezeos.simulator import NoiseModel
from ezeos.stabilizer import (NotCliffordError, StabilizerSimulator, StabilizerState, clifford_rule,
                              is_clifford, is_clifford_gate, pauli_from_string, pauli_mul, pauli_to_string,
                              random_clifford_circuit)
from ezeos.transpile import transpile

PI = math.pi

# Every Clifford gate (with Clifford parameters) that the gate library can express.
CLIFFORD_GATES = [
    ("id", ()), ("x", ()), ("y", ()), ("z", ()), ("h", ()), ("s", ()), ("sdg", ()), ("sx", ()), ("sxdg", ()),
    ("rx", (PI / 2,)), ("ry", (-PI / 2,)), ("rz", (PI,)), ("p", (PI / 2,)), ("u", (PI / 2, 0.0, PI)),
    ("prx", (PI / 2, PI / 2)), ("gpi", (0.0,)), ("gpi2", (PI / 2,)),
    ("cx", ()), ("cy", ()), ("cz", ()), ("swap", ()), ("iswap", ()), ("ecr", ()),
    ("rxx", (PI / 2,)), ("ryy", (PI / 2,)), ("rzz", (-PI / 2,)), ("cp", (PI,)), ("ms", (0.0, 0.0)),
    ("zz", (PI / 2,)),
]

NON_CLIFFORD = [("t", ()), ("tdg", ()), ("rz", (0.3,)), ("ch", ()), ("cp", (PI / 2,)), ("ccx", ()),
                ("cswap", ()), ("rzz", (0.1,))]


def _circ(n, ops):
    c = Circuit(n)
    for name, qubits, params in ops:
        c.append(name, qubits, params)
    return c


# ------------------------------------------------------------- Pauli algebra
def test_pauli_string_roundtrip():
    for label in ["+XZI", "-YY", "+IIZ", "-XYZ", "+Y"]:
        p = pauli_from_string(label)
        assert pauli_to_string(p, len(label) - 1) == label


def _pauli_matrix(p, d):
    r, x, z = p
    phase = (1, 1j, -1, -1j)[r]
    m = [[0j] * d for _ in range(d)]
    for b in range(d):
        m[b ^ x][b] = phase * (-1 if bin(z & b).count("1") & 1 else 1)
    return m


def test_pauli_mul_matches_matrices():
    labels = ["II", "XY", "YZ", "ZX", "YY", "-XI", "+iZZ", "-iYX"]
    for a in labels:
        for b in labels:
            pa, pb = pauli_from_string(a), pauli_from_string(b)
            want = G.matmul(_pauli_matrix(pa, 4), _pauli_matrix(pb, 4))
            assert G.allclose(_pauli_matrix(pauli_mul(pa, pb), 4), want), (a, b)


def test_y_label_is_the_pauli_y_matrix():
    assert G.allclose(_pauli_matrix(pauli_from_string("Y"), 2), G.get("y").unitary())


def test_pauli_from_string_rejects_garbage():
    with pytest.raises(ValueError):
        pauli_from_string("XQ")


# ------------------------------------------------- rules from exact unitaries
@pytest.mark.parametrize("name,params", CLIFFORD_GATES)
def test_clifford_rule_reproduces_conjugation_exactly(name, params):
    """U P U^dagger built from the rule equals the exact matrix product, for every generator."""
    rule = clifford_rule(name, params)
    k = rule.num_qubits
    d = 1 << k
    u = G.get(name).unitary(params)
    phases = (1, 1j, -1, -1j)

    def pmat(r, x, z):
        m = [[0j] * d for _ in range(d)]
        for b in range(d):
            m[b ^ x][b] = phases[r] * (-1 if bin(z & b).count("1") & 1 else 1)
        return m

    for j in range(k):
        for g, (gx, gz) in enumerate(((1 << j, 0), (0, 1 << j))):
            exact = G.matmul(u, G.matmul(pmat(0, gx, gz), G.dagger(u)))
            assert G.allclose(pmat(*rule.images[2 * j + g]), exact, 1e-9)


@pytest.mark.parametrize("name,params", NON_CLIFFORD)
def test_non_clifford_gates_are_rejected(name, params):
    assert not is_clifford_gate(name, params)
    with pytest.raises(NotCliffordError):
        clifford_rule(name, params)


def test_is_clifford_on_circuits():
    assert is_clifford(A.ghz(5))
    assert not is_clifford(A.qft(3))


# ------------------------------------------------- agreement with state vector
@pytest.mark.parametrize("name,params", CLIFFORD_GATES)
def test_each_gate_matches_state_vector(name, params):
    k = G.get(name).num_qubits
    n = 3
    rng = random.Random(hash(name) & 0xFFFF)
    prep = random_clifford_circuit(n, 12, rng)
    qubits = rng.sample(range(n), k)
    c = prep.copy()
    c.append(name, qubits, params)
    sv = Simulator().statevector(c)
    st = StabilizerSimulator().state(c)
    assert st.to_statevector().fidelity(sv) == pytest.approx(1.0, abs=1e-9)


def test_random_clifford_circuits_match_state_vector():
    rng = random.Random(7)
    gates = ("h", "s", "sdg", "x", "y", "z", "sx", "sxdg", "cx", "cy", "cz", "swap", "iswap", "ecr")
    for trial in range(25):
        n = rng.randint(1, 5)
        c = random_clifford_circuit(n, 40, rng, gates if n > 1 else ("h", "s", "x", "sx"))
        sv = Simulator().statevector(c)
        st = StabilizerSimulator().state(c)
        assert st.to_statevector().fidelity(sv) == pytest.approx(1.0, abs=1e-9), trial


def test_expectation_values_match_state_vector():
    rng = random.Random(11)
    for _ in range(10):
        c = random_clifford_circuit(3, 30, rng)
        sv = Simulator().statevector(c)
        st = StabilizerSimulator().state(c)
        for label in ["ZII", "IXI", "YYZ", "XZX", "IIY", "ZZZ"]:
            assert st.expectation_pauli(label) == pytest.approx(sv.expectation_pauli(label), abs=1e-9)


def test_measurement_statistics_match_state_vector():
    rng = random.Random(3)
    c = random_clifford_circuit(4, 30, rng)
    c.measure_all()
    exact = Simulator(seed=1).run(c, 4000).probabilities()
    got = StabilizerSimulator(seed=2).run(c, 4000).probabilities()
    for key in set(exact) | set(got):
        assert got.get(key, 0) == pytest.approx(exact.get(key, 0), abs=0.05)
    assert set(got) == {k for k, v in exact.items() if v > 0}


# ------------------------------------------------------------- tableau facts
def test_initial_state_and_bell_stabilizers():
    st = StabilizerState(2)
    assert st.stabilizers() == ["+IZ", "+ZI"]
    st.apply("h", [0])
    st.apply("cx", [0, 1])
    assert sorted(st.stabilizers()) == ["+XX", "+ZZ"]
    assert st.expectation_pauli("YY") == -1.0
    assert st.expectation_pauli("ZI") == 0.0


def test_measurement_collapses_and_repeats():
    rng = random.Random(5)
    st = StabilizerState(2)
    st.apply("h", [0])
    st.apply("cx", [0, 1])
    assert not st.is_deterministic(0)
    m0 = st.measure(0, rng)
    assert st.is_deterministic(1)
    assert st.measure(1, rng) == m0
    assert st.measure(0, rng) == m0


def test_reset_returns_qubit_to_zero():
    rng = random.Random(9)
    for _ in range(20):
        st = StabilizerState(1)
        st.apply("h", [0])
        st.reset(0, rng)
        assert st.expectation_pauli("Z") == 1.0


def test_apply_pauli_flips_signs():
    st = StabilizerState(1)
    st.apply_pauli("X", 0)
    assert st.stabilizers() == ["-Z"]
    st.apply_pauli("Z", 0)
    assert st.stabilizers() == ["-Z"]


def test_bad_arguments():
    with pytest.raises(ValueError):
        StabilizerState(0)
    st = StabilizerState(2)
    with pytest.raises(ValueError):
        st.apply("cx", [0, 2])
    with pytest.raises(ValueError):
        st.expectation_pauli("Z")
    with pytest.raises(NotCliffordError):
        StabilizerSimulator().run(A.qft(2), 10)


# ------------------------------------------------------------- large circuits
def test_large_ghz_is_perfectly_correlated():
    n = 200
    res = StabilizerSimulator(seed=4).run(A.ghz(n), 20)
    assert set(res.counts) <= {"0" * n, "1" * n}
    assert len(res.counts) == 2


def test_large_ghz_stabilizers():
    n = 60
    st = StabilizerSimulator().state(A.ghz(n).remove_final_measurements())
    assert st.expectation_pauli("X" * n) == 1.0
    assert st.expectation_pauli("I" * (n - 2) + "ZZ") == 1.0
    assert st.expectation_pauli("I" * (n - 1) + "Z") == 0.0


def test_bernstein_vazirani_is_clifford_and_exact():
    secret = "1011001110"
    c = A.bernstein_vazirani(secret)
    assert is_clifford(c)
    res = StabilizerSimulator(seed=1).run(c, 50)
    assert res.most_likely().endswith(secret) and res.counts[res.most_likely()] == 50


def test_mid_circuit_measurement_and_reset():
    c = Circuit(2, 2)
    c.h(0).measure(0, 0).cx(0, 1).measure(1, 1).reset(0).measure(0, 0)
    res = StabilizerSimulator(seed=2).run(c, 400)
    for bits in res.counts:
        assert bits[1] == "0"            # clbit 0 holds the post-reset measurement
    assert set(res.counts) == {"00", "10"}


# ------------------------------------------------------------- noise
def test_readout_noise_rate():
    c = Circuit(1).measure_all()
    res = StabilizerSimulator(seed=3, noise=NoiseModel(readout=0.1)).run(c, 5000)
    assert res.counts.get("1", 0) / 5000 == pytest.approx(0.1, abs=0.02)


def test_depolarizing_noise_rate():
    c = Circuit(1)
    c.x(0).measure_all()
    res = StabilizerSimulator(seed=3, noise=NoiseModel(p1=0.3)).run(c, 6000)
    # a random X or Y (2/3 of the errors) flips the outcome
    assert res.counts.get("0", 0) / 6000 == pytest.approx(0.2, abs=0.02)


# ------------------------------------------------------------- integration
def test_transpiled_circuits_stay_clifford():
    native, _ = transpile(A.ghz(4), D.get("ibm_system_two_heron"))
    assert is_clifford(native)
    res = StabilizerSimulator(seed=1).run(native, 200)
    assert set(res.counts) <= {"0000", "1111"}


def test_stabilizer_backend_through_kernel():
    k = Kernel()
    jid = k.submit(Job(A.ghz(5), shots=100, device="ezeos_sim", backend="stabilizer", options={"seed": 1}))
    k.run_all()
    job = k.jobs[jid]
    assert job.error is None
    assert set(job.result.counts) <= {"00000", "11111"}
    assert job.result.backend.startswith("stabilizer:")
    assert backend_for(D.get("ezeos_sim"), "stabilizer").name == "stabilizer"


def test_cli_stabilizer(capsys):
    assert main(["stabilizer", "ghz:3", "--stabilizers"]) == 0
    assert sorted(capsys.readouterr().out.split()) == ["+IZZ", "+XXX", "+ZZI"]
    assert main(["stabilizer", "ghz:100", "--shots", "4", "--seed", "1"]) == 0
    assert "100 qubits" in capsys.readouterr().out
    assert main(["stabilizer", "qft:3"]) == 1

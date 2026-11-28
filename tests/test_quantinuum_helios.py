"""Quantinuum Helios native gates: matrices, transpilation, OpenQASM and TKET mapping.

Reference (read 2026-11-28):
https://docs.quantinuum.com/systems/user_guide/hardware_user_guide/system_operation.html
U1q(theta, phi) = exp(-i theta/2 (cos phi X + sin phi Y)), Rz(lam) = exp(-i lam/2 Z),
ZZ() = exp(-i pi/4 Z⊗Z), RZZ(theta) = exp(-i theta/2 Z⊗Z); radians in the formulas,
units of pi in TKET (PhasedX, Rz, ZZMax, ZZPhase).
"""
import cmath
import math
import random

import pytest

from ezeos import algorithms as A
from ezeos import devices as D
from ezeos import gates as G
from ezeos.backends import QuantinuumBackend
from ezeos.backends.vendors import _prx_to_u
from ezeos.circuit import Circuit
from ezeos.qasm import to_qasm2
from ezeos.simulator import circuit_unitary
from ezeos.stabilizer import is_clifford_gate
from ezeos.transpile import transpile

PI = math.pi
X = [[0j, 1 + 0j], [1 + 0j, 0j]]
Y = [[0j, -1j], [1j, 0j]]


def doc_u1q(theta, phi):
    """exp(-i theta/2 n.sigma) = cos(theta/2) I - i sin(theta/2) (cos phi X + sin phi Y)."""
    c, s = math.cos(theta / 2), math.sin(theta / 2)
    n = [[math.cos(phi) * X[r][k] + math.sin(phi) * Y[r][k] for k in range(2)] for r in range(2)]
    return [[c * (r == k) - 1j * s * n[r][k] for k in range(2)] for r in range(2)]


def doc_zz_diag(angle):
    """exp(-i angle Z⊗Z) as a 4x4 diagonal (Z⊗Z eigenvalues +1, -1, -1, +1)."""
    a, b = cmath.exp(-1j * angle), cmath.exp(1j * angle)
    return [[a, 0j, 0j, 0j], [0j, b, 0j, 0j], [0j, 0j, b, 0j], [0j, 0j, 0j, a]]


@pytest.mark.parametrize("theta,phi", [(0.0, 0.0), (PI / 2, 0.0), (PI, PI / 2), (0.73, -1.9), (-2.4, 3.0)])
def test_u1q_matches_quantinuum_definition_exactly(theta, phi):
    u = G.get("u1q").unitary((theta, phi))
    assert G.is_unitary(u)
    assert G.allclose(u, doc_u1q(theta, phi))
    # Quantinuum: U1q(theta, phi) = U(theta, phi - pi/2, pi/2 - phi), up to global phase
    assert G.equal_up_to_phase(u, G.get("u").unitary((theta, phi - PI / 2, PI / 2 - phi)))


def test_zzmax_and_rzz_match_quantinuum_definitions_exactly():
    assert G.allclose(G.get("zzmax").unitary(()), doc_zz_diag(PI / 4))
    for theta in (0.0, 0.3, -1.1, PI / 2, PI):
        assert G.allclose(G.get("rzz").unitary((theta,)), doc_zz_diag(theta / 2))
    # "The error on RZZ(pi/2) is equal to the error of ZZ()": same operation
    assert G.allclose(G.get("zzmax").unitary(()), G.get("rzz").unitary((PI / 2,)))


def test_helios_catalog_entry_uses_documented_natives_and_fidelities():
    helios = D.get("quantinuum_helios")
    assert helios.native_gates == ("u1q", "rz", "zzmax", "rzz")
    assert "prx" not in helios.native_gates
    assert helios.qubits == 98
    assert helios.fidelity_1q == pytest.approx(0.999975)
    assert helios.fidelity_2q == pytest.approx(0.99921)
    assert helios.source.startswith("https://www.quantinuum.com/blog/introducing-helios")


def test_inverse_of_u1q_and_zzmax():
    c = Circuit(2).u1q(0.8, 0.3, 0).zzmax(0, 1).rz(0.2, 1)
    both = Circuit(2)
    both.instructions = c.instructions + c.inverse().instructions
    assert G.allclose(circuit_unitary(both), G.identity(4))


def test_zzmax_is_clifford_and_lowers_exactly():
    assert is_clifford_gate("zzmax")
    native, _ = transpile(Circuit(2).zzmax(0, 1), D.get("iqm_spark"))
    assert G.equal_up_to_phase(circuit_unitary(_reduce(native, 2)), G.get("zzmax").unitary(()))


def _random_circuit(n, depth, rng):
    c = Circuit(n)
    for _ in range(depth):
        a, b = rng.sample(range(n), 2)
        c.u(rng.uniform(-PI, PI), rng.uniform(-PI, PI), rng.uniform(-PI, PI), a)
        c.cx(a, b)
        c.rzz(rng.uniform(-PI, PI), b, a)
        c.zzmax(a, b)
    return c


def _reduce(native, n, layout=None):
    layout = layout or list(range(n))
    idx = {p: k for k, p in enumerate(layout[:n])}
    red = Circuit(n)
    for ins in native:
        red.append(ins.name, [idx[q] for q in ins.qubits], ins.params)
    return red


@pytest.mark.parametrize("seed", [4, 5, 6])
def test_helios_transpile_preserves_exact_unitary(seed):
    rng = random.Random(seed)
    circ = _random_circuit(3, 6, rng)
    native, rep = transpile(circ, D.get("quantinuum_helios"))
    assert {i.name for i in native} <= {"u1q", "rz", "zzmax"}
    assert rep.initial_layout == rep.final_layout  # all-to-all: no SWAPs
    assert G.equal_up_to_phase(circuit_unitary(_reduce(native, 3, rep.initial_layout)), circuit_unitary(circ))


def test_helios_bell_uses_one_fixed_angle_zz():
    native, rep = transpile(A.bell(), D.get("quantinuum_helios"))
    gates = [i.name for i in native if i.is_gate]
    assert gates.count("zzmax") == 1 and "rzz" not in gates
    qasm = to_qasm2(_prx_to_u(native))
    assert "rzz(pi/2)" in qasm and "zzmax" not in qasm and "u1q" not in qasm


def test_tket_ops_use_half_turns():
    c = Circuit(2).u1q(PI / 2, PI, 0).rz(-PI / 4, 1).zzmax(0, 1).rzz(PI / 3, 1, 0)
    c.measure_all()
    ops = QuantinuumBackend.tket_ops(c)
    assert ops[0] == ("PhasedX", (0,), pytest.approx((0.5, 1.0)))
    assert ops[1] == ("Rz", (1,), pytest.approx((-0.25,)))
    assert ops[2] == ("ZZMax", (0, 1), ())
    assert ops[3][0] == "ZZPhase" and ops[3][2] == pytest.approx((1 / 3,))
    assert [o[0] for o in ops[4:]] == ["Measure", "Measure"]
    with pytest.raises(ValueError):
        QuantinuumBackend.tket_ops(Circuit(2).cx(0, 1))

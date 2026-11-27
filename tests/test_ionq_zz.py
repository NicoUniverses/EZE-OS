"""IonQ Forte native ZZ gate: matrix, transpilation and API payload.

Reference: https://docs.ionq.com/guides/getting-started-with-native-gates
(ZZ(t) = exp(-i pi t Z⊗Z), t in turns; MS on Aria-class, ZZ on Forte-class).
"""
import cmath
import math
import random

import pytest

from ezeos import algorithms as A
from ezeos import devices as D
from ezeos import gates as G
from ezeos.backends import IonQBackend
from ezeos.circuit import Circuit
from ezeos.simulator import circuit_unitary
from ezeos.transpile import transpile

PI = math.pi


def ionq_doc_zz(turns):
    """ZZ exactly as IonQ documents it: diag(e^-ipt, e^ipt, e^ipt, e^-ipt)."""
    a, b = cmath.exp(-1j * PI * turns), cmath.exp(1j * PI * turns)
    return [[a, 0j, 0j, 0j], [0j, b, 0j, 0j], [0j, 0j, b, 0j], [0j, 0j, 0j, a]]


@pytest.mark.parametrize("turns", [0.0, 0.25, -0.1, 0.37, 0.5])
def test_zz_matches_ionq_definition_exactly(turns):
    u = G.get("zz").unitary((2 * PI * turns,))
    assert G.is_unitary(u)
    assert G.allclose(u, ionq_doc_zz(turns))  # exact, not only up to phase


def test_zz_is_symmetric_and_inverts_by_negation():
    c = Circuit(2).zz(0.7, 0, 1)
    swapped = Circuit(2).zz(0.7, 1, 0)
    assert G.allclose(circuit_unitary(c), circuit_unitary(swapped))
    both = Circuit(2).zz(0.7, 0, 1).zz(-0.7, 0, 1)
    assert G.allclose(circuit_unitary(both), G.identity(4))
    assert c.inverse().instructions[0].params == (-0.7,)


def test_forte_native_set_follows_ionq_docs():
    forte = D.get("ionq_forte_enterprise")
    assert forte.native_gates == ("gpi", "gpi2", "zz")
    assert "ms" not in forte.native_gates


def _random_circuit(n, depth, rng):
    c = Circuit(n)
    for _ in range(depth):
        a, b = rng.sample(range(n), 2)
        c.u(rng.uniform(-PI, PI), rng.uniform(-PI, PI), rng.uniform(-PI, PI), a)
        c.cx(a, b)
        c.rzz(rng.uniform(-PI, PI), b, a)
    return c


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_forte_transpile_preserves_exact_unitary(seed):
    """Full unitary check (not only probabilities), with the virtual-Z frame undone."""
    rng = random.Random(seed)
    circ = _random_circuit(3, 6, rng)
    native, rep = transpile(circ, D.get("ionq_forte_enterprise"))
    assert {i.name for i in native} <= {"gpi", "gpi2", "zz"}
    assert rep.initial_layout == rep.final_layout  # all-to-all: no SWAPs
    phys = rep.initial_layout[:3]
    idx = {p: k for k, p in enumerate(phys)}
    red = Circuit(3)
    for ins in native:
        red.append(ins.name, [idx[q] for q in ins.qubits], ins.params)
    for p, ang in enumerate(native.metadata["final_z_frame"]):
        if p in idx and abs(ang) > 0:
            red.rz(ang, idx[p])
    assert G.equal_up_to_phase(circuit_unitary(red), circuit_unitary(circ))


def test_forte_payload_uses_zz_in_turns():
    dev = D.get("ionq_forte_enterprise")
    native, _ = transpile(A.bell(), dev)
    ops = IonQBackend(dev).payload(native, 10)["input"]["circuit"]
    zz = [op for op in ops if op["gate"] == "zz"]
    assert len(zz) == 1
    assert set(zz[0]) == {"gate", "targets", "angle"}
    assert zz[0]["angle"] == pytest.approx(0.25)  # CX uses a quarter-turn ZZ

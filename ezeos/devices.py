"""Catalog of quantum processors that can be bought today (late 2026).

Each entry records the manufacturer, model, qubit count, technology, the
native gate set EZE OS compiles to, a coupling map generator and a public
source. Native gate sets and fidelities are *planning assumptions* taken from
public vendor material; always confirm them against the vendor's current
documentation and calibration data before running on real hardware.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

Edge = Tuple[int, int]


# --------------------------------------------------------------------------
# topology helpers
# --------------------------------------------------------------------------

def line(n: int) -> List[Edge]:
    return [(i, i + 1) for i in range(n - 1)]


def ring(n: int) -> List[Edge]:
    return line(n) + ([(n - 1, 0)] if n > 2 else [])


def grid(rows: int, cols: int) -> List[Edge]:
    edges = []
    for r in range(rows):
        for c in range(cols):
            q = r * cols + c
            if c + 1 < cols:
                edges.append((q, q + 1))
            if r + 1 < rows:
                edges.append((q, q + cols))
    return edges


def star(n: int) -> List[Edge]:
    """Qubit 0 in the centre (IQM Spark-like)."""
    return [(0, i) for i in range(1, n)]


def all_to_all(n: int) -> List[Edge]:
    return [(i, j) for i in range(n) for j in range(i + 1, n)]


def heavy_hex_like(n: int) -> List[Edge]:
    """Approximation of IBM heavy-hex connectivity: a line with periodic bridges."""
    edges = line(n)
    for i in range(0, n - 12, 4):
        edges.append((i, i + 12))
    return edges


# --------------------------------------------------------------------------
# device model
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Device:
    key: str
    vendor: str
    model: str
    qubits: int
    technology: str
    form: str                 # "system" (full machine) or "qpu" (chip only) or "annealer"
    native_gates: Tuple[str, ...]
    topology: Callable[[], List[Edge]]
    purchase: str             # how to buy / public price
    source: str               # public reference URL
    sdk: str                  # recommended software path
    fidelity_1q: float = 0.999
    fidelity_2q: float = 0.99
    fidelity_readout: float = 0.98
    gate_model: bool = True
    notes: str = ""
    aliases: Tuple[str, ...] = field(default_factory=tuple)

    def coupling_map(self) -> List[Edge]:
        return self.topology()

    def neighbors(self) -> Dict[int, List[int]]:
        nb: Dict[int, List[int]] = {q: [] for q in range(self.qubits)}
        for a, b in self.coupling_map():
            nb[a].append(b)
            nb[b].append(a)
        return nb

    def is_connected(self, a: int, b: int) -> bool:
        return (a, b) in set(self.coupling_map()) or (b, a) in set(self.coupling_map())

    def summary(self) -> str:
        return (f"{self.vendor} {self.model}: {self.qubits} qubits, {self.technology}, "
                f"native {{{', '.join(self.native_gates)}}}")


IBM_NATIVE = ("rz", "sx", "x", "cz")
IQM_NATIVE = ("prx", "cz")
RIGETTI_NATIVE = ("rx", "rz", "cz", "iswap")
IONQ_NATIVE = ("gpi", "gpi2", "ms")
QUANTINUUM_NATIVE = ("prx", "rz", "rzz")
SUPERCONDUCTING_GENERIC = ("rx", "ry", "rz", "cz")
TRAPPED_ION_GENERIC = ("rx", "ry", "rz", "rxx")
NMR_NATIVE = ("rx", "ry", "rz", "cz")

CATALOG: Dict[str, Device] = {}


def _add(d: Device) -> None:
    CATALOG[d.key] = d
    for a in d.aliases:
        CATALOG.setdefault(a, d)


# --- bare chips (QPUs) ----------------------------------------------------
_add(Device(
    key="quantware_soprano_d5", vendor="QuantWare", model="Soprano-D5", qubits=5,
    technology="superconducting transmon", form="qpu", native_gates=SUPERCONDUCTING_GENERIC,
    topology=lambda: star(5), purchase="Chip only, from EUR 60,000 (public list price)",
    source="https://quantware.com/product/soprano",
    sdk="Bring your own control stack (Qblox, Quantum Machines, Zurich Instruments); EZE OS emits OpenQASM 3",
    fidelity_2q=0.98, aliases=("soprano",),
))
_add(Device(
    key="quantware_contralto_d21", vendor="QuantWare", model="Contralto-D21", qubits=21,
    technology="superconducting transmon", form="qpu", native_gates=SUPERCONDUCTING_GENERIC,
    topology=lambda: grid(3, 7), purchase="Chip only, from EUR 300,000 (public list price)",
    source="https://quantware.com/product/contralto",
    sdk="Bring your own control stack; EZE OS emits OpenQASM 3", fidelity_2q=0.98,
    aliases=("contralto",),
))
_add(Device(
    key="quantware_tenor_d64", vendor="QuantWare", model="Tenor-D64", qubits=64,
    technology="superconducting transmon", form="qpu", native_gates=SUPERCONDUCTING_GENERIC,
    topology=lambda: grid(8, 8), purchase="Chip only, price on request",
    source="https://www.quantware.com/product/tenor",
    sdk="Bring your own control stack; EZE OS emits OpenQASM 3", fidelity_2q=0.98,
    aliases=("tenor",),
))
_add(Device(
    key="rigetti_novera", vendor="Rigetti Computing", model="Novera QPU", qubits=9,
    technology="superconducting transmon (Ankaa-class, tunable couplers)", form="qpu",
    native_gates=RIGETTI_NATIVE, topology=lambda: grid(3, 3),
    purchase="QPU from USD 900,000; full Novera system with fridge and control also sold",
    source="https://www.rigetti.com/",
    sdk="pyQuil / Quil-T, or OpenQASM via Amazon Braket-compatible tooling",
    fidelity_2q=0.99, aliases=("novera",),
))

# --- full on-premises systems --------------------------------------------
_add(Device(
    key="iqm_spark", vendor="IQM Quantum Computers", model="IQM Spark", qubits=5,
    technology="superconducting transmon", form="system", native_gates=IQM_NATIVE,
    topology=lambda: star(5), purchase="Full system, reported under EUR 1M",
    source="https://iqm.tech/products/iqm-spark/", sdk="iqm-client / Qiskit-on-IQM / Cirq-on-IQM",
    fidelity_2q=0.985, aliases=("spark",),
))
_add(Device(
    key="iqm_radiance_20", vendor="IQM Quantum Computers", model="IQM Radiance 20", qubits=20,
    technology="superconducting transmon", form="system", native_gates=IQM_NATIVE,
    topology=lambda: grid(4, 5), purchase="Full system, sales quote",
    source="https://iqm.tech/", sdk="iqm-client / Qiskit-on-IQM", fidelity_2q=0.99,
))
_add(Device(
    key="iqm_radiance_54", vendor="IQM Quantum Computers", model="IQM Radiance 54", qubits=54,
    technology="superconducting transmon", form="system", native_gates=IQM_NATIVE,
    topology=lambda: grid(6, 9), purchase="Full system, sales quote",
    source="https://iqm.tech/", sdk="iqm-client / Qiskit-on-IQM", fidelity_2q=0.99,
    aliases=("radiance",),
))
_add(Device(
    key="ibm_system_two_heron", vendor="IBM", model="Quantum System Two (Heron r2)", qubits=156,
    technology="superconducting transmon", form="system", native_gates=IBM_NATIVE,
    topology=lambda: heavy_hex_like(156), purchase="Full system, contact IBM (no public price)",
    source="https://www.ibm.com/quantum", sdk="Qiskit + qiskit-ibm-runtime", fidelity_2q=0.997,
    aliases=("ibm", "heron"),
))
_add(Device(
    key="ionq_forte_enterprise", vendor="IonQ", model="Forte Enterprise", qubits=36,
    technology="trapped ion (Yb+)", form="system", native_gates=IONQ_NATIVE,
    topology=lambda: all_to_all(36), purchase="Full system, contact sales",
    source="https://ionq.com/", sdk="IonQ API (native gates JSON) / Amazon Braket / Qiskit-IonQ",
    fidelity_2q=0.995, aliases=("ionq", "forte"),
))
_add(Device(
    key="quantinuum_helios", vendor="Quantinuum", model="Helios", qubits=98,
    technology="trapped ion (Ba+)", form="system", native_gates=QUANTINUUM_NATIVE,
    topology=lambda: all_to_all(98), purchase="Sales contract, no public price; also via cloud",
    source="https://www.quantinuum.com/", sdk="pytket + Quantinuum Nexus (qnexus)",
    fidelity_2q=0.999, aliases=("quantinuum", "helios"),
))
_add(Device(
    key="aqt_ibex_q1", vendor="Alpine Quantum Technologies (AQT)", model="IBEX Q1", qubits=12,
    technology="trapped ion (Ca+), 19-inch rack", form="system", native_gates=TRAPPED_ION_GENERIC,
    topology=lambda: all_to_all(12), purchase="Full system, sales quote",
    source="https://www.aqt.eu/", sdk="qiskit-aqt-provider / Amazon Braket", fidelity_2q=0.98,
    aliases=("aqt", "ibex"),
))
_add(Device(
    key="spinq_triangulum", vendor="SpinQ", model="Triangulum", qubits=3,
    technology="NMR (room temperature, desktop)", form="system", native_gates=NMR_NATIVE,
    topology=lambda: all_to_all(3), purchase="Desktop, launched at about USD 58,000",
    source="https://www.spinquanta.com/", sdk="SpinQit; EZE OS emits OpenQASM 2",
    fidelity_1q=0.99, fidelity_2q=0.95, fidelity_readout=0.95,
    notes="Educational device; no entanglement advantage.", aliases=("triangulum",),
))
_add(Device(
    key="spinq_gemini_mini", vendor="SpinQ", model="Gemini Mini", qubits=2,
    technology="NMR (room temperature, portable)", form="system", native_gates=NMR_NATIVE,
    topology=lambda: all_to_all(2), purchase="Portable, launched at about USD 8,700",
    source="https://www.spinquanta.com/", sdk="SpinQit; EZE OS emits OpenQASM 2",
    fidelity_1q=0.99, fidelity_2q=0.95, fidelity_readout=0.95,
    notes="Cheapest quantum computer on the market; educational.", aliases=("gemini_mini",),
))
_add(Device(
    key="dwave_advantage2", vendor="D-Wave", model="Advantage2", qubits=4400,
    technology="superconducting flux qubits, quantum annealing", form="annealer", native_gates=(),
    topology=lambda: [], purchase="On-premises purchase available, contact D-Wave",
    source="https://www.dwavequantum.com/solutions-and-products/systems/",
    sdk="D-Wave Ocean SDK (QUBO / Ising problems, not gate circuits)", gate_model=False,
    aliases=("dwave", "advantage2"),
))
_add(Device(
    key="pasqal_orion", vendor="Pasqal", model="Orion (140+ atoms)", qubits=140,
    technology="neutral atoms (analog / Rydberg)", form="system", native_gates=(),
    topology=lambda: [], purchase="Contract; public deal reported at EUR 12.99M",
    source="https://www.pasqal.com/", sdk="Pulser (analog pulse sequences)", gate_model=False,
    aliases=("pasqal",),
))

# simulator target
_add(Device(
    key="ezeos_sim", vendor="EZE OS", model="Local state-vector simulator", qubits=22,
    technology="classical simulation", form="system",
    native_gates=("u", "rx", "ry", "rz", "h", "x", "cx", "cz", "swap"),
    topology=lambda: all_to_all(22), purchase="Free, included with EZE OS",
    source="https://ezeos.org", sdk="ezeos", fidelity_1q=1.0, fidelity_2q=1.0, fidelity_readout=1.0,
    aliases=("local", "sim"),
))


def get(key: str) -> Device:
    k = key.lower().replace("-", "_").replace(" ", "_")
    if k in CATALOG:
        return CATALOG[k]
    matches = [d for d in unique() if k in d.key or k in d.model.lower().replace(" ", "_")]
    if len(matches) == 1:
        return matches[0]
    raise KeyError(f"unknown device '{key}'. Run `ezeos devices` to list them.")


def unique() -> List[Device]:
    seen, out = set(), []
    for d in CATALOG.values():
        if d.key not in seen:
            seen.add(d.key)
            out.append(d)
    return out


def table(gate_model_only: bool = False) -> str:
    rows = [("KEY", "VENDOR", "MODEL", "QUBITS", "FORM", "TECHNOLOGY")]
    for d in unique():
        if gate_model_only and not d.gate_model:
            continue
        rows.append((d.key, d.vendor, d.model, str(d.qubits), d.form, d.technology))
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    return "\n".join("  ".join(c.ljust(w) for c, w in zip(r, widths)) for r in rows)

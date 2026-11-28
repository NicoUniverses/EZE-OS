"""EZE OS - an experimental, hardware-neutral operating layer for quantum processors.

Copyright (C) 2026 Nicolás E. Veiga Palacios. Maintained by EZE Capital (Switzerland).
Licensed under the GNU General Public License v2.0 (GPL-2.0-only).

EXPERIMENTAL SOFTWARE, PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.
"""
__version__ = "0.3.2"
__author__ = "Nicolás E. Veiga Palacios"
__maintainer__ = "EZE Capital (Switzerland)"
__license__ = "GPL-2.0-only"

from . import algorithms, annealing, backends, devices, gates, kernel, qasm, query, stabilizer  # noqa: E402
from .circuit import Circuit, Instruction  # noqa: E402
from .simulator import NoiseModel, Result, Simulator, StateVector, run, statevector  # noqa: E402
from .stabilizer import StabilizerSimulator, StabilizerState  # noqa: E402
from .transpile import transpile  # noqa: E402

__all__ = [
    "Circuit", "Instruction", "NoiseModel", "Result", "Simulator", "StabilizerSimulator",
    "StabilizerState", "StateVector",
    "algorithms", "annealing", "backends", "devices", "gates", "kernel", "qasm", "query",
    "stabilizer", "run", "statevector", "transpile", "__version__",
]

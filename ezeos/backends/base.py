"""Backend interface: the boundary between the EZE OS kernel and a device.

A backend receives a circuit that is already transpiled for its device and
returns a :class:`ezeos.simulator.Result`. Vendor backends are thin adapters
around the vendor's official SDK; they are imported lazily so EZE OS itself
has no third-party dependencies.

STATUS: the vendor adapters are experimental and have not been validated on
real hardware by the EZE OS project. Treat them as starting points.
"""
from __future__ import annotations

import importlib
from abc import ABC, abstractmethod
from typing import Dict, Optional

from ..circuit import Circuit
from ..devices import Device
from ..simulator import Result


class BackendUnavailable(RuntimeError):
    """Raised when a vendor SDK or credentials are missing."""


def require(module: str, pip_name: Optional[str] = None):
    try:
        return importlib.import_module(module)
    except ImportError as exc:
        raise BackendUnavailable(
            f"this backend needs the '{pip_name or module}' package: pip install {pip_name or module}"
        ) from exc


class Backend(ABC):
    name: str = "backend"

    def __init__(self, device: Device, **options):
        self.device = device
        self.options: Dict[str, object] = dict(options)

    @abstractmethod
    def run(self, circuit: Circuit, shots: int = 1024) -> Result:
        """Execute an already-transpiled circuit."""

    def validate(self, circuit: Circuit) -> None:
        native = set(self.device.native_gates) | {"measure", "barrier", "reset"}
        bad = sorted({i.name for i in circuit if i.name not in native})
        if bad:
            raise ValueError(f"{self.device.model} does not support {bad}; run ezeos.transpile first")
        if circuit.num_qubits > self.device.qubits:
            raise ValueError("circuit is wider than the device")

    def __repr__(self) -> str:
        return f"<{type(self).__name__} device={self.device.key}>"


def counts_from_bitstrings(bitstrings) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for b in bitstrings:
        out[b] = out.get(b, 0) + 1
    return out

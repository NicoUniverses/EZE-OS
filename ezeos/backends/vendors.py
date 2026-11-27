"""Experimental adapters for commercial quantum hardware.

Each adapter converts an EZE OS circuit into the format the vendor's own SDK
expects and submits it. None of these paths has been validated on physical
hardware by the EZE OS project; use them at your own risk, read the vendor
documentation and verify every result.
"""
from __future__ import annotations

import math
import os
from typing import Dict

from ..circuit import Circuit
from ..qasm import to_qasm2, to_qasm3
from ..simulator import NoiseModel, Result, Simulator
from .base import Backend, BackendUnavailable, require


class LocalBackend(Backend):
    """EZE OS state-vector simulator, optionally with the device's noise profile."""

    name = "local"

    def run(self, circuit: Circuit, shots: int = 1024) -> Result:
        noisy = bool(self.options.get("noisy", False))
        noise = NoiseModel.from_device(self.device) if noisy else None
        used = sorted({q for i in circuit for q in i.qubits})
        if used and len(used) < circuit.num_qubits:   # simulate only the qubits the job touches
            circuit = _compact(circuit, used)
        sim = Simulator(seed=self.options.get("seed"), noise=noise)
        res = sim.run(circuit, shots)
        res.backend = f"local:{self.device.key}{':noisy' if noisy else ''}"
        return res


class StabilizerBackend(Backend):
    """EZE OS stabilizer (Clifford) simulator: no width limit beyond the device itself."""

    name = "stabilizer"

    def run(self, circuit: Circuit, shots: int = 1024) -> Result:
        from ..stabilizer import StabilizerSimulator

        noisy = bool(self.options.get("noisy", False))
        noise = NoiseModel.from_device(self.device) if noisy else None
        sim = StabilizerSimulator(seed=self.options.get("seed"), noise=noise)
        res = sim.run(circuit, shots)
        res.backend = f"stabilizer:{self.device.key}{':noisy' if noisy else ''}"
        return res


def _compact(circuit: Circuit, used) -> Circuit:
    idx = {p: k for k, p in enumerate(used)}
    c = Circuit(len(used), circuit.num_clbits, circuit.name, metadata=dict(circuit.metadata))
    for ins in circuit:
        if ins.name == "barrier":
            continue
        c.append(ins.name, [idx[q] for q in ins.qubits], ins.params, ins.clbits)
    return c


class IBMBackend(Backend):
    """IBM Quantum via qiskit + qiskit-ibm-runtime (Sampler primitive)."""

    name = "ibm"

    def run(self, circuit: Circuit, shots: int = 1024) -> Result:
        qiskit = require("qiskit")
        runtime = require("qiskit_ibm_runtime", "qiskit-ibm-runtime")
        qc = qiskit.QuantumCircuit.from_qasm_str(to_qasm2(circuit))
        service = runtime.QiskitRuntimeService()
        backend = service.backend(self.options.get("backend_name") or service.least_busy().name)
        isa = qiskit.transpile(qc, backend=backend, optimization_level=1)
        job = runtime.SamplerV2(mode=backend).run([isa], shots=shots)
        data = job.result()[0].data
        counts = next(iter(data.values())).get_counts()
        return Result(counts, shots, circuit.num_qubits, f"ibm:{backend.name}", metadata={"job_id": job.job_id()})


class BraketBackend(Backend):
    """Amazon Braket (IonQ, IQM, Rigetti, AQT, QuEra) using OpenQASM 3 programs."""

    name = "braket"

    def run(self, circuit: Circuit, shots: int = 1024) -> Result:
        braket_aws = require("braket.aws", "amazon-braket-sdk")
        ir = require("braket.ir.openqasm", "amazon-braket-sdk")
        arn = self.options.get("device_arn")
        if not arn:
            raise BackendUnavailable("pass device_arn='arn:aws:braket:...' for the target QPU")
        device = braket_aws.AwsDevice(arn)
        program = ir.Program(source=to_qasm3(circuit))
        task = device.run(program, shots=shots)
        counts = dict(task.result().measurement_counts)
        return Result(counts, shots, circuit.num_qubits, f"braket:{arn}", metadata={"task": task.id})


class IQMBackend(Backend):
    """IQM Spark / Radiance through iqm-client (Qiskit-on-IQM)."""

    name = "iqm"

    def run(self, circuit: Circuit, shots: int = 1024) -> Result:
        qiskit = require("qiskit")
        iqm = require("iqm.qiskit_iqm", "iqm-client[qiskit]")
        url = self.options.get("server_url") or os.environ.get("IQM_SERVER_URL")
        if not url:
            raise BackendUnavailable("set server_url or IQM_SERVER_URL to your IQM system")
        backend = iqm.IQMProvider(url).get_backend()
        qc = qiskit.QuantumCircuit.from_qasm_str(to_qasm2(_prx_to_u(circuit)))
        job = backend.run(qiskit.transpile(qc, backend=backend), shots=shots)
        return Result(job.result().get_counts(), shots, circuit.num_qubits, f"iqm:{url}")


class IonQBackend(Backend):
    """IonQ native-gate JSON (GPI, GPI2 and MS on Aria / ZZ on Forte), all phases in turns."""

    name = "ionq"

    def payload(self, circuit: Circuit, shots: int) -> Dict:
        ops = []
        for ins in circuit:
            if ins.name == "gpi":
                ops.append({"gate": "gpi", "target": ins.qubits[0], "phase": ins.params[0] / (2 * math.pi)})
            elif ins.name == "gpi2":
                ops.append({"gate": "gpi2", "target": ins.qubits[0], "phase": ins.params[0] / (2 * math.pi)})
            elif ins.name == "ms":
                ops.append({"gate": "ms", "targets": list(ins.qubits),
                            "phases": [p / (2 * math.pi) for p in ins.params]})
            elif ins.name == "zz":
                ops.append({"gate": "zz", "targets": list(ins.qubits), "angle": ins.params[0] / (2 * math.pi)})
        return {"target": self.options.get("target", "qpu.forte-enterprise-1"), "shots": shots,
                "input": {"format": "ionq.circuit.v0", "gateset": "native",
                          "qubits": circuit.num_qubits, "circuit": ops}}

    def run(self, circuit: Circuit, shots: int = 1024) -> Result:
        requests = require("requests")
        key = self.options.get("api_key") or os.environ.get("IONQ_API_KEY")
        if not key:
            raise BackendUnavailable("set IONQ_API_KEY")
        r = requests.post("https://api.ionq.co/v0.3/jobs", json=self.payload(circuit, shots),
                          headers={"Authorization": f"apiKey {key}"}, timeout=60)
        r.raise_for_status()
        job = r.json()
        return Result({}, shots, circuit.num_qubits, "ionq", metadata={"job": job, "status": "submitted"})


class QuantinuumBackend(Backend):
    """Quantinuum Helios via pytket + qnexus (OpenQASM 2 import)."""

    name = "quantinuum"

    def run(self, circuit: Circuit, shots: int = 1024) -> Result:
        qasm_mod = require("pytket.qasm", "pytket")
        qnx = require("qnexus")
        tk = qasm_mod.circuit_from_qasm_str(to_qasm2(_prx_to_u(circuit)))
        project = qnx.projects.get_or_create(name="ezeos")
        ref = qnx.circuits.upload(circuit=tk, name=circuit.name, project=project)
        device = self.options.get("device_name", "Helios-1")
        compiled = qnx.compile(programs=[ref], backend_config=qnx.QuantinuumConfig(device_name=device),
                               project=project)
        job = qnx.start_execute_job(programs=compiled, n_shots=[shots],
                                    backend_config=qnx.QuantinuumConfig(device_name=device), project=project)
        qnx.jobs.wait_for(job)
        res = qnx.jobs.results(job)[0].download_result()
        counts = {"".join(map(str, k)): v for k, v in res.get_counts().items()}
        return Result(counts, shots, circuit.num_qubits, f"quantinuum:{device}")


class OpenQASMExportBackend(Backend):
    """For bare QPUs (QuantWare, Rigetti Novera, SpinQ): write OpenQASM for your control stack.

    QuantWare and Novera chips are driven by the buyer's own control electronics
    (Qblox, Quantum Machines, Zurich Instruments, Rigetti control). EZE OS hands
    over a native-gate OpenQASM 3 program; pulse calibration stays with the lab.
    """

    name = "export"

    def run(self, circuit: Circuit, shots: int = 1024) -> Result:
        path = self.options.get("path", f"{circuit.name}.{self.device.key}.qasm")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f"// EZE OS export for {self.device.vendor} {self.device.model}, shots={shots}\n")
            fh.write(to_qasm3(circuit))
        return Result({}, shots, circuit.num_qubits, f"export:{path}", metadata={"path": path})


def _prx_to_u(circuit: Circuit) -> Circuit:
    """PRX(theta, phi) == U(theta, phi - pi/2, pi/2 - phi) for OpenQASM 2 export."""
    c = Circuit(circuit.num_qubits, circuit.num_clbits, circuit.name)
    for ins in circuit:
        if ins.name == "prx":
            th, ph = ins.params
            c.append("u", ins.qubits, (th, ph - math.pi / 2, math.pi / 2 - ph))
        elif ins.name == "rzz":
            c.append("rzz", ins.qubits, ins.params)
        else:
            c.append(ins.name, ins.qubits, ins.params, ins.clbits)
    return c


REGISTRY = {
    "local": LocalBackend,
    "stabilizer": StabilizerBackend,
    "ibm": IBMBackend,
    "braket": BraketBackend,
    "iqm": IQMBackend,
    "ionq": IonQBackend,
    "quantinuum": QuantinuumBackend,
    "export": OpenQASMExportBackend,
}

DEFAULT_FOR_VENDOR = {
    "IBM": "ibm",
    "IQM Quantum Computers": "iqm",
    "IonQ": "ionq",
    "Quantinuum": "quantinuum",
    "Alpine Quantum Technologies (AQT)": "braket",
    "QuantWare": "export",
    "Rigetti Computing": "export",
    "SpinQ": "export",
    "EZE OS": "local",
}


def backend_for(device, kind: str = "auto", **options) -> Backend:
    if kind == "auto":
        kind = DEFAULT_FOR_VENDOR.get(device.vendor, "local")
    try:
        cls = REGISTRY[kind]
    except KeyError:
        raise ValueError(f"unknown backend '{kind}', choose from {sorted(REGISTRY)}")
    return cls(device, **options)

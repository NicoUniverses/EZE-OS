"""The EZE OS kernel: jobs, a priority scheduler and a device resource manager.

This is the "operating system" layer. Programs submit :class:`Job` objects;
the kernel picks a device that can run them, transpiles, dispatches to a
backend and keeps an auditable log of everything that happened.
"""
from __future__ import annotations

import heapq
import itertools
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional

from ..circuit import Circuit
from ..devices import Device, get as get_device, unique
from ..simulator import Result
from ..transpile import TranspileReport, transpile


class JobState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Job:
    circuit: Circuit
    shots: int = 1024
    priority: int = 5                    # 0 = highest
    device: Optional[str] = None         # device key, or None to let the kernel choose
    backend: str = "auto"
    options: Dict[str, object] = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    state: JobState = JobState.QUEUED
    result: Optional[Result] = None
    report: Optional[TranspileReport] = None
    error: Optional[str] = None
    submitted_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None

    @property
    def runtime(self) -> Optional[float]:
        return None if self.finished_at is None else self.finished_at - self.submitted_at


@dataclass
class LogEntry:
    t: float
    job: str
    event: str
    detail: str = ""


class ResourceManager:
    """Chooses a device for a job and tracks which devices are busy."""

    def __init__(self, devices: Optional[List[Device]] = None):
        self.devices = devices or [d for d in unique() if d.gate_model]
        self.busy: Dict[str, str] = {}

    def candidates(self, job: Job) -> List[Device]:
        if job.device:
            return [get_device(job.device)]
        need = job.circuit.num_qubits
        ok = [d for d in self.devices if d.qubits >= need and d.key not in self.busy]
        # prefer: the local simulator for small jobs, then highest expected fidelity
        return sorted(ok, key=lambda d: (d.key != "ezeos_sim", -expected_fidelity(job.circuit, d)))

    def acquire(self, device: Device, job: Job) -> None:
        self.busy[device.key] = job.id

    def release(self, device: Device) -> None:
        self.busy.pop(device.key, None)


def expected_fidelity(circuit: Circuit, device: Device) -> float:
    """Crude success estimate: product of gate and readout fidelities."""
    n1 = sum(1 for i in circuit if i.is_gate and len(i.qubits) == 1)
    n2 = sum(1 for i in circuit if i.is_gate and len(i.qubits) >= 2)
    return (device.fidelity_1q ** n1) * (device.fidelity_2q ** (3 * n2 if device.qubits > 40 else n2)) * \
        (device.fidelity_readout ** circuit.num_qubits)


class Kernel:
    """Priority scheduler with a pluggable backend factory."""

    def __init__(self, resources: Optional[ResourceManager] = None,
                 backend_factory: Optional[Callable] = None):
        from ..backends import backend_for

        self.resources = resources or ResourceManager()
        self.backend_factory = backend_factory or backend_for
        self._queue: List = []
        self._counter = itertools.count()
        self.jobs: Dict[str, Job] = {}
        self.log: List[LogEntry] = []

    # ------------------------------------------------------------------
    def _log(self, job: Job, event: str, detail: str = "") -> None:
        self.log.append(LogEntry(time.time(), job.id, event, detail))

    def submit(self, job: Job) -> str:
        self.jobs[job.id] = job
        heapq.heappush(self._queue, (job.priority, next(self._counter), job.id))
        self._log(job, "submitted", f"{job.circuit!r} shots={job.shots} priority={job.priority}")
        return job.id

    def cancel(self, job_id: str) -> bool:
        job = self.jobs.get(job_id)
        if job and job.state == JobState.QUEUED:
            job.state = JobState.CANCELLED
            self._log(job, "cancelled")
            return True
        return False

    def pending(self) -> int:
        return sum(1 for j in self.jobs.values() if j.state == JobState.QUEUED)

    def step(self) -> Optional[Job]:
        """Run the highest-priority queued job. Returns it, or None if the queue is empty."""
        while self._queue:
            _, _, jid = heapq.heappop(self._queue)
            job = self.jobs[jid]
            if job.state != JobState.QUEUED:
                continue
            self._execute(job)
            return job
        return None

    def run_all(self) -> List[Job]:
        done = []
        while True:
            j = self.step()
            if j is None:
                return done
            done.append(j)

    def _execute(self, job: Job) -> None:
        job.state = JobState.RUNNING
        cands = self.resources.candidates(job)
        if not cands:
            job.state, job.error = JobState.FAILED, "no device can run this job"
            self._log(job, "failed", job.error)
            return
        device = cands[0]
        self.resources.acquire(device, job)
        self._log(job, "dispatched", device.key)
        try:
            native, report = transpile(job.circuit, device)
            job.report = report
            self._log(job, "transpiled", str(report))
            backend = self.backend_factory(device, job.backend, **job.options)
            job.result = backend.run(native, job.shots)
            job.state = JobState.DONE
            self._log(job, "done", repr(job.result))
        except Exception as exc:  # noqa: BLE001 - every failure must be logged, never swallowed silently
            job.state, job.error = JobState.FAILED, f"{type(exc).__name__}: {exc}"
            self._log(job, "failed", job.error)
        finally:
            job.finished_at = time.time()
            self.resources.release(device)

    def status(self) -> str:
        lines = [f"{'JOB':12}  {'STATE':9}  {'DEVICE':24}  RESULT"]
        for j in self.jobs.values():
            dev = j.report.device if j.report else (j.device or "-")
            res = j.result.most_likely() if j.result and j.result.counts else (j.error or "")
            lines.append(f"{j.id:12}  {j.state.value:9}  {dev:24}  {res}")
        return "\n".join(lines)

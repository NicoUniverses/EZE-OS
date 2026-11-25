"""Command-line interface: ``ezeos <command>``."""
from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from . import __version__
from . import algorithms as A
from .devices import get as get_device, table
from .kernel import Job, Kernel
from .qasm import from_qasm2, to_qasm3
from .transpile import transpile

BANNER = f"EZE OS {__version__} - experimental quantum operating layer (GPL-2.0, no warranty)"


def _load(spec: str):
    """A file path (OpenQASM 2) or a built-in algorithm like ``ghz:4`` / ``grover:101``."""
    if spec.endswith(".qasm"):
        with open(spec, encoding="utf-8") as fh:
            return from_qasm2(fh.read())
    name, _, arg = spec.partition(":")
    if name not in A.ALGORITHMS:
        raise SystemExit(f"unknown program '{spec}'. built-ins: {', '.join(sorted(A.ALGORITHMS))}")
    fn = A.ALGORITHMS[name]
    if name in ("ghz", "qft", "phase_estimation") and arg:
        return fn(float(arg) if name == "phase_estimation" else int(arg))
    if name in ("bernstein_vazirani", "grover") and arg:
        return fn(arg)
    if name == "deutsch_jozsa" and arg:
        return fn(int(arg))
    defaults = {"ghz": (3,), "qft": (3,), "bernstein_vazirani": ("1011",), "grover": ("101",),
                "deutsch_jozsa": (3,), "phase_estimation": (0.25,)}
    return fn(*defaults.get(name, ()))


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="ezeos", description=BANNER)
    p.add_argument("--version", action="version", version=BANNER)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("devices", help="list supported commercial quantum chips")

    i = sub.add_parser("info", help="show one device")
    i.add_argument("device")

    t = sub.add_parser("transpile", help="compile a program for a device")
    t.add_argument("program", help="file.qasm or built-in, e.g. ghz:4")
    t.add_argument("--device", default="ezeos_sim")
    t.add_argument("--qasm3", action="store_true", help="print the native OpenQASM 3")

    r = sub.add_parser("run", help="run a program through the EZE OS kernel")
    r.add_argument("program")
    r.add_argument("--device", default="ezeos_sim")
    r.add_argument("--backend", default="local", help="local | export | ibm | braket | iqm | ionq | quantinuum")
    r.add_argument("--shots", type=int, default=1024)
    r.add_argument("--noisy", action="store_true", help="apply the device's noise profile (local backend)")
    r.add_argument("--seed", type=int)
    r.add_argument("--json", action="store_true")

    d = sub.add_parser("draw", help="ASCII drawing of a program")
    d.add_argument("program")

    a = sub.add_parser("anneal", help="solve a MaxCut QUBO (D-Wave style) on the CPU")
    a.add_argument("edges", help="e.g. 0-1,1-2,2-0")

    args = p.parse_args(argv)

    if args.cmd == "devices":
        print(table())
        return 0
    if args.cmd == "info":
        print(get_device(args.device).summary())
        return 0
    if args.cmd == "draw":
        print(_load(args.program).draw())
        return 0
    if args.cmd == "transpile":
        circ = _load(args.program)
        native, report = transpile(circ, get_device(args.device))
        print(report)
        if args.qasm3:
            print(to_qasm3(native))
        return 0
    if args.cmd == "run":
        circ = _load(args.program)
        if not circ.has_measurements():
            circ.measure_all()
        k = Kernel()
        opts = {"noisy": args.noisy, "seed": args.seed} if args.backend == "local" else {}
        jid = k.submit(Job(circ, shots=args.shots, device=args.device, backend=args.backend, options=opts))
        k.run_all()
        job = k.jobs[jid]
        if job.error:
            print(f"error: {job.error}", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps({"job": job.id, "device": job.report.device, "counts": job.result.counts,
                              "report": str(job.report)}, indent=2))
        else:
            print(BANNER)
            print(job.report)
            for bits, c in job.result.top(8):
                bar = "#" * max(1, int(40 * c / job.shots))
                print(f"  {bits}  {c:6d}  {bar}")
        return 0
    if args.cmd == "anneal":
        from .annealing import maxcut_qubo

        edges = [tuple(int(x) for x in e.split("-")) for e in args.edges.split(",")]
        x, e = maxcut_qubo(edges).brute_force() if len(edges) < 40 else maxcut_qubo(edges).simulated_annealing()
        print(f"assignment={x} cut={-e:g}")
        return 0
    return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

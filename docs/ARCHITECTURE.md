# EZE OS architecture

```
 user program (Python API, OpenQASM 2, CLI built-ins)
        │
        ▼
 ┌──────────────┐   Job(circuit, shots, priority, device?)
 │    kernel    │── priority queue ── resource manager (picks a free device by expected fidelity)
 └──────┬───────┘                          │
        ▼                                  ▼
 ┌──────────────┐  lower_to_cx → route (SWAPs) → merge_1q → to_native → cancel
 │  transpiler  │  every rule verified against exact unitaries in tests/
 └──────┬───────┘
        ▼
 ┌──────────────┐  local simulator · IBM · Braket · IQM · IonQ · Quantinuum · OpenQASM 3 export
 │   backends   │  vendor SDKs imported lazily, never required
 └──────┬───────┘
        ▼
     Result(counts, shots, backend, metadata)  +  kernel audit log
```

## Conventions

- Qubit 0 is the least significant bit. Bit strings print with qubit 0 on the right, as in Qiskit.
- For two-qubit matrices the basis index is `2*q1 + q0`; for controlled gates operand 0 is the control.
- Global phase is ignored wherever physics allows it; tests compare unitaries up to phase.

## Why pure Python

EZE OS is meant to be read, audited and ported. A small dependency-free core runs anywhere,
including on the control computers that ship with on-premises systems. Speed-critical paths
can move to native code later behind the same interfaces.

## Adding a device

1. Add a `Device` to `ezeos/devices.py` with its topology, native gates, fidelities and a source URL.
2. If its native set is new, add a branch to `synth_1q` and `_cx_native` in `ezeos/transpile.py`.
3. The parametrized test `test_transpile_preserves_semantics_on_every_device` picks it up automatically.

# Changelog

All notable changes to EZE OS. Versions follow [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-11-25

First public release. Experimental.

### Added
- `ezeos.gates`: 34 exact gate definitions including vendor-native gates.
- `ezeos.circuit`: circuit model, fluent API, depth, layers, inverse, drawing.
- `ezeos.simulator`: state-vector simulator, sampling and trajectory paths, device noise model.
- `ezeos.devices`: catalog of 16 devices from QuantWare, Rigetti, IQM, IBM, IonQ, Quantinuum, AQT, SpinQ, D-Wave, Pasqal.
- `ezeos.transpile`: lowering, routing, single-qubit fusion, native synthesis, IonQ virtual-Z frames.
- `ezeos.backends`: local, IBM, Amazon Braket, IQM, IonQ, Quantinuum and OpenQASM 3 export adapters.
- `ezeos.kernel`: jobs, priority scheduler, resource manager and audit log.
- `ezeos.annealing`: QUBO / Ising models, brute-force and simulated annealing, D-Wave handoff.
- `ezeos.algorithms`: Bell, GHZ, QFT, Bernstein-Vazirani, Deutsch-Jozsa, Grover, QPE, QAOA MaxCut, toy VQE.
- `ezeos` command-line tool.

# Changelog

All notable changes to EZE OS. Versions follow [Semantic Versioning](https://semver.org/).

## [0.3.1] - 2026-11-27

IonQ Forte native gates: the transpiler now emits ZZ instead of Mølmer-Sørensen.

### Fixed
- IonQ Forte Enterprise used `ms` as its two-qubit native gate, but IonQ documents MS only for Aria-class
  systems and ZZ for Forte-class systems
  ([getting started with native gates](https://docs.ionq.com/guides/getting-started-with-native-gates), read
  2026-11-27). The Forte native set is now `gpi`, `gpi2`, `zz`.

### Added
- `zz` gate (`Circuit.zz`): IonQ ZZ(t) = exp(-i·π·t·Z⊗Z) with t in turns; EZE OS stores the angle in radians
  (θ = 2πt) and the IonQ backend sends `{"gate": "zz", "targets": [...], "angle": t}`.
- CX synthesis through ZZ(π/2), a lowering rule for `zz`, OpenQASM export as `rzz`, inversion and stabilizer
  support (ZZ(π/2) is Clifford). The virtual-Z pass leaves ZZ untouched because it commutes with RZ.
- `tests/test_ionq_zz.py`: the matrix is checked entry by entry against IonQ's definition, and transpiled Forte
  circuits are checked against the exact unitary with the virtual-Z frame undone.

## [0.3.0] - 2026-11-26

Stabilizer simulator: Clifford circuits with hundreds or thousands of qubits.

### Added
- `ezeos.stabilizer`: tableau simulator after Aaronson & Gottesman (Phys. Rev. A 70, 052328, 2004) with
  destabilizers, Z measurement, reset, Pauli expectation values and dense export for small states.
- Gate rules are derived from the exact unitaries in `ezeos.gates` by Pauli conjugation, so every gate at a
  Clifford angle (`rz(pi/2)`, `rxx(pi/2)`, `gpi2`, `prx`, `ecr`, `iswap`, transpiled `u`, ...) is supported and
  non-Clifford gates are rejected with `NotCliffordError`.
- `StabilizerSimulator`: shots, mid-circuit measurement, reset, depolarizing (Pauli) and readout noise from
  `NoiseModel`; the measurement-free prefix is evolved once and reused for every shot.
- `is_clifford()`, `random_clifford_circuit()`, `pauli_mul()` and Pauli string helpers.
- `stabilizer` backend for the kernel (`ezeos run ... --backend stabilizer`) and the `ezeos stabilizer` CLI command.
- `tests/test_stabilizer.py`: every rule checked against `U P U^dagger`, and random circuits checked against the
  state-vector simulator (states, Pauli expectations and measurement statistics).

## [0.2.0] - 2026-11-25

Doctrine integration: quantum queries over any database Doctrine DBAL can read.

### Added
- `ezeos.query`: QQL (Quantum Query Language) with `SEARCH` (Grover), `OPTIMIZE` (QUBO → QAOA or annealing)
  and `SAMPLE` (amplitude encoding); parser, planner, JSON protocol and a Doctrine-style `QueryBuilder`.
- `ezeos.query.lexer`: Python port of `Doctrine\Common\Lexer\AbstractLexer` (MIT).
- `ezeos query` CLI command (JSON in, JSON out), used by the PHP bridge.
- `bridges/doctrine-php`: `ezeos/doctrine-quantum` PHP package on Doctrine DBAL 4 and doctrine/lexer 3
  (`QuantumConnection`, `QuantumQueryBuilder`, `QuantumResult`, `QqlLexer`, `ProcessBridge`), examples and tests.
- `third_party/doctrine-lexer`: vendored doctrine/lexer sources with their MIT license.
- `docs/DOCTRINE.md`, `THIRD_PARTY_NOTICES.md`.

### Changed
- The local backend simulates only the qubits a job touches, so large devices run quickly.

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

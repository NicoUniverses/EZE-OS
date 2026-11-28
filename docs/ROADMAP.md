# Roadmap

EZE OS grows in weekly releases. Each release must keep the full test-suite green.

## 0.1 (current)
- Gate library, circuit API, state-vector simulator with device noise
- Catalog of purchasable chips with native gates and topologies
- Transpiler: lowering, SWAP routing, 1q fusion, per-vendor synthesis
- Kernel: jobs, priority scheduler, resource manager, audit log
- Backends: local, IBM, Braket, IQM, IonQ, Quantinuum, OpenQASM 3 export
- QUBO / Ising tools for D-Wave annealers

## 0.2
- [x] Doctrine integration: QQL quantum queries over Doctrine DBAL (PHP bridge + Python engine)

## 0.3
- [x] Stabilizer simulator for large Clifford circuits (`ezeos.stabilizer`, `stabilizer` backend, `ezeos stabilizer` CLI)

## 0.3.x: vendor native-gate corrections
- [x] IonQ Forte: `zz` instead of `ms` (0.3.1)
- [x] Quantinuum Helios: `u1q` (PhasedX) + `rz`, `zzmax` (ZZMax) and `rzz` (ZZPhase) (0.3.2)
- [ ] Rigetti Cepheus generation: RX/RZ + `cz` (no `iswap`), with a public source
- [ ] AQT IBEX Q1: `R(θ, φ)`, `RZ`, `RXX`, with a public source
- [ ] Fidelities in the catalog from public vendor data only (Helios done in 0.3.2; IonQ, AQT and the rest pending)

## Next
- [ ] QQL: COUNT (quantum counting), JOIN of two tables, Doctrine ORM repository helpers
- [ ] Doctrine DBAL middleware that logs QQL next to SQL
- [ ] Density-matrix simulator with T1/T2 relaxation and crosstalk
- [ ] SABRE-style lookahead routing and noise-aware initial layout
- [ ] Two-qubit KAK decomposition and native iSWAP / ECR synthesis
- [ ] OpenQASM 3 parser (classical control, mid-circuit measurement)
- [ ] Pulse-level export for QuantWare chips (Qblox, Quantum Machines, Zurich Instruments)
- [ ] Error mitigation: readout calibration, zero-noise extrapolation
- [ ] Minor-embedding for annealers (Chimera / Pegasus / Zephyr graphs)
- [ ] Kernel: persistent job store, cost accounting per vendor, multi-user quotas
- [ ] Validation runs on real hardware, published with raw data

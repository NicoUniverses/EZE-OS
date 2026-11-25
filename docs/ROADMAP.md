# Roadmap

EZE OS grows in weekly releases. Each release must keep the full test-suite green.

## 0.1 (current)
- Gate library, circuit API, state-vector simulator with device noise
- Catalog of purchasable chips with native gates and topologies
- Transpiler: lowering, SWAP routing, 1q fusion, per-vendor synthesis
- Kernel: jobs, priority scheduler, resource manager, audit log
- Backends: local, IBM, Braket, IQM, IonQ, Quantinuum, OpenQASM 3 export
- QUBO / Ising tools for D-Wave annealers

## Next
- [ ] Density-matrix simulator with T1/T2 relaxation and crosstalk
- [ ] SABRE-style lookahead routing and noise-aware initial layout
- [ ] Two-qubit KAK decomposition and native iSWAP / ECR synthesis
- [ ] OpenQASM 3 parser (classical control, mid-circuit measurement)
- [ ] Pulse-level export for QuantWare chips (Qblox, Quantum Machines, Zurich Instruments)
- [ ] Error mitigation: readout calibration, zero-noise extrapolation
- [ ] Stabilizer simulator for large Clifford circuits
- [ ] Minor-embedding for annealers (Chimera / Pegasus / Zephyr graphs)
- [ ] Kernel: persistent job store, cost accounting per vendor, multi-user quotas
- [ ] Validation runs on real hardware, published with raw data

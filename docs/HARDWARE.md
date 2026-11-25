# Quantum hardware you can buy (November 2026)

This is the catalog behind `ezeos.devices`. Prices are public list prices or figures reported
in the press; most vendors sell by quote only. Everything here is **experimental and may be
out of date**: check with the manufacturer before relying on it.

## Chips sold on their own (bring your own fridge and control electronics)

| Manufacturer | Model | Qubits | Technology | Price | Source |
|---|---|---|---|---|---|
| QuantWare (Netherlands) | Soprano-D5 | 5 | superconducting transmon | from EUR 60,000 | <https://quantware.com/product/soprano> |
| QuantWare | Contralto-D21 | 21 | superconducting transmon | from EUR 300,000 | <https://quantware.com/product/contralto> |
| QuantWare | Tenor-D64 | 64 | superconducting transmon | on request | <https://www.quantware.com/product/tenor> |
| Rigetti Computing (USA) | Novera QPU | 9 | superconducting, tunable couplers | about USD 900,000 for the QPU | <https://www.rigetti.com/> |

A bare QPU needs a dilution refrigerator and room-temperature control electronics
(for example Qblox, Quantum Machines or Zurich Instruments). EZE OS stops at the gate level:
it writes native-gate OpenQASM 3 that the lab's control stack calibrates into pulses.

## Complete on-premises systems

| Manufacturer | Model | Qubits | Technology | Price | Source |
|---|---|---|---|---|---|
| IQM (Finland) | IQM Spark | 5 | superconducting | reported under EUR 1M | <https://iqm.tech/products/iqm-spark/> |
| IQM | Radiance 20 / 54 | 20 / 54 | superconducting | quote | <https://iqm.tech/> |
| IBM (USA) | Quantum System Two, Heron processors | 156 per Heron | superconducting | quote | <https://www.ibm.com/quantum> |
| IonQ (USA) | Forte Enterprise | 36 | trapped ion | quote | <https://ionq.com/> |
| Quantinuum (USA/UK) | Helios | 98 | trapped ion | contract | <https://www.quantinuum.com/> |
| AQT (Austria) | IBEX Q1 | 12 | trapped ion, 19-inch rack | quote | <https://www.aqt.eu/> |
| Rigetti | Novera full system | 9 | superconducting | two systems reported at about USD 5.7M | <https://www.rigetti.com/> |
| Pasqal (France) | Orion | 140+ atoms | neutral atoms, analog | contract | <https://www.pasqal.com/> |

## Desktop and educational machines

| Manufacturer | Model | Qubits | Technology | Price | Source |
|---|---|---|---|---|---|
| SpinQ (China) | Gemini Mini | 2 | NMR, room temperature | about USD 8,700 | <https://www.spinquanta.com/> |
| SpinQ | Triangulum | 3 | NMR, room temperature | about USD 58,000 | <https://www.spinquanta.com/> |

## Quantum annealers

| Manufacturer | Model | Qubits | Technology | Price | Source |
|---|---|---|---|---|---|
| D-Wave (Canada/USA) | Advantage2 | 4,400+ | superconducting flux qubits, annealing | on-premises sale by quote | <https://www.dwavequantum.com/solutions-and-products/systems/> |

Annealers do not run gate circuits. EZE OS models them with `ezeos.annealing.QUBO`
and hands the problem to D-Wave's Ocean SDK.

## Native gate sets used by the transpiler

| Device family | Single-qubit | Two-qubit | Notes |
|---|---|---|---|
| IBM Heron | `rz`, `sx`, `x` | `cz` | RZ is virtual (frame change) |
| IQM | `prx` | `cz` | RZ synthesized from PRX |
| Quantinuum | `prx`, `rz` | `rzz` | arbitrary-angle ZZ |
| IonQ | `gpi`, `gpi2` | `ms` | RZ tracked as a virtual frame |
| AQT | `rx`, `ry`, `rz` | `rxx` | Mølmer-Sørensen as RXX |
| QuantWare, SpinQ | `rx`, `ry`, `rz` | `cz` | depends on the buyer's control stack |
| Rigetti | `rx`, `rz` | `cz`, `iswap` | |

Further reading used to compile this list:
<https://postquantum.com/quantum-computing/merchant-qpu-market/>

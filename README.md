# EZE OS

**An experimental, hardware-neutral operating layer for commercial quantum processors.**

EZE OS takes one quantum program and runs it on the chips you can actually buy today:
superconducting QPUs from QuantWare, Rigetti, IQM and IBM, trapped-ion systems from IonQ,
Quantinuum and AQT, desktop NMR machines from SpinQ, and D-Wave annealers. It compiles the
program to each chip's native gates and wiring, schedules jobs like an operating system and
keeps an audit log of everything it does.

Website: <https://ezeos.org/index.php> · Releases: [GitHub Releases](../../releases)

> **EXPERIMENTAL. NO WARRANTY. NO LIABILITY.** See the [disclaimer](#disclaimer) below.

---

## Author and maintainer

- **Author:** Nicolás E. Veiga Palacios
- **Maintained by:** EZE Capital, Switzerland
- **License:** GNU General Public License, version 2 (GPL-2.0-only), the same license as the Linux kernel
- **Status:** open source, pre-1.0, experimental

## What it does

| Layer | Module | What it gives you |
|---|---|---|
| Gates | `ezeos.gates` | 34 exact gate definitions, including vendor natives (`sx`, `prx`, `gpi`, `gpi2`, `ms`, `ecr`, `rzz`) |
| Circuits | `ezeos.circuit` | Fluent circuit API, depth, layers, inverse, ASCII drawing |
| Simulator | `ezeos.simulator` | Pure-Python state-vector simulator (up to 22 qubits), noise from device fidelities |
| Devices | `ezeos.devices` | Catalog of purchasable chips: qubits, topology, native gates, price, source |
| Transpiler | `ezeos.transpile` | Lowering, routing with SWAP insertion, 1-qubit fusion, native synthesis per vendor |
| Backends | `ezeos.backends` | Adapters for IBM, Amazon Braket, IQM, IonQ, Quantinuum, and OpenQASM 3 export |
| Kernel | `ezeos.kernel` | Jobs, priority scheduler, device resource manager, audit log |
| Annealing | `ezeos.annealing` | QUBO and Ising models, exact and simulated-annealing solvers, D-Wave handoff |
| Algorithms | `ezeos.algorithms` | Bell, GHZ, QFT, Bernstein-Vazirani, Deutsch-Jozsa, Grover, QPE, QAOA, VQE |

No third-party dependencies. Vendor SDKs are imported only when you use that vendor's backend.

## Install

```bash
pip install ezeos-0.1.0-py3-none-any.whl     # from the GitHub release
# or from source
pip install .
```

Python 3.10 or newer.

## Quick start

```python
from ezeos import Circuit, devices, transpile, run

bell = Circuit(2).h(0).cx(0, 1).measure_all()
print(run(bell, shots=1000, seed=1).counts)          # {'00': ~500, '11': ~500}

native, report = transpile(bell, devices.get("iqm_spark"))
print(report)                                          # PRX + CZ on IQM's star topology
```

```bash
ezeos devices                                   # chips you can buy, with prices and sources
ezeos run grover:101 --device rigetti_novera --noisy
ezeos transpile ghz:4 --device quantware_soprano_d5 --qasm3 > ghz.qasm
ezeos anneal 0-1,1-2,2-3,3-0                    # MaxCut as a D-Wave style QUBO
```

## Supported hardware

See [docs/HARDWARE.md](docs/HARDWARE.md) for models, manufacturers, prices and sources.

| Manufacturer | Model | Qubits | Technology | How EZE OS reaches it |
|---|---|---|---|---|
| QuantWare | Soprano-D5, Contralto-D21, Tenor-D64 | 5 / 21 / 64 | superconducting | OpenQASM 3 for your control stack |
| Rigetti | Novera QPU | 9 | superconducting | OpenQASM 3 export |
| IQM | Spark, Radiance 20, Radiance 54 | 5 / 20 / 54 | superconducting | iqm-client |
| IBM | Quantum System Two (Heron) | 156 | superconducting | Qiskit Runtime |
| IonQ | Forte Enterprise | 36 | trapped ion | native JSON API |
| Quantinuum | Helios | 98 | trapped ion | pytket + qnexus |
| AQT | IBEX Q1 | 12 | trapped ion | Amazon Braket / provider |
| SpinQ | Gemini Mini, Triangulum | 2 / 3 | NMR, desktop | OpenQASM export |
| D-Wave | Advantage2 | 4,400+ | annealing | `ezeos.annealing` + Ocean |

The vendor adapters have **not** been validated on physical hardware by this project yet.

## Development

```bash
python -m pytest -q          # every rewrite rule is checked against exact unitaries
python scripts/count_lines.py
```

Read [CONTRIBUTING.md](CONTRIBUTING.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and
[docs/ROADMAP.md](docs/ROADMAP.md). Security reports: [SECURITY.md](SECURITY.md).

## Disclaimer

EZE OS is **experimental software**. Everything in this repository, including the code,
the device catalog, prices, the documentation and the website, is experimental and may be
wrong, incomplete or out of date.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR
PURPOSE AND NON-INFRINGEMENT. IN NO EVENT SHALL THE AUTHOR, EZE CAPITAL OR ANY CONTRIBUTOR
BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR ITS USE.
Sections 11 and 12 of the GPL-2.0 apply in full.

- EZE OS can make mistakes. Verify every result independently.
- Nothing produced by EZE OS is financial, investment, medical, legal or other professional advice.
- Running programs on real quantum hardware can cost money. You are responsible for your
  accounts, credentials and bills with each vendor.
- Trademarks belong to their owners. EZE OS is not affiliated with or endorsed by any
  hardware manufacturer listed here.

Copyright (C) 2026 Nicolás E. Veiga Palacios. Maintained by EZE Capital, Switzerland.

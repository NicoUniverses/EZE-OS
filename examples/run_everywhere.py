"""Compile one GHZ program for every purchasable gate-model chip and compare the cost."""
from ezeos import algorithms, devices, transpile

ghz = algorithms.ghz(4)
print(f"{'device':28} {'2q gates':>8} {'depth':>6} {'swaps':>6}")
for dev in devices.unique():
    if not dev.gate_model or dev.qubits < ghz.num_qubits:
        continue
    native, rep = transpile(ghz, dev)
    print(f"{dev.vendor + ' ' + dev.model:28.28} {rep.two_qubit_after:8d} {rep.depth_after:6d} {rep.swaps_inserted:6d}")
